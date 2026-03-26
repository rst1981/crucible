"""
forge/researchers/fred.py — FRED API adapter (Federal Reserve Economic Data)

Fetches economic time series from FRED. Requires FRED_API_KEY in env.
Free key: https://fredaccount.stlouisfed.org/login/secure/

Two modes:
  1. Series fetch  — given a known series ID (e.g. "GDP", "UNRATE"),
                     returns recent observations + metadata.
  2. Series search — given a keyword, returns matching series IDs + descriptions.

The calibrates hint maps FRED series to Crucible env keys, e.g.:
    "GDP" → "keynesian__gdp_normalized"
    "UNRATE" → "keynesian__unemployment"

Rate limit: 120 req/min. We stay well under with typical usage.

FRED API docs: https://fred.stlouisfed.org/docs/api/fred/
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from forge.researchers.base import BaseAdapter, ResearchResult

_BASE_URL = "https://api.stlouisfed.org/fred"


class FredAdapter(BaseAdapter):
    SOURCE_TYPE = "fred"

    def __init__(self, client: httpx.AsyncClient, api_key: str | None = None) -> None:
        self._client = client
        self._api_key = api_key or os.environ.get("FRED_API_KEY", "")

    async def fetch(
        self,
        query: str,
        max_results: int = 5,
        calibrates: str | None = None,
    ) -> list[ResearchResult]:
        """
        If query looks like a FRED series ID (uppercase, no spaces), fetch
        that series directly. Otherwise, search for matching series.
        """
        if not self._api_key:
            return [self._error_result(query, "FRED_API_KEY not set", calibrates)]

        if _looks_like_series_id(query):
            return await self._fetch_series(query, calibrates)
        else:
            return await self._search_series(query, max_results, calibrates)

    async def _fetch_series(
        self,
        series_id: str,
        calibrates: str | None,
    ) -> list[ResearchResult]:
        """Fetch metadata + recent observations for a known series ID."""
        try:
            # Parallel: series info + recent observations
            info_resp, obs_resp = await _gather(
                self._client.get(
                    f"{_BASE_URL}/series",
                    params={"series_id": series_id, "api_key": self._api_key, "file_type": "json"},
                    timeout=15.0,
                ),
                self._client.get(
                    f"{_BASE_URL}/series/observations",
                    params={
                        "series_id": series_id,
                        "api_key": self._api_key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": 12,  # last 12 observations
                    },
                    timeout=15.0,
                ),
            )
            info_resp.raise_for_status()
            obs_resp.raise_for_status()
        except Exception as exc:
            return [self._error_result(series_id, str(exc), calibrates)]

        try:
            info = info_resp.json()["seriess"][0]
            obs_list = obs_resp.json().get("observations", [])
        except (KeyError, IndexError, Exception) as exc:
            return [self._error_result(series_id, f"parse error: {exc}", calibrates)]

        # Build a plain-language summary
        title = info.get("title", series_id)
        units = info.get("units_short", info.get("units", ""))
        freq = info.get("frequency_short", "")
        latest = next((o["value"] for o in obs_list if o["value"] != "."), "N/A")
        latest_date = obs_list[0]["date"] if obs_list else "unknown"

        summary = (
            f"{title} ({series_id}). Units: {units}. Frequency: {freq}. "
            f"Latest value: {latest} as of {latest_date}."
        )

        # Numeric observations (skip '.' missing values)
        numeric_obs = [
            {"date": o["date"], "value": float(o["value"])}
            for o in obs_list
            if o["value"] != "."
        ]

        data: dict[str, Any] = {
            "series_id": series_id,
            "title": title,
            "units": info.get("units", ""),
            "units_short": units,
            "frequency": freq,
            "seasonal_adjustment": info.get("seasonal_adjustment_short", ""),
            "observations": numeric_obs,
            "latest_value": float(latest) if latest != "N/A" else None,
            "latest_date": latest_date,
        }

        return [ResearchResult(
            source_type="fred",
            query=series_id,
            title=title,
            summary=summary,
            url=f"https://fred.stlouisfed.org/series/{series_id}",
            calibrates=calibrates,
            data=data,
            raw=str(numeric_obs[:5]),
        )]

    async def _search_series(
        self,
        query: str,
        max_results: int,
        calibrates: str | None,
    ) -> list[ResearchResult]:
        """Search FRED for series matching a keyword query."""
        try:
            resp = await self._client.get(
                f"{_BASE_URL}/series/search",
                params={
                    "search_text": query,
                    "api_key": self._api_key,
                    "file_type": "json",
                    "limit": max_results,
                    "order_by": "popularity",
                    "sort_order": "desc",
                },
                timeout=15.0,
            )
            resp.raise_for_status()
        except Exception as exc:
            return [self._error_result(query, str(exc), calibrates)]

        try:
            series_list = resp.json().get("seriess", [])
        except Exception as exc:
            return [self._error_result(query, f"parse error: {exc}", calibrates)]

        results: list[ResearchResult] = []
        for s in series_list:
            series_id = s.get("id", "")
            title = s.get("title", series_id)
            units = s.get("units_short", s.get("units", ""))
            freq = s.get("frequency_short", "")
            notes = s.get("notes", "")[:200]

            summary = f"{title} ({series_id}). {units}, {freq}. {notes}".strip(". ")

            results.append(ResearchResult(
                source_type="fred",
                query=query,
                title=title,
                summary=summary,
                url=f"https://fred.stlouisfed.org/series/{series_id}",
                calibrates=calibrates,
                data={
                    "series_id": series_id,
                    "title": title,
                    "units": units,
                    "frequency": freq,
                    "popularity": s.get("popularity", 0),
                },
                raw=notes,
            ))

        return results or [self._error_result(query, "no series found", calibrates)]


def _looks_like_series_id(query: str) -> bool:
    """Heuristic: FRED series IDs are short, uppercase, no spaces."""
    return bool(query) and len(query) <= 20 and query == query.upper() and " " not in query


async def _gather(*coros):
    """Thin wrapper around asyncio.gather for two coroutines."""
    import asyncio
    return await asyncio.gather(*coros)
