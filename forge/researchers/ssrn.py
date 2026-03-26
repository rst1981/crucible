"""
forge/researchers/ssrn.py — SSRN search adapter

SSRN (Social Science Research Network) hosts working papers in economics,
finance, law, and political science — high relevance for Crucible scenarios.

SSRN does not offer a public API. This adapter uses two strategies:
  1. SSRN search page scrape (HTML, no auth) — title + abstract + authors
  2. Fallback: Google Scholar-style URL construction for direct paper lookup

Note: SSRN scraping can be fragile. If the scrape fails, the adapter
returns a graceful error result (never raises). The Scoping Agent can
fall back to arXiv for academic theory.

The adapter is intentionally conservative:
  - Max 3 results (scraping is slow)
  - 20s timeout
  - User-agent mimics a browser to avoid bot blocks
"""
from __future__ import annotations

import re
from typing import Any

import httpx

from forge.researchers.base import BaseAdapter, ResearchResult

_SEARCH_URL = "https://www.ssrn.com/index.cfm/en/fen-commons-fen-network-search/"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class SsrnAdapter(BaseAdapter):
    SOURCE_TYPE = "ssrn"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch(
        self,
        query: str,
        max_results: int = 3,
        calibrates: str | None = None,
    ) -> list[ResearchResult]:
        # Cap at 3 — scraping more is slow and fragile
        max_results = min(max_results, 3)

        try:
            resp = await self._client.get(
                _SEARCH_URL,
                params={"query": query, "requestUri": "/search", "pageNumber": 1},
                headers=_HEADERS,
                timeout=20.0,
                follow_redirects=True,
            )
            resp.raise_for_status()
        except Exception as exc:
            return [self._error_result(query, str(exc), calibrates)]

        try:
            return _parse_ssrn_html(resp.text, query, calibrates, max_results)
        except Exception as exc:
            return [self._error_result(query, f"parse error: {exc}", calibrates)]


def _parse_ssrn_html(
    html: str,
    query: str,
    calibrates: str | None,
    max_results: int,
) -> list[ResearchResult]:
    """
    Parse SSRN search results from HTML.

    SSRN's HTML structure changes occasionally. This parser targets the
    most stable patterns. Falls back to a single error result if nothing
    is found.
    """
    results: list[ResearchResult] = []

    # Pattern 1: title in <h3 class="title"> or <div class="title">
    # Pattern 2: abstract in <div class="abstract-text">
    # Pattern 3: authors in <div class="authors">

    # Try to find paper blocks — SSRN uses various wrappers
    # Look for abstract IDs (most stable marker)
    paper_ids = re.findall(r'abstract[_-]?id[=\s]+"?(\d+)"?', html, re.IGNORECASE)
    titles = re.findall(
        r'<(?:h3|h2|div)[^>]*class="[^"]*title[^"]*"[^>]*>\s*<a[^>]*href="([^"]*)"[^>]*>([^<]+)<',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    abstracts = re.findall(
        r'<(?:div|p)[^>]*class="[^"]*abstract[^"]*"[^>]*>(.*?)</(?:div|p)>',
        html,
        re.IGNORECASE | re.DOTALL,
    )

    for i, (url_path, title_raw) in enumerate(titles[:max_results]):
        title = re.sub(r"\s+", " ", title_raw).strip()
        abstract_raw = abstracts[i] if i < len(abstracts) else ""
        abstract = re.sub(r"<[^>]+>", "", abstract_raw)
        abstract = re.sub(r"\s+", " ", abstract).strip()[:400]

        ssrn_id = paper_ids[i] if i < len(paper_ids) else ""
        url = (
            f"https://papers.ssrn.com/abstract={ssrn_id}"
            if ssrn_id
            else f"https://www.ssrn.com{url_path}" if url_path.startswith("/") else url_path
        )

        short = abstract[:300].rstrip() + ("…" if len(abstract) > 300 else "")

        results.append(ResearchResult(
            source_type="ssrn",
            query=query,
            title=title,
            summary=short or f"SSRN working paper: {title}",
            url=url,
            calibrates=calibrates,
            data={
                "ssrn_id": ssrn_id,
                "title": title,
                "abstract": abstract,
            },
            raw=abstract,
        ))

    if not results:
        # Scrape found nothing — return a graceful "no results" result
        return [ResearchResult(
            source_type="ssrn",
            query=query,
            title=f"SSRN search: {query}",
            summary=f"No SSRN results parsed for '{query}'. Try arXiv for this topic.",
            url=f"https://www.ssrn.com/index.cfm/en/fen-commons-fen-network-search/?query={query}",
            calibrates=calibrates,
            data={"note": "scrape returned no structured results"},
        )]

    return results
