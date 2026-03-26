"""
forge/researchers/un.py — United Nations News & Security Council feeds

Aggregates feeds from the UN system. No authentication required.

Feeds:
  UN News (all topics):   https://news.un.org/feed/subscribe/en/news/all/rss.xml
  Security Council:       https://www.un.org/press/en/rss.xml
  OHCHR (human rights):  https://www.ohchr.org/en/rss.xml

Security Council press releases are especially valuable for Crucible:
  - Sanctions committee decisions
  - Ceasefire resolution texts
  - P5 vetoes (signal of bloc alignment)
  - Peacekeeping mission updates

Uses feedparser (already installed). Fetches all feeds in parallel,
filters by keyword relevance, returns top results.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import feedparser
import httpx

from forge.researchers.base import BaseAdapter, ResearchResult

_FEEDS = {
    "un_news":        "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
    "security_council": "https://www.un.org/press/en/rss.xml",
    "ohchr":          "https://www.ohchr.org/en/rss.xml",
}

# Security Council feed is most relevant for conflict scenarios
_SC_KEYWORDS = {
    "resolution", "sanctions", "ceasefire", "veto", "peacekeeping",
    "unanimous", "condemned", "authorized", "demanded",
}


class UnAdapter(BaseAdapter):
    SOURCE_TYPE = "un"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch(
        self,
        query: str,
        max_results: int = 8,
        calibrates: str | None = None,
        feeds: list[str] | None = None,
    ) -> list[ResearchResult]:
        """
        Fetch UN feeds in parallel, filter by keyword, return top results.

        Args:
            query:       Keyword(s), e.g. "Iran sanctions nuclear"
            max_results: Max results to return
            calibrates:  Env key hint
            feeds:       Override feed URLs (uses all three by default)
        """
        feed_urls = feeds or list(_FEEDS.values())

        raw = await asyncio.gather(
            *[self._fetch_feed(url) for url in feed_urls],
            return_exceptions=True,
        )

        all_articles: list[dict[str, Any]] = []
        for feed_result in raw:
            if not isinstance(feed_result, Exception):
                all_articles.extend(feed_result)

        if not all_articles:
            return [self._error_result(query, "no UN feed articles fetched", calibrates)]

        # Score by keyword relevance
        keywords = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 2]
        scored = [
            (a, _score(a, keywords))
            for a in all_articles
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        top = [a for a, s in scored if s > 0][:max_results]
        if not top:
            top = all_articles[:max_results]

        return [_article_to_result(a, query, calibrates) for a in top]

    async def _fetch_feed(self, url: str) -> list[dict[str, Any]]:
        """Fetch and parse one UN RSS feed."""
        try:
            resp = await self._client.get(url, timeout=12.0, follow_redirects=True)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
        except Exception:
            return []

        articles: list[dict[str, Any]] = []
        feed_title = feed.feed.get("title", url)
        is_sc = "press" in url or "security" in url.lower()

        for entry in feed.entries[:25]:
            title = getattr(entry, "title", "")
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            link = getattr(entry, "link", "")
            published = getattr(entry, "published", "") or getattr(entry, "updated", "")

            clean = re.sub(r"<[^>]+>", "", summary).strip()[:400]

            articles.append({
                "title": title,
                "summary": clean,
                "url": link,
                "published": published,
                "feed": feed_title,
                "is_security_council": is_sc,
            })

        return articles


def _score(article: dict[str, Any], keywords: list[str]) -> int:
    title = article.get("title", "").lower()
    body = article.get("summary", "").lower()
    # Extra weight for Security Council articles (high signal for conflict scenarios)
    sc_bonus = 3 if article.get("is_security_council") else 0
    kw_score = sum(
        3 if kw in title else (1 if kw in body else 0)
        for kw in keywords
    )
    return kw_score + sc_bonus


def _article_to_result(
    article: dict[str, Any],
    query: str,
    calibrates: str | None,
) -> ResearchResult:
    summary = article.get("summary", "")
    short = summary[:300].rstrip() + ("…" if len(summary) > 300 else "")
    feed_label = "UN Security Council" if article.get("is_security_council") else article.get("feed", "UN")

    return ResearchResult(
        source_type="un",
        query=query,
        title=article.get("title", ""),
        summary=short or article.get("title", ""),
        url=article.get("url", ""),
        calibrates=calibrates,
        data={
            "feed": feed_label,
            "published": article.get("published", ""),
            "is_security_council": article.get("is_security_council", False),
        },
        raw=summary,
    )
