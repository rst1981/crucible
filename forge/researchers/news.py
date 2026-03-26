"""
forge/researchers/news.py — RSS/OSINT news adapter

Fetches recent news from configurable RSS feeds. Uses feedparser for
parsing. Returns articles as ResearchResult, with summary from the
article description and a link to the full article.

Default feeds cover geopolitics, economics, and markets — tuned for
Crucible scenario research. Callers can pass custom feed URLs.

Uses feedparser (pure Python, no network dependency for parsing).
Each feed fetch is independent; errors on one feed don't block others.

Typical use:
    adapter = NewsAdapter(client)
    # Search across default feeds
    results = await adapter.fetch("Strait of Hormuz oil tanker", max_results=5)
    # Fetch from a specific feed
    results = await adapter.fetch("Reuters geopolitics",
                                   feeds=["https://feeds.reuters.com/Reuters/worldNews"])
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import feedparser
import httpx

from forge.researchers.base import BaseAdapter, ResearchResult

# Default RSS feeds — broad coverage of geopolitics, macro, markets
DEFAULT_FEEDS: list[str] = [
    # Geopolitics / IR
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    # Economics / markets
    "https://feeds.bloomberg.com/markets/news.rss",
    "https://www.ft.com/?format=rss",
    # Defense / security
    "https://www.defensenews.com/arc/outboundfeeds/rss/",
    # Energy
    "https://oilprice.com/rss/main",
]


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
        max_results: int = 5,
        calibrates: str | None = None,
        feeds: list[str] | None = None,
    ) -> list[ResearchResult]:
        """
        Fetch RSS feeds in parallel, filter articles by keyword relevance,
        return top max_results sorted by recency.
        """
        feed_urls = feeds or self._feeds

        # Fetch all feeds in parallel
        raw_feeds = await asyncio.gather(
            *[self._fetch_feed(url) for url in feed_urls],
            return_exceptions=True,
        )

        # Collect all articles across feeds
        all_articles: list[dict[str, Any]] = []
        for feed_result in raw_feeds:
            if isinstance(feed_result, Exception):
                continue
            all_articles.extend(feed_result)

        if not all_articles:
            return [self._error_result(query, "no articles fetched from any feed", calibrates)]

        # Score articles by keyword relevance
        keywords = _tokenize(query)
        scored = [
            (article, _relevance_score(article, keywords))
            for article in all_articles
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Return top results with score > 0, fall back to most recent
        top = [a for a, s in scored if s > 0][:max_results]
        if not top:
            top = all_articles[:max_results]  # no keyword match; return most recent

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
        for entry in feed.entries[:20]:  # cap per feed
            title = getattr(entry, "title", "")
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            link = getattr(entry, "link", "")
            published = getattr(entry, "published", "") or getattr(entry, "updated", "")
            source = feed.feed.get("title", url)

            # Strip HTML tags from summary
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
    text_title = article.get("title", "").lower()
    text_body = article.get("summary", "").lower()
    score = 0
    for kw in keywords:
        if kw in text_title:
            score += 3
        if kw in text_body:
            score += 1
    return score


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
