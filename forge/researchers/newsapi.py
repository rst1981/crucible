"""
forge/researchers/newsapi.py — NewsAPI.org

Aggregates news from 80,000+ sources via a single keyword search endpoint.
Free tier: 100 requests/day, articles up to 1 month old, content truncated
to ~200 chars (use description field for full summaries).

Free key registration: https://newsapi.org/register
Set env var: NEWSAPI_KEY

API docs: https://newsapi.org/docs/endpoints/everything
Rate limit: 100 req/day free tier; up to 1000/day developer tier (paid).

Note: On the free tier, `content` is truncated — use `description` as the
primary summary field. The description is typically 2-3 full sentences.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from forge.researchers.base import BaseAdapter, ResearchResult

_BASE_URL = "https://newsapi.org/v2/everything"

# High-quality English-language sources to prefer when not domain-specific
_PREFERRED_SOURCES = (
    "reuters,associated-press,bbc-news,bloomberg,financial-times,"
    "the-guardian-uk,the-wall-street-journal,al-jazeera-english,"
    "foreign-policy,the-economist"
)


class NewsApiAdapter(BaseAdapter):
    SOURCE_TYPE = "newsapi"

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str | None = None,
    ) -> None:
        self._client = client
        self._api_key = api_key or os.environ.get("NEWSAPI_KEY", "")

    async def fetch(
        self,
        query: str,
        max_results: int = 10,
        calibrates: str | None = None,
        language: str = "en",
        sort_by: str = "relevancy",
        domains: str | None = None,
    ) -> list[ResearchResult]:
        """
        Search all indexed news sources for articles matching the query.

        Args:
            query:       Keyword(s), phrases, or boolean operators
                         e.g. "Iran OR Saudi Arabia oil export"
            max_results: Max articles (capped at 100 on free tier)
            calibrates:  Env key hint
            language:    ISO 639-1 language code, default "en"
            sort_by:     "relevancy" | "popularity" | "publishedAt"
            domains:     Comma-separated source domains to restrict to
                         e.g. "reuters.com,bbc.co.uk"
        """
        if not self._api_key:
            return [self._error_result(query, "NEWSAPI_KEY not set", calibrates)]

        params: dict[str, Any] = {
            "q": query,
            "apiKey": self._api_key,
            "language": language,
            "sortBy": sort_by,
            "pageSize": min(max_results, 100),
        }
        if domains:
            params["domains"] = domains

        try:
            resp = await self._client.get(_BASE_URL, params=params, timeout=15.0)
            data = resp.json()

            # NewsAPI returns 200 even on errors (with status: "error" in body)
            if data.get("status") == "error":
                code = data.get("code", "unknown")
                msg = data.get("message", "NewsAPI error")
                return [self._error_result(query, f"{code}: {msg}", calibrates)]

            resp.raise_for_status()
        except Exception as exc:
            return [self._error_result(query, str(exc), calibrates)]

        articles = data.get("articles", [])
        if not articles:
            return [ResearchResult(
                source_type=self.SOURCE_TYPE,
                query=query,
                title=f"NewsAPI: no results for '{query}'",
                summary=f"NewsAPI returned no articles for '{query}'.",
                url="",
                calibrates=calibrates,
            )]

        return [_article_to_result(a, query, calibrates) for a in articles]


def _article_to_result(
    article: dict[str, Any],
    query: str,
    calibrates: str | None,
) -> ResearchResult:
    title = article.get("title", "") or ""
    description = article.get("description", "") or ""
    url = article.get("url", "") or ""
    published = article.get("publishedAt", "")
    source_name = (article.get("source") or {}).get("name", "")

    # description is the primary summary on free tier (content is truncated)
    summary = description[:300].rstrip() + ("…" if len(description) > 300 else "")
    if not summary:
        summary = f"{title} — {source_name}"

    return ResearchResult(
        source_type="newsapi",
        query=query,
        title=title,
        summary=summary,
        url=url,
        calibrates=calibrates,
        data={
            "source": source_name,
            "published": published,
            "author": article.get("author", ""),
        },
        raw=description,
    )
