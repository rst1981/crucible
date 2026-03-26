"""
forge/researchers/gdelt.py — GDELT 2.0 Document API

The Global Database of Events, Language, and Tone (GDELT) monitors news
media globally in real time, updating every 15 minutes. No API key required.

GDELT 2.0 Doc API:
  https://api.gdeltproject.org/api/v2/doc/doc

Key feature: every article has a `tone` score [-100, 100].
  negative tone → conflict, crisis, hostility
  positive tone → cooperation, stability, resolution
This makes GDELT uniquely useful for calibrating Crucible conflict theories
(Richardson, Fearon, Wittman-Zartman).

Themes: GDELT tags each article with CAMEO themes (e.g. "CRISISLEX_CONFLICT",
"ENV_OIL", "ECON_TRADE") — useful for domain-specific filtering.

Modes used here:
  artlist — returns article list (url, title, domain, seendate, language,
             socialimage, themes, tone)

Rate limit: unofficial ~5 req/sec; stay conservative.

Reference: Leetaru & Schrodt (2013). GDELT: Global Data on Events, Location
and Tone. ISA Annual Convention.
"""
from __future__ import annotations

from typing import Any

import httpx

from forge.researchers.base import BaseAdapter, ResearchResult

_BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


class GdeltAdapter(BaseAdapter):
    SOURCE_TYPE = "gdelt"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch(
        self,
        query: str,
        max_results: int = 10,
        calibrates: str | None = None,
        timespan: str = "48h",
    ) -> list[ResearchResult]:
        """
        Search GDELT for recent news articles matching the query.

        Args:
            query:      Keyword(s) or CAMEO theme, e.g. "Iran Strait Hormuz oil"
            max_results: Max articles to return (GDELT returns up to 250)
            calibrates:  Env key hint
            timespan:    How far back to search: "1h", "24h", "48h", "1w", "1m"
        """
        params = {
            "query": query,
            "mode": "artlist",
            "maxrecords": min(max_results, 250),
            "timespan": timespan,
            "format": "json",
            "sort": "DateDesc",
        }
        try:
            resp = await self._client.get(_BASE_URL, params=params, timeout=20.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            return [self._error_result(query, str(exc), calibrates)]

        articles = data.get("articles", [])
        if not articles:
            return [ResearchResult(
                source_type=self.SOURCE_TYPE,
                query=query,
                title=f"GDELT: no articles found for '{query}'",
                summary=f"GDELT returned no results for '{query}' in the last {timespan}.",
                url="",
                calibrates=calibrates,
            )]

        return [_article_to_result(a, query, calibrates) for a in articles[:max_results]]


def _article_to_result(
    article: dict[str, Any],
    query: str,
    calibrates: str | None,
) -> ResearchResult:
    title = article.get("title", "")
    url = article.get("url", "")
    domain = article.get("domain", "")
    seendate = article.get("seendate", "")
    language = article.get("language", "English")
    tone = article.get("tone", None)          # float, negative = conflict
    themes = article.get("themes", "")         # semicolon-separated CAMEO themes

    # Build a summary that includes the tone signal for the Scoping Agent
    tone_desc = ""
    if tone is not None:
        try:
            t = float(tone)
            if t < -5:
                tone_desc = f"Negative tone ({t:.1f}) — signals conflict/crisis. "
            elif t > 5:
                tone_desc = f"Positive tone ({t:.1f}) — signals cooperation/stability. "
        except (ValueError, TypeError):
            pass

    theme_list = [th.strip() for th in themes.split(";") if th.strip()][:5]
    theme_str = ", ".join(theme_list) if theme_list else ""

    summary_parts = [f"[{domain}]"]
    if tone_desc:
        summary_parts.append(tone_desc)
    if theme_str:
        summary_parts.append(f"Themes: {theme_str}.")
    summary_parts.append(f"Published: {seendate}.")
    summary = " ".join(summary_parts)

    return ResearchResult(
        source_type="gdelt",
        query=query,
        title=title,
        summary=summary,
        url=url,
        calibrates=calibrates,
        data={
            "domain": domain,
            "seendate": seendate,
            "language": language,
            "tone": tone,
            "themes": theme_list,
            "socialimage": article.get("socialimage", ""),
        },
        raw=title,
    )
