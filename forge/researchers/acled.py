"""
forge/researchers/acled.py — ACLED (Armed Conflict Location & Event Data)

ACLED is the gold standard for conflict event data. It codes political
violence and protest events globally with actor, location, date, event type,
and fatalities. Updated weekly.

Free academic/NGO key: https://acleddata.com/access-data/
Set env vars: ACLED_API_KEY, ACLED_EMAIL

API docs: https://apidocs.acleddata.com/
Rate limit: ~1000 events per call; paginate for more.

Event types coded by ACLED:
  Battles                     — armed clashes between organized forces
  Explosions/Remote violence  — airstrikes, IEDs, shelling
  Violence against civilians  — targeted attacks on non-combatants
  Protests                    — non-violent demonstrations
  Riots                       — violent demonstrations
  Strategic developments      — HQ establishment, arrests, sanctions

Fatalities field: directly usable as a conflict intensity signal in
Richardson, Fearon, and Wittman-Zartman theory modules.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from forge.researchers.base import BaseAdapter, ResearchResult

_BASE_URL = "https://api.acleddata.com/acled/read"

# ACLED event type → rough Crucible conflict intensity [0,1]
_EVENT_INTENSITY: dict[str, float] = {
    "Battles": 0.85,
    "Explosions/Remote violence": 0.80,
    "Violence against civilians": 0.75,
    "Riots": 0.50,
    "Protests": 0.20,
    "Strategic developments": 0.30,
}


class AcledAdapter(BaseAdapter):
    SOURCE_TYPE = "acled"

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str | None = None,
        email: str | None = None,
    ) -> None:
        self._client = client
        self._api_key = api_key or os.environ.get("ACLED_API_KEY", "")
        self._email = email or os.environ.get("ACLED_EMAIL", "")

    async def fetch(
        self,
        query: str,
        max_results: int = 20,
        calibrates: str | None = None,
        country: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list[ResearchResult]:
        """
        Fetch recent ACLED conflict events for a country or keyword.

        Args:
            query:       Country name, actor name, or keyword (used in country= param)
            max_results: Max ResearchResult objects returned (each summarizes events)
            calibrates:  Env key hint
            country:     Override country filter (e.g. "Iran", "Yemen")
            event_type:  Filter by ACLED type (e.g. "Battles")
            limit:       Raw events to fetch from ACLED (max 500 per call)
        """
        if not self._api_key or not self._email:
            missing = []
            if not self._api_key:
                missing.append("ACLED_API_KEY")
            if not self._email:
                missing.append("ACLED_EMAIL")
            return [self._error_result(query, f"{', '.join(missing)} not set", calibrates)]

        params: dict[str, Any] = {
            "key": self._api_key,
            "email": self._email,
            "limit": min(limit, 500),
            "fields": (
                "event_date|event_type|sub_event_type|actor1|actor2|"
                "country|admin1|location|latitude|longitude|fatalities|notes|source"
            ),
        }

        # Use country param if explicitly provided, otherwise try to use query as country
        target_country = country or query
        params["country"] = target_country

        if event_type:
            params["event_type"] = event_type

        try:
            resp = await self._client.get(_BASE_URL, params=params, timeout=20.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            return [self._error_result(query, str(exc), calibrates)]

        events = data.get("data", [])
        if not events:
            return [ResearchResult(
                source_type=self.SOURCE_TYPE,
                query=query,
                title=f"ACLED: no events found for '{target_country}'",
                summary=(
                    f"ACLED returned no conflict events for '{target_country}'. "
                    f"This may mean low conflict activity or an unrecognized country name."
                ),
                url="https://acleddata.com/data-export-tool/",
                calibrates=calibrates,
            )]

        return _summarize_events(events, query, target_country, calibrates, max_results)


def _summarize_events(
    events: list[dict[str, Any]],
    query: str,
    country: str,
    calibrates: str | None,
    max_results: int,
) -> list[ResearchResult]:
    """
    Convert a list of raw ACLED events into ResearchResult objects.

    Strategy: group events by type, produce one summary result per event type.
    This keeps token cost low while preserving the key signals (intensity, fatalities).
    """
    from collections import defaultdict

    by_type: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        etype = ev.get("event_type", "Unknown")
        by_type[etype].append(ev)

    total_fatalities = sum(
        int(ev.get("fatalities", 0) or 0)
        for ev in events
    )

    results: list[ResearchResult] = []

    for event_type, evs in sorted(by_type.items(), key=lambda x: -len(x[1])):
        if len(results) >= max_results:
            break

        count = len(evs)
        type_fatalities = sum(int(ev.get("fatalities", 0) or 0) for ev in evs)
        intensity = _EVENT_INTENSITY.get(event_type, 0.5)

        # Sample of recent locations
        locations = list({ev.get("location", "") for ev in evs[:10] if ev.get("location")})[:5]
        actors = list({ev.get("actor1", "") for ev in evs[:10] if ev.get("actor1")})[:3]

        date_range = ""
        dates = sorted(ev.get("event_date", "") for ev in evs if ev.get("event_date"))
        if dates:
            date_range = f"{dates[0]} to {dates[-1]}"

        summary = (
            f"{count} {event_type} event(s) in {country}. "
            f"Fatalities: {type_fatalities}. "
            f"Intensity signal: {intensity:.2f}. "
            f"Locations: {', '.join(locations)}. "
            f"Key actors: {', '.join(actors)}. "
            f"Period: {date_range}."
        )

        # Most recent event notes as raw context
        recent_notes = " | ".join(
            ev.get("notes", "")[:150] for ev in evs[:3] if ev.get("notes")
        )

        results.append(ResearchResult(
            source_type="acled",
            query=query,
            title=f"ACLED — {country}: {count}× {event_type}",
            summary=summary,
            url="https://acleddata.com/data-export-tool/",
            calibrates=calibrates,
            data={
                "event_type": event_type,
                "count": count,
                "fatalities": type_fatalities,
                "total_fatalities_all_types": total_fatalities,
                "intensity": intensity,
                "locations": locations,
                "actors": actors,
                "date_range": date_range,
                "country": country,
                "events_sample": evs[:5],
            },
            raw=recent_notes,
        ))

    return results
