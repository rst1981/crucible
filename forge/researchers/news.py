"""
forge/researchers/news.py — RSS/OSINT news adapter

Fetches recent news from ~50 curated RSS feeds across geopolitics, defense,
economics, energy, corporate, and think tanks. Uses feedparser for parsing.

Each feed fetch is independent; errors on one feed don't block others.
Feeds are fetched in parallel via asyncio.gather().

Filtering:
  - Pass category= to restrict to a subset of feeds (faster, more focused)
  - Pass feeds= to use a completely custom feed list
  - Keyword relevance scoring: title hits weight 3×, summary hits weight 1×

Typical use:
    adapter = NewsAdapter(client)

    # All feeds, keyword search
    results = await adapter.fetch("Strait of Hormuz oil tanker", max_results=10)

    # Category-restricted (faster — only fetches relevant feeds)
    results = await adapter.fetch("OPEC production cut", category="energy", max_results=5)

    # Custom feeds
    results = await adapter.fetch("sanctions Iran",
                                   feeds=["https://home.treasury.gov/.../ofac_recent_actions.xml"])
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import feedparser
import httpx

from forge.researchers.base import BaseAdapter, ResearchResult

# ── Curated feed catalog ──────────────────────────────────────────────────────
# Organized by category. Each feed has been selected for quality, reliability,
# and relevance to consulting/geopolitical/economic scenario research.

FEEDS_BY_CATEGORY: dict[str, list[str]] = {
    "geopolitics": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",               # BBC World
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",     # NYT World
        "https://feeds.reuters.com/Reuters/worldNews",                 # Reuters World
        "https://www.aljazeera.com/xml/rss/all.xml",                  # Al Jazeera
        "https://foreignpolicy.com/feed/",                            # Foreign Policy
        "https://thediplomat.com/feed/",                              # The Diplomat (Asia-Pacific)
        "https://www.foreignaffairs.com/rss.xml",                     # Foreign Affairs
        "https://www.chathamhouse.org/rss.xml",                       # Chatham House
        "https://www.crisisgroup.org/rss.xml",                        # ICG (conflict regions)
        "https://carnegieendowment.org/rss/",                         # Carnegie Endowment
        "https://www.cfr.org/rss/all",                                # Council on Foreign Relations
    ],
    "defense": [
        "https://www.defensenews.com/arc/outboundfeeds/rss/",         # Defense News
        "https://breakingdefense.com/feed/",                          # Breaking Defense
        "https://www.csis.org/rss.xml",                               # CSIS
        "https://www.rand.org/news/press.rss",                        # RAND
        "https://www.iiss.org/rss",                                   # IISS
        "https://www.belfercenter.org/rss.xml",                       # Belfer Center (Harvard)
        "https://warontherocks.com/feed/",                            # War on the Rocks
        "https://www.sipri.org/rss.xml",                              # SIPRI (arms/military)
        "https://www.nato.int/cps/en/natolive/news.rss",              # NATO press
    ],
    "economics": [
        "https://feeds.bloomberg.com/markets/news.rss",               # Bloomberg Markets
        "https://www.ft.com/?format=rss",                             # Financial Times
        "https://feeds.a.dj.com/rss/RSSMarketsMain.aspx",             # WSJ Markets
        "https://www.imf.org/en/Blogs/rss",                           # IMF Blog
        "https://cepr.org/vox/rss.xml",                               # VoxEU (CEPR)
        "https://www.brookings.edu/topic/economics/feed/",            # Brookings Economics
        "https://www.piie.com/rss.xml",                               # Peterson Institute
        "https://www.nber.org/rss/new_working_papers.xml",            # NBER Working Papers
        "https://blogs.worldbank.org/rss.xml",                        # World Bank Blog
        "https://www.project-syndicate.org/rss",                      # Project Syndicate
    ],
    "energy": [
        "https://oilprice.com/rss/main",                              # OilPrice
        "https://www.eia.gov/rss/todayinenergy.xml",                  # EIA Today in Energy
        "https://www.iea.org/news.rss",                               # IEA
        "https://www.ogj.com/rss",                                    # Oil & Gas Journal
        "https://www.energymonitor.ai/feed/",                         # Energy Monitor
        "https://www.spglobal.com/commodityinsights/en/rss/",         # S&P Global Commodities
    ],
    "corporate": [
        "https://feeds.bloomberg.com/markets/news.rss",               # Bloomberg (shared)
        "https://www.ft.com/?format=rss",                             # FT (shared)
        "https://feeds.a.dj.com/rss/RSSBusiness.aspx",               # WSJ Business
        "https://feeds.hbr.org/harvardbusiness",                      # Harvard Business Review
        "https://www.economist.com/finance-and-economics/rss.xml",    # Economist Finance
        "https://feeds.fortune.com/fortune/global500",                # Fortune Global
    ],
    "sanctions": [
        "https://home.treasury.gov/system/files/126/ofac_recent_actions.xml",  # OFAC actions
        "https://feeds.reuters.com/Reuters/worldNews",                 # Reuters (shared)
        "https://www.cfr.org/rss/sanctions",                          # CFR sanctions tracker
    ],
    "think_tanks": [
        "https://www.brookings.edu/feed/",                            # Brookings (all)
        "https://carnegieendowment.org/rss/",                         # Carnegie (shared)
        "https://www.chathamhouse.org/rss.xml",                       # Chatham House (shared)
        "https://www.csis.org/rss.xml",                               # CSIS (shared)
        "https://www.rand.org/news/press.rss",                        # RAND (shared)
        "https://ips-dc.org/feed/",                                   # Institute for Policy Studies
        "https://www.wilsoncenter.org/rss.xml",                       # Wilson Center
    ],
    "conflict": [
        "https://www.crisisgroup.org/rss.xml",                        # ICG (shared)
        "https://warontherocks.com/feed/",                            # WOTR (shared)
        "https://www.iiss.org/rss",                                   # IISS (shared)
        "https://www.un.org/press/en/rss.xml",                        # UN Security Council
        "https://news.un.org/feed/subscribe/en/news/all/rss.xml",     # UN News
        "https://www.aljazeera.com/xml/rss/all.xml",                  # Al Jazeera (shared)
    ],
}

# Flat deduplicated default list — all categories combined
DEFAULT_FEEDS: list[str] = list(dict.fromkeys(
    url
    for feeds in FEEDS_BY_CATEGORY.values()
    for url in feeds
))


class NewsAdapter(BaseAdapter):
    SOURCE_TYPE = "news"

    def __init__(
        self,
        client: httpx.AsyncClient,
        feeds: list[str] | None = None,
    ) -> None:
        self._client = client
        self._feeds = feeds or DEFAULT_FEEDS

    async def fetch(
        self,
        query: str,
        max_results: int = 10,
        calibrates: str | None = None,
        feeds: list[str] | None = None,
        category: str | None = None,
    ) -> list[ResearchResult]:
        """
        Fetch RSS feeds in parallel, filter by keyword relevance, return top results.

        Args:
            query:       Keyword(s) to search for
            max_results: Max articles to return
            calibrates:  Env key hint
            feeds:       Explicit feed URL list (overrides category and defaults)
            category:    One of: geopolitics, defense, economics, energy,
                         corporate, sanctions, think_tanks, conflict
                         Restricts to only that category's feeds (faster).
        """
        if feeds:
            feed_urls = feeds
        elif category and category in FEEDS_BY_CATEGORY:
            feed_urls = FEEDS_BY_CATEGORY[category]
        else:
            feed_urls = self._feeds

        raw_feeds = await asyncio.gather(
            *[self._fetch_feed(url) for url in feed_urls],
            return_exceptions=True,
        )

        all_articles: list[dict[str, Any]] = []
        for feed_result in raw_feeds:
            if not isinstance(feed_result, Exception):
                all_articles.extend(feed_result)

        if not all_articles:
            return [self._error_result(query, "no articles fetched from any feed", calibrates)]

        keywords = _tokenize(query)
        scored = [(a, _relevance_score(a, keywords)) for a in all_articles]
        scored.sort(key=lambda x: x[1], reverse=True)

        top = [a for a, s in scored if s > 0][:max_results]
        if not top:
            top = all_articles[:max_results]

        return [_article_to_result(a, query, calibrates) for a in top]

    async def _fetch_feed(self, url: str) -> list[dict[str, Any]]:
        """Fetch and parse a single RSS feed. Returns list of article dicts."""
        try:
            resp = await self._client.get(url, timeout=10.0, follow_redirects=True)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
        except Exception:
            return []

        articles: list[dict[str, Any]] = []
        for entry in feed.entries[:20]:
            title = getattr(entry, "title", "")
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            link = getattr(entry, "link", "")
            published = getattr(entry, "published", "") or getattr(entry, "updated", "")
            source = feed.feed.get("title", url)

            summary_clean = re.sub(r"<[^>]+>", "", summary).strip()[:400]

            articles.append({
                "title": title,
                "summary": summary_clean,
                "url": link,
                "published": published,
                "source": source,
                "feed_url": url,
            })

        return articles


def _tokenize(query: str) -> list[str]:
    """Lowercase tokens from query string, filtered to meaningful words."""
    stopwords = {"the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "is"}
    return [w for w in re.findall(r"\w+", query.lower()) if w not in stopwords and len(w) > 2]


def _relevance_score(article: dict[str, Any], keywords: list[str]) -> int:
    """Count keyword hits in title (weight 3) + summary (weight 1)."""
    title = article.get("title", "").lower()
    body = article.get("summary", "").lower()
    return sum(3 if kw in title else (1 if kw in body else 0) for kw in keywords)


def _article_to_result(
    article: dict[str, Any],
    query: str,
    calibrates: str | None,
) -> ResearchResult:
    title = article.get("title", "")
    summary = article.get("summary", "")
    short = summary[:300].rstrip() + ("…" if len(summary) > 300 else "")

    return ResearchResult(
        source_type="news",
        query=query,
        title=title,
        summary=short or title,
        url=article.get("url", ""),
        calibrates=calibrates,
        data={
            "title": title,
            "published": article.get("published", ""),
            "source": article.get("source", ""),
            "feed_url": article.get("feed_url", ""),
        },
        raw=summary,
    )
