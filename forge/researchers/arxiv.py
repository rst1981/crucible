"""
forge/researchers/arxiv.py — arXiv search adapter

Uses the arXiv public API (no auth required) to search for papers by
keyword. Returns abstracts + metadata as ResearchResult.

arXiv API docs: https://arxiv.org/help/api/basics
Rate limit: ~3 req/sec; we stay well under with max_results ≤ 10.

Typical use:
    adapter = ArxivAdapter(client)
    results = await adapter.fetch("arms race Richardson model", max_results=5)
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from forge.researchers.base import BaseAdapter, ResearchResult

_BASE_URL = "https://export.arxiv.org/api/query"
_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class ArxivAdapter(BaseAdapter):
    SOURCE_TYPE = "arxiv"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch(
        self,
        query: str,
        max_results: int = 5,
        calibrates: str | None = None,
    ) -> list[ResearchResult]:
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        try:
            resp = await self._client.get(_BASE_URL, params=params, timeout=15.0)
            resp.raise_for_status()
        except Exception as exc:
            return [self._error_result(query, str(exc), calibrates)]

        try:
            return _parse_arxiv_xml(resp.text, query, calibrates)
        except Exception as exc:
            return [self._error_result(query, f"parse error: {exc}", calibrates)]


def _parse_arxiv_xml(xml_text: str, query: str, calibrates: str | None) -> list[ResearchResult]:
    root = ET.fromstring(xml_text)
    results: list[ResearchResult] = []

    for entry in root.findall("atom:entry", _NS):
        title_el = entry.find("atom:title", _NS)
        summary_el = entry.find("atom:summary", _NS)
        id_el = entry.find("atom:id", _NS)
        published_el = entry.find("atom:published", _NS)

        title = (title_el.text or "").strip().replace("\n", " ")
        abstract = (summary_el.text or "").strip().replace("\n", " ")
        arxiv_url = (id_el.text or "").strip()

        # Extract arXiv ID from URL for the data payload
        arxiv_id_match = re.search(r"arxiv\.org/abs/(.+)$", arxiv_url)
        arxiv_id = arxiv_id_match.group(1) if arxiv_id_match else ""

        # Authors
        authors = [
            (a.find("atom:name", _NS).text or "").strip()
            for a in entry.findall("atom:author", _NS)
            if a.find("atom:name", _NS) is not None
        ]

        # Categories
        categories = [
            c.get("term", "")
            for c in entry.findall("atom:category", _NS)
        ]

        # Short summary for context snippets (first 300 chars of abstract)
        short_summary = abstract[:300].rstrip() + ("…" if len(abstract) > 300 else "")

        data: dict[str, Any] = {
            "arxiv_id": arxiv_id,
            "authors": authors,
            "categories": categories,
            "abstract": abstract,
            "published": (published_el.text or "").strip() if published_el is not None else "",
        }

        results.append(ResearchResult(
            source_type="arxiv",
            query=query,
            title=title,
            summary=short_summary,
            url=arxiv_url,
            calibrates=calibrates,
            data=data,
            raw=abstract,
        ))

    return results
