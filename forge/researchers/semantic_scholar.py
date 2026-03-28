"""
forge/researchers/semantic_scholar.py — Semantic Scholar API adapter

Searches 200M+ academic papers across all disciplines.
No API key required (100 req/5 min unauthenticated).
Covers all arXiv papers plus SSRN, PubMed, ACL, IEEE, and more.

API docs: https://api.semanticscholar.org/graph/v1
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from forge.researchers.base import BaseAdapter, ResearchResult

_BASE_URL = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "title,abstract,year,authors,externalIds,url,openAccessPdf,tldr"


class SemanticScholarAdapter(BaseAdapter):
    SOURCE_TYPE = "semantic_scholar"

    def __init__(self, client: httpx.AsyncClient, api_key: str | None = None) -> None:
        self._client = client
        self._api_key = api_key or os.environ.get("S2_API_KEY", "")

    async def fetch(
        self,
        query: str,
        max_results: int = 5,
        calibrates: str | None = None,
    ) -> list[ResearchResult]:
        import asyncio

        headers = {}
        if self._api_key:
            headers["x-api-key"] = self._api_key

        params = {
            "query": query[:200],
            "limit": min(max_results, 10),
            "fields": _FIELDS,
        }

        # Retry once on 429 — respect Retry-After header if present, else 15s
        for attempt in range(2):
            try:
                resp = await self._client.get(
                    f"{_BASE_URL}/paper/search",
                    params=params,
                    headers=headers,
                    timeout=15.0,
                )
                if resp.status_code == 429:
                    if attempt == 0:
                        wait = int(resp.headers.get("Retry-After", "15"))
                        await asyncio.sleep(min(wait, 30))
                        continue
                    return [self._error_result(query, "rate limited (429)", calibrates)]
                resp.raise_for_status()
                break
            except Exception as exc:
                return [self._error_result(query, str(exc), calibrates)]

        try:
            data = resp.json()
            papers = data.get("data", [])
        except Exception as exc:
            return [self._error_result(query, f"parse error: {exc}", calibrates)]

        if not papers:
            return [self._error_result(query, "no results", calibrates)]

        results = []
        for p in papers:
            title = p.get("title") or ""
            abstract = p.get("abstract") or ""
            tldr = (p.get("tldr") or {}).get("text") or ""
            year = p.get("year") or ""
            authors = [a.get("name", "") for a in (p.get("authors") or [])[:3]]

            # Prefer TLDR for summary (concise), fall back to abstract snippet
            summary = tldr or abstract[:300].rstrip() + ("…" if len(abstract) > 300 else "")

            # Best URL: open access PDF > S2 paper page > externalId
            ext = p.get("externalIds") or {}
            url = (
                (p.get("openAccessPdf") or {}).get("url")
                or p.get("url")
                or (f"https://arxiv.org/abs/{ext['ArXiv']}" if "ArXiv" in ext else "")
                or (f"https://doi.org/{ext['DOI']}" if "DOI" in ext else "")
                or ""
            )

            data_payload: dict[str, Any] = {
                "paper_id": p.get("paperId", ""),
                "year": year,
                "authors": authors,
                "abstract": abstract,
                "external_ids": ext,
                "tldr": tldr,
            }

            results.append(ResearchResult(
                source_type="semantic_scholar",
                query=query,
                title=title,
                summary=summary,
                url=url,
                calibrates=calibrates,
                data=data_payload,
                raw=abstract,
            ))

        return results
