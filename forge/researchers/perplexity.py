"""
forge/researchers/perplexity.py — Perplexity Sonar API adapter

Sends a natural-language research question to Perplexity's Sonar model and
returns a synthesized answer with citations. Unlike keyword-search adapters,
Sonar reasons over its web index and returns a cited prose answer — ideal for
specific quantitative gap-filling questions like:

  "What was the percentage increase in global shipping freight rates during
   historical Middle East conflicts, with specific figures?"

Free trial credits on signup. Paid: ~$0.001-0.005/query (sonar model).
API key: https://www.perplexity.ai/settings/api

Model options (set PERPLEXITY_MODEL env var):
  sonar              — fast, cheap, good for factual retrieval  (default)
  sonar-pro          — deeper reasoning, better for complex economic questions
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from forge.researchers.base import BaseAdapter, ResearchResult

_API_URL = "https://api.perplexity.ai/chat/completions"

_SYSTEM_PROMPT = (
    "You are a quantitative research analyst. Answer the question with "
    "specific numbers, percentages, rates, or ranges wherever available. "
    "Cite your sources inline. Be concise — 3-5 sentences max. "
    "If you cannot find specific quantitative data, say so explicitly."
)


class PerplexityAdapter(BaseAdapter):
    SOURCE_TYPE = "perplexity"

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._client = client
        self._api_key = api_key or os.environ.get("PERPLEXITY_API_KEY", "")
        self._model = model or os.environ.get("PERPLEXITY_MODEL", "sonar")

    async def fetch(
        self,
        query: str,
        max_results: int = 1,
        calibrates: str | None = None,
    ) -> list[ResearchResult]:
        """
        Send query as a research question to Perplexity Sonar.

        query should be a full natural-language question, not keywords.
        max_results is ignored (Sonar returns one synthesized answer).
        """
        if not self._api_key:
            return [self._error_result(query, "PERPLEXITY_API_KEY not set", calibrates)]

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            "max_tokens": 512,
            "temperature": 0.1,
            "return_citations": True,
        }

        try:
            resp = await self._client.post(
                _API_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

            answer = data["choices"][0]["message"]["content"]
            citations: list[str] = data.get("citations", [])

            # Build a clean title from the question (first ~60 chars)
            title = query[:60].rstrip() + ("…" if len(query) > 60 else "")

            # Append citation URLs to summary for traceability
            citation_text = ""
            if citations:
                citation_text = "\nSources: " + " | ".join(citations[:4])

            return [ResearchResult(
                source_type=self.SOURCE_TYPE,
                query=query,
                title=title,
                summary=answer + citation_text,
                url=citations[0] if citations else "",
                calibrates=calibrates,
                data={
                    "answer": answer,
                    "citations": citations,
                    "model": self._model,
                },
                raw=answer,
            )]

        except httpx.HTTPStatusError as exc:
            return [self._error_result(
                query,
                f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
                calibrates,
            )]
        except Exception as exc:
            return [self._error_result(query, str(exc), calibrates)]
