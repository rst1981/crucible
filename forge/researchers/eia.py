"""
forge/researchers/eia.py — US Energy Information Administration

Two modes depending on whether EIA_API_KEY is set:

  Mode 1 — RSS (no key): fetches "Today in Energy" commentary articles.
            Always available, no registration required.
            URL: https://www.eia.gov/rss/todayinenergy.xml

  Mode 2 — API series (free key): fetches energy time-series data.
            Free key: https://www.eia.gov/opendata/register.php
            Set env var: EIA_API_KEY
            Endpoint: https://api.eia.gov/v2/seriesid/{series_id}?api_key=...
            Returns: recent observations (up to 12), units, frequency.

Key energy series IDs (crude oil, natural gas, electricity):
  PET.RWTC.D       — Crude Oil, WTI Spot Price ($/bbl, daily)
  PET.RBRTE.D      — Crude Oil, Brent Spot Price ($/bbl, daily)
  NG.RNGWHHD.D     — Natural Gas, Henry Hub ($/MMBtu, daily)
  PET.MCREXUS1.M   — US Crude Oil Exports (Mb/d, monthly)
  PET.MCRIMUS1.M   — US Crude Oil Imports (Mb/d, monthly)
  ELEC.GEN.ALL-US-99.M — US Net Electricity Generation (MWh, monthly)

EIA series IDs can also be discovered via:
  https://api.eia.gov/v2/seriesid/{id}?api_key=...&out=json
"""
from __future__ import annotations

import os
from typing import Any

import feedparser
import httpx

from forge.researchers.base import BaseAdapter, ResearchResult

_RSS_URL = "https://www.eia.gov/rss/todayinenergy.xml"
_API_BASE = "https://api.eia.gov/v2"

# Common series for quick reference
COMMON_SERIES: dict[str, str] = {
    "PET.RWTC.D":       "WTI Crude Oil Spot Price ($/bbl)",
    "PET.RBRTE.D":      "Brent Crude Oil Spot Price ($/bbl)",
    "NG.RNGWHHD.D":     "Henry Hub Natural Gas Price ($/MMBtu)",
    "PET.MCREXUS1.M":   "US Crude Oil Exports (Mb/d)",
    "PET.MCRIMUS1.M":   "US Crude Oil Imports (Mb/d)",
    "ELEC.GEN.ALL-US-99.M": "US Net Electricity Generation (MWh)",
}


class EiaAdapter(BaseAdapter):
    SOURCE_TYPE = "eia"

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str | None = None,
    ) -> None:
        self._client = client
        self._api_key = api_key or os.environ.get("EIA_API_KEY", "")

    async def fetch(
        self,
        query: str,
        max_results: int = 5,
        calibrates: str | None = None,
    ) -> list[ResearchResult]:
        """
        If query looks like an EIA series ID (uppercase, dots/dashes, no spaces),
        fetch that series via the API (requires key). Otherwise fetch Today in
        Energy RSS filtered by keyword.
        """
        if _looks_like_series_id(query) and self._api_key:
            return await self._fetch_series(query, calibrates)
        elif _looks_like_series_id(query) and not self._api_key:
            # Series requested but no key — explain and fall through to RSS
            rss_results = await self._fetch_rss(query, max_results, calibrates)
            note = ResearchResult(
                source_type=self.SOURCE_TYPE,
                query=query,
                title=f"EIA: API key needed for series '{query}'",
                summary=(
                    f"Series '{query}' requires EIA_API_KEY. "
                    f"Register free at https://www.eia.gov/opendata/register.php. "
                    f"Returning RSS news instead."
                ),
                url="https://www.eia.gov/opendata/register.php",
                calibrates=calibrates,
            )
            return [note] + rss_results
        else:
            return await self._fetch_rss(query, max_results, calibrates)

    async def _fetch_series(
        self,
        series_id: str,
        calibrates: str | None,
    ) -> list[ResearchResult]:
        """Fetch a known EIA series via the v2 API."""
        url = f"{_API_BASE}/seriesid/{series_id}"
        try:
            resp = await self._client.get(
                url,
                params={"api_key": self._api_key, "out": "json", "num": 12},
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            return [self._error_result(series_id, str(exc), calibrates)]

        try:
            series_data = data["response"]["data"]
            description = data["response"].get("description", series_id)
            units = data["response"].get("units", "")
        except (KeyError, TypeError) as exc:
            return [self._error_result(series_id, f"parse error: {exc}", calibrates)]

        if not series_data:
            return [self._error_result(series_id, "no observations returned", calibrates)]

        numeric_obs = [
            {"date": obs.get("period", ""), "value": obs.get("value")}
            for obs in series_data
            if obs.get("value") is not None
        ]
        latest = numeric_obs[0] if numeric_obs else {}
        display_name = COMMON_SERIES.get(series_id, description)

        summary = (
            f"{display_name} ({series_id}). "
            f"Units: {units}. "
            f"Latest: {latest.get('value', 'N/A')} as of {latest.get('date', 'unknown')}. "
            f"{len(numeric_obs)} observations available."
        )

        return [ResearchResult(
            source_type="eia",
            query=series_id,
            title=display_name,
            summary=summary,
            url=f"https://www.eia.gov/opendata/qb.php?sdid={series_id}",
            calibrates=calibrates,
            data={
                "series_id": series_id,
                "description": display_name,
                "units": units,
                "observations": numeric_obs,
                "latest_value": latest.get("value"),
                "latest_date": latest.get("date"),
            },
            raw=str(numeric_obs[:5]),
        )]

    async def _fetch_rss(
        self,
        query: str,
        max_results: int,
        calibrates: str | None,
    ) -> list[ResearchResult]:
        """Fetch and filter EIA Today in Energy RSS by keyword."""
        try:
            resp = await self._client.get(_RSS_URL, timeout=10.0)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
        except Exception as exc:
            return [self._error_result(query, str(exc), calibrates)]

        keywords = [w.lower() for w in query.split() if len(w) > 2]
        results: list[ResearchResult] = []

        for entry in feed.entries[:30]:
            title = getattr(entry, "title", "")
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            link = getattr(entry, "link", "")
            published = getattr(entry, "published", "")

            # Score relevance
            text = (title + " " + summary).lower()
            if not keywords or any(kw in text for kw in keywords):
                import re
                clean = re.sub(r"<[^>]+>", "", summary).strip()[:300]
                results.append(ResearchResult(
                    source_type="eia",
                    query=query,
                    title=title,
                    summary=clean or title,
                    url=link,
                    calibrates=calibrates,
                    data={"published": published, "source": "EIA Today in Energy"},
                    raw=clean,
                ))
                if len(results) >= max_results:
                    break

        return results or [self._error_result(query, "no EIA RSS articles matched", calibrates)]


def _looks_like_series_id(query: str) -> bool:
    """EIA series IDs: uppercase letters, numbers, dots, dashes. No spaces."""
    import re
    return bool(re.match(r'^[A-Z0-9][A-Z0-9._\-]{3,}$', query))
