"""
api/routers/theories.py — Theory catalog and recommendation endpoints

GET  /api/theories                      List all theories (filterable)
GET  /api/theories/{theory_id}          Full theory detail
POST /api/theories/recommend            Recommend theories for a scenario
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.catalog import DOMAIN_MAP, build_catalog, get_entry, invalidate_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/theories", tags=["theories"])


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("")
async def list_theories(
    domain: str | None = Query(default=None, description="Filter by domain (e.g. 'geopolitics', 'market')"),
    q: str | None = Query(default=None, description="Keyword search across name + description"),
    source: str | None = Query(default=None, description="Filter by source: 'builtin' or 'discovered'"),
) -> dict:
    """
    List all registered theories with optional filtering.

    - `domain`: restricts to theories whose DOMAINS list contains this value
    - `q`: case-insensitive keyword search across theory name and description
    - `source`: 'builtin' | 'discovered'
    """
    catalog = build_catalog()
    entries = catalog

    if domain:
        domain_lower = domain.lower()
        entries = [e for e in entries if domain_lower in [d.lower() for d in e.domains]]

    if q:
        q_lower = q.lower()
        entries = [
            e for e in entries
            if q_lower in e.name.lower() or q_lower in e.description.lower()
        ]

    if source:
        entries = [e for e in entries if e.source == source]

    return {
        "count":   len(entries),
        "filters": {"domain": domain, "q": q, "source": source},
        "theories": [e.to_summary_dict() for e in entries],
    }


@router.get("/recommend")
async def recommend_get() -> dict:
    """Usage hint — use POST for recommendations."""
    return {"detail": "Use POST /api/theories/recommend with a JSON body."}


@router.get("/{theory_id}")
async def get_theory_detail(theory_id: str) -> dict:
    """
    Full detail for a single theory: parameters table, env reads/writes,
    description, academic reference.
    """
    entry = get_entry(theory_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Theory '{theory_id}' not found")
    return entry.to_dict()


# ── Recommend ──────────────────────────────────────────────────────────────────

class RecommendRequest(BaseModel):
    domain: str
    description: str = ""
    max_results: int = 5
    use_claude: bool = True   # set False to get domain-match fast path only


@router.post("/recommend")
async def recommend_theories(body: RecommendRequest) -> dict:
    """
    Recommend theories for a scenario.

    Two-stage:
      1. Domain-match fast path — instant, no API cost, returns DOMAIN_MAP candidates
      2. Claude (claude-haiku) refinement — reranks and filters based on description
         (skipped if use_claude=False or ANTHROPIC_API_KEY not set)

    Returns:
        recommended: list of {theory_id, name, domains, description, reasoning, confidence}
    """
    catalog = build_catalog()
    catalog_index = {e.theory_id: e for e in catalog}

    # Stage 1: domain-match fast path
    domain_lower = body.domain.lower()
    candidate_ids = list(DOMAIN_MAP.get(domain_lower, []))

    # Broaden: also include any theory whose DOMAINS contains this domain
    for entry in catalog:
        if domain_lower in [d.lower() for d in entry.domains] and entry.theory_id not in candidate_ids:
            candidate_ids.append(entry.theory_id)

    # Resolve candidates (skip any IDs not in registry — e.g. stale DOMAIN_MAP entries)
    candidates = [catalog_index[tid] for tid in candidate_ids if tid in catalog_index]

    if not candidates:
        return {
            "domain":      body.domain,
            "stage":       "domain_match",
            "recommended": [],
            "message":     f"No theories found for domain '{body.domain}'. Available domains: {sorted(DOMAIN_MAP)}",
        }

    # Stage 2: Claude refinement
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not body.use_claude or not api_key or not body.description:
        # Fast-path only — return top max_results candidates with generic reasoning
        recs = [
            {
                "theory_id":   e.theory_id,
                "name":        e.name,
                "domains":     e.domains,
                "description": e.description[:200],
                "reasoning":   f"Standard {body.domain} theory.",
                "confidence":  0.7,
            }
            for e in candidates[:body.max_results]
        ]
        return {
            "domain":      body.domain,
            "stage":       "domain_match",
            "recommended": recs,
        }

    # Build catalog summary for Claude
    catalog_text = "\n".join(
        f"- {e.theory_id}: {e.name} | domains: {', '.join(e.domains)} | {e.description[:120]}"
        for e in candidates
    )

    prompt = f"""You are a theory selection assistant for a scenario simulation platform.

Scenario domain: {body.domain}
Scenario description: {body.description}

Candidate theories:
{catalog_text}

Select the {body.max_results} most relevant theories for this scenario. For each, provide:
- theory_id (exact, from the list)
- one-sentence reasoning explaining why it fits
- confidence score 0.0–1.0

Respond as a JSON array only, no prose:
[{{"theory_id": "...", "reasoning": "...", "confidence": 0.0}}, ...]"""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        text = response.content[0].text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = re.sub(r"```(?:json)?", "", text).strip().rstrip("```").strip()
        ranked = json.loads(text)

        recs = []
        for item in ranked[:body.max_results]:
            tid = item.get("theory_id", "")
            entry = catalog_index.get(tid)
            if entry is None:
                continue
            recs.append({
                "theory_id":   tid,
                "name":        entry.name,
                "domains":     entry.domains,
                "description": entry.description[:200],
                "reasoning":   item.get("reasoning", ""),
                "confidence":  float(item.get("confidence", 0.7)),
            })

        return {
            "domain":      body.domain,
            "stage":       "claude_refined",
            "recommended": recs,
        }

    except Exception as exc:
        logger.warning("Claude refinement failed (%s), falling back to domain-match", exc)
        # Fall back to domain-match result
        recs = [
            {
                "theory_id":   e.theory_id,
                "name":        e.name,
                "domains":     e.domains,
                "description": e.description[:200],
                "reasoning":   f"Standard {body.domain} theory (fast-path fallback).",
                "confidence":  0.65,
            }
            for e in candidates[:body.max_results]
        ]
        return {
            "domain":      body.domain,
            "stage":       "domain_match_fallback",
            "recommended": recs,
            "warning":     f"Claude refinement failed: {exc}",
        }


import re  # noqa: E402 (needed by recommend route above)
