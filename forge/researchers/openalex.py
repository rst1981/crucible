"""
forge/researchers/openalex.py — OpenAlex API adapter

OpenAlex is a fully open catalog of 250M+ scholarly works.
No API key required. Generous rate limits (~10 req/sec).
Strong coverage: economics, political science, energy, IR, finance.

API docs: https://docs.openalex.org/
Polite pool (faster): set OPENALEX_EMAIL env var (adds mailto= param).
API key (higher rate limits): set OPENALEX_API_KEY env var (adds api_key= param).
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from forge.researchers.base import BaseAdapter, ResearchResult

_BASE_URL = "https://api.openalex.org"


class OpenAlexAdapter(BaseAdapter):
    SOURCE_TYPE = "openalex"

    def __init__(
        self,
        client: httpx.AsyncClient,
        email: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._client = client
        self._email = email or os.environ.get("OPENALEX_EMAIL", "")
        self._api_key = api_key or os.environ.get("OPENALEX_API_KEY", "")

    async def fetch(
        self,
        query: str,
        max_results: int = 5,
        calibrates: str | None = None,
    ) -> list[ResearchResult]:
        params: dict[str, Any] = {
            "search": query[:200],
            "per-page": min(max_results, 10),
            "select": "id,title,abstract_inverted_index,publication_year,authorships,primary_location,open_access,concepts",
            "sort": "relevance_score:desc",
        }
        if self._api_key:
            params["api_key"] = self._api_key
        elif self._email:
            params["mailto"] = self._email

        try:
            resp = await self._client.get(
                f"{_BASE_URL}/works",
                params=params,
                timeout=15.0,
            )
            resp.raise_for_status()
        except Exception as exc:
            return [self._error_result(query, str(exc), calibrates)]

        try:
            data = resp.json()
            works = data.get("results", [])
        except Exception as exc:
            return [self._error_result(query, f"parse error: {exc}", calibrates)]

        if not works:
            return [self._error_result(query, "no results", calibrates)]

        results = []
        for w in works:
            title = w.get("title") or ""
            year = w.get("publication_year") or ""
            authors = [
                a.get("author", {}).get("display_name", "")
                for a in (w.get("authorships") or [])[:3]
            ]

            # Reconstruct abstract from inverted index
            abstract = _reconstruct_abstract(w.get("abstract_inverted_index"))

            # Best URL
            loc = w.get("primary_location") or {}
            oa = w.get("open_access") or {}
            url = (
                oa.get("oa_url")
                or loc.get("landing_page_url")
                or w.get("id", "")
            )

            # Top concepts as domain tags
            concepts = [
                c.get("display_name", "")
                for c in (w.get("concepts") or [])[:5]
                if c.get("score", 0) > 0.3
            ]

            summary = abstract[:300].rstrip() + ("…" if len(abstract) > 300 else "")
            if not summary and concepts:
                summary = f"Topics: {', '.join(concepts)}. Year: {year}."

            data_payload: dict[str, Any] = {
                "openalex_id": w.get("id", ""),
                "year": year,
                "authors": authors,
                "abstract": abstract,
                "concepts": concepts,
                "is_open_access": oa.get("is_oa", False),
            }

            results.append(ResearchResult(
                source_type="openalex",
                query=query,
                title=title,
                summary=summary,
                url=url,
                calibrates=calibrates,
                data=data_payload,
                raw=abstract,
            ))

        return results


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    """OpenAlex stores abstracts as inverted index {word: [positions]}. Reconstruct."""
    if not inverted_index:
        return ""
    try:
        max_pos = max(pos for positions in inverted_index.values() for pos in positions)
        words = [""] * (max_pos + 1)
        for word, positions in inverted_index.items():
            for pos in positions:
                words[pos] = word
        return " ".join(w for w in words if w)
    except Exception:
        return ""
