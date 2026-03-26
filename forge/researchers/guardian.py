"""
forge/researchers/guardian.py — Guardian Open Platform API

The Guardian provides a free REST API with full-text search across its
journalism archive. Excellent structured coverage of world news, politics,
economics, and environment.

Free key registration: https://open-platform.theguardian.com/access/
Set env var: GUARDIAN_API_KEY

API docs: https://open-platform.theguardian.com/documentation/
Rate limit: 12 requests/second, 5,000/day on free tier.

show-fields=trailText gives a clean 2-3 sentence summary without requiring
full-text access (which is on a separate commercial plan).

Sections most relevant to Crucible:
  world, politics, business, environment, science, technology,
  money, global-development, us-news, uk-news, australia-news
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from forge.researchers.base import BaseAdapter, ResearchResult

_BASE_URL = "https://content.guardianapis.com/search"


class GuardianAdapter(BaseAdapter):
    SOURCE_TYPE = "guardian"

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str | None = None,
    ) -> None:
        self._client = client
        self._api_key = api_key or os.environ.get("GUARDIAN_API_KEY", "")

    async def fetch(
        self,
        query: str,
        max_results: int = 10,
        calibrates: str | None = None,
        section: str | None = None,
        order_by: str = "relevance",
    ) -> list[ResearchResult]:
        """
        Search Guardian articles by keyword.

        Args:
            query:       Keyword search, e.g. "Iran oil sanctions"
            max_results: Max articles (Guardian free tier: up to 200/request)
            calibrates:  Env key hint
            section:     Optional section filter, e.g. "world", "business"
            order_by:    "relevance" | "newest" | "oldest"
        """
        if not self._api_key:
            return [self._error_result(query, "GUARDIAN_API_KEY not set", calibrates)]

        params: dict[str, Any] = {
            "q": query,
            "api-key": self._api_key,
            "page-size": min(max_results, 50),
            "show-fields": "trailText,thumbnail",
            "order-by": order_by,
        }
        if section:
            params["section"] = section

        try:
            resp = await self._client.get(_BASE_URL, params=params, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            return [self._error_result(query, str(exc), calibrates)]

        try:
            results_raw = data["response"]["results"]
        except (KeyError, TypeError) as exc:
            return [self._error_result(query, f"parse error: {exc}", calibrates)]

        if not results_raw:
            return [ResearchResult(
                source_type=self.SOURCE_TYPE,
                query=query,
                title=f"Guardian: no results for '{query}'",
                summary=f"Guardian search returned no articles for '{query}'.",
                url="",
                calibrates=calibrates,
            )]

        return [_article_to_result(a, query, calibrates) for a in results_raw]


def _article_to_result(
    article: dict[str, Any],
    query: str,
    calibrates: str | None,
) -> ResearchResult:
    title = article.get("webTitle", "")
    url = article.get("webUrl", "")
    section = article.get("sectionId", "")
    published = article.get("webPublicationDate", "")
    fields = article.get("fields", {}) or {}
    trail = fields.get("trailText", "")

    # Strip any HTML tags that sneak in
    import re
    trail_clean = re.sub(r"<[^>]+>", "", trail).strip()
    summary = trail_clean or f"{title} ({section}, {published[:10]})"
    short = summary[:300].rstrip() + ("…" if len(summary) > 300 else "")

    return ResearchResult(
        source_type="guardian",
        query=query,
        title=title,
        summary=short,
        url=url,
        calibrates=calibrates,
        data={
            "section": section,
            "published": published,
            "thumbnail": fields.get("thumbnail", ""),
        },
        raw=trail_clean,
    )
