"""
forge/researchers/worldbank.py — World Bank indicators adapter

Fetches development indicators from the World Bank Open Data API.
No API key required.

Two modes:
  1. Indicator fetch  — given a known indicator code (e.g. "NY.GDP.MKTP.CD"),
                        returns recent annual values for all countries or a
                        specific country.
  2. Indicator search — given a keyword, returns matching indicator codes.

Useful for calibrating macro + geopolitical scenarios with ground-truth data:
    GDP per capita, military expenditure, trade openness, inflation, etc.

World Bank API docs: https://datahelpdesk.worldbank.org/knowledgebase/articles/898581
"""
from __future__ import annotations

from typing import Any

import httpx

from forge.researchers.base import BaseAdapter, ResearchResult

_BASE_URL = "https://api.worldbank.org/v2"

# Common indicator codes worth knowing
COMMON_INDICATORS: dict[str, str] = {
    "NY.GDP.MKTP.CD":    "GDP (current USD)",
    "NY.GDP.PCAP.CD":    "GDP per capita (current USD)",
    "FP.CPI.TOTL.ZG":    "Inflation, consumer prices (annual %)",
    "NE.TRD.GNFS.ZS":    "Trade (% of GDP)",
    "MS.MIL.XPND.GD.ZS": "Military expenditure (% of GDP)",
    "SP.POP.TOTL":        "Population, total",
    "SL.UEM.TOTL.ZS":    "Unemployment, total (% of labor force)",
    "BX.KLT.DINV.CD.WD": "Foreign direct investment, net inflows (USD)",
    "IC.BUS.EASE.XQ":    "Ease of doing business score",
    "GC.DOD.TOTL.GD.ZS": "Central government debt (% of GDP)",
}


class WorldBankAdapter(BaseAdapter):
    SOURCE_TYPE = "world_bank"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch(
        self,
        query: str,
        max_results: int = 5,
        calibrates: str | None = None,
    ) -> list[ResearchResult]:
        """
        If query looks like an indicator code (contains dots, e.g. "NY.GDP.MKTP.CD"),
        fetch that indicator. Otherwise search for matching indicators.

        Optionally qualify with country: "USA:NY.GDP.MKTP.CD" fetches US only.
        """
        if ":" in query:
            country, indicator = query.split(":", 1)
            return await self._fetch_indicator(indicator.strip(), country.strip(), calibrates)
        elif _looks_like_indicator(query):
            return await self._fetch_indicator(query, "all", calibrates)
        else:
            return await self._search_indicators(query, max_results, calibrates)

    async def _fetch_indicator(
        self,
        indicator_id: str,
        country: str,
        calibrates: str | None,
    ) -> list[ResearchResult]:
        """Fetch recent values for a known indicator code."""
        url = f"{_BASE_URL}/country/{country}/indicator/{indicator_id}"
        try:
            resp = await self._client.get(
                url,
                params={"format": "json", "per_page": 10, "mrv": 10},
                timeout=15.0,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            return [self._error_result(indicator_id, str(exc), calibrates)]

        # World Bank returns [metadata, data_array]
        if not isinstance(payload, list) or len(payload) < 2:
            return [self._error_result(indicator_id, "unexpected response format", calibrates)]

        metadata = payload[0]
        data_array = payload[1] or []

        if not data_array:
            return [self._error_result(indicator_id, "no data returned", calibrates)]

        # Group observations by country
        by_country: dict[str, list[dict]] = {}
        for obs in data_array:
            cid = obs.get("countryiso3code") or obs.get("country", {}).get("id", "")
            cname = obs.get("country", {}).get("value", cid)
            key = f"{cname} ({cid})"
            if obs.get("value") is not None:
                by_country.setdefault(key, []).append({
                    "year": obs.get("date", ""),
                    "value": obs["value"],
                })

        # Build one result per country (or one aggregate for "all" with many)
        results: list[ResearchResult] = []
        indicator_name = COMMON_INDICATORS.get(indicator_id, indicator_id)

        for country_name, obs_list in list(by_country.items())[:5]:
            latest = obs_list[0] if obs_list else {}
            summary = (
                f"{indicator_name} for {country_name}. "
                f"Latest: {latest.get('value', 'N/A')} ({latest.get('year', '')}). "
                f"{len(obs_list)} years of data available."
            )
            results.append(ResearchResult(
                source_type="world_bank",
                query=indicator_id,
                title=f"{indicator_name} — {country_name}",
                summary=summary,
                url=f"https://data.worldbank.org/indicator/{indicator_id}",
                calibrates=calibrates,
                data={
                    "indicator_id": indicator_id,
                    "indicator_name": indicator_name,
                    "country": country_name,
                    "observations": obs_list,
                    "latest_value": latest.get("value"),
                    "latest_year": latest.get("year"),
                },
                raw=str(obs_list[:5]),
            ))

        return results or [self._error_result(indicator_id, "no valid data", calibrates)]

    async def _search_indicators(
        self,
        query: str,
        max_results: int,
        calibrates: str | None,
    ) -> list[ResearchResult]:
        """Search World Bank indicator catalog by keyword."""
        try:
            resp = await self._client.get(
                f"{_BASE_URL}/indicator",
                params={"format": "json", "per_page": max_results, "q": query},
                timeout=15.0,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            return [self._error_result(query, str(exc), calibrates)]

        if not isinstance(payload, list) or len(payload) < 2:
            return [self._error_result(query, "unexpected response format", calibrates)]

        indicators = payload[1] or []
        results: list[ResearchResult] = []

        for ind in indicators:
            ind_id = ind.get("id", "")
            name = ind.get("name", ind_id)
            source = ind.get("sourceNote", "")[:200]
            topic = ", ".join(t.get("value", "") for t in ind.get("topics", []))

            summary = f"{name} ({ind_id}). Topics: {topic}. {source}".strip(". ")

            results.append(ResearchResult(
                source_type="world_bank",
                query=query,
                title=name,
                summary=summary[:300],
                url=f"https://data.worldbank.org/indicator/{ind_id}",
                calibrates=calibrates,
                data={
                    "indicator_id": ind_id,
                    "indicator_name": name,
                    "topics": topic,
                    "source_note": source,
                },
                raw=source,
            ))

        return results or [self._error_result(query, "no indicators found", calibrates)]


def _looks_like_indicator(query: str) -> bool:
    """Heuristic: WB indicator codes contain dots, e.g. 'NY.GDP.MKTP.CD'."""
    return "." in query and len(query) <= 30 and " " not in query
