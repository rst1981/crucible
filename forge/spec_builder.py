"""
forge/spec_builder.py — SpecBuilder

Translates free-text intake into a skeleton SimSpec, applies research hints,
handles user answers, and infers gaps when max turns is reached.

All LLM calls use claude-haiku-4-5-20251001 for cost efficiency.
Heavy reasoning stays in ScopingAgent (claude-sonnet / claude-opus).
"""
from __future__ import annotations

import json
import logging
from typing import Any, TYPE_CHECKING

from anthropic import Anthropic

from core.spec import SimSpec, ActorSpec, TimeframeSpec

if TYPE_CHECKING:
    from forge.session import SpecGap, ResearchContext

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"

_PARSE_SYSTEM = """
You are a simulation design assistant. Extract structured information from a
free-text scenario description and return a JSON object with these exact fields:

{
  "name": "short scenario name (< 60 chars)",
  "description": "1-2 sentence summary",
  "domain": "one of: geopolitics | conflict | market | macro | corporate | ecology | technology",
  "actors": [
    {
      "actor_id": "snake_case_id",
      "name": "Display Name",
      "role": "state | market | ngo | individual | other",
      "belief_state": {}
    }
  ],
  "timeframe": {
    "total_ticks": 24,
    "tick_unit": "month",
    "start_date": "YYYY-MM-DD"
  },
  "initial_environment": {
    "global__key": 0.5
  }
}

Rules:
- Use snake_case for actor_id
- Normalize all env values to [0, 1]
- Guess timeframe from context clues (e.g. "over the next two years" → 24 months)
- Include at least the 3-5 most obvious actors
- Return ONLY valid JSON, no commentary, no markdown fences
"""

_ANSWER_SYSTEM = """
You are a simulation spec updater. Given a list of open gaps and a user's answer,
extract any SimSpec updates and return JSON:

{
  "env_updates": {"env_key": 0.0_to_1.0},
  "timeframe_ticks": null_or_integer,
  "domain": null_or_string,
  "actor_updates": [{"actor_id": "...", "name": "...", "role": "..."}],
  "metadata_updates": {"outcome_focus": "plain text summary of desired outcomes and decision"},
  "gap_paths_filled": ["actors", "timeframe", "outcome_focus"]
}

Rules:
- All env values must be [0, 1] normalized
- gap_paths_filled lists field_path strings for gaps this answer resolves
- If the answer describes desired outcomes or what decision to inform, populate metadata_updates.outcome_focus
- Return ONLY valid JSON, no markdown fences
"""


class SpecBuilder:
    """
    Translates raw text and structured inputs into a SimSpec.
    Uses claude-haiku for all LLM calls (fast + cheap).
    """

    def __init__(self, client: Anthropic | None = None) -> None:
        self._client = client or Anthropic()

    # ── Public API ─────────────────────────────────────────────────────────

    def parse_intake(self, intake_text: str) -> SimSpec:
        """
        Call Claude haiku to parse free text into a skeleton SimSpec.
        Returns a minimal valid SimSpec — actors/env may be sparse.
        Falls back to a minimal skeleton on parse failure.
        """
        try:
            resp = self._client.messages.create(
                model=_MODEL,
                max_tokens=2048,
                system=_PARSE_SYSTEM,
                messages=[{"role": "user", "content": intake_text}],
            )
            raw = resp.content[0].text.strip()
            raw = _strip_fences(raw)
            data = json.loads(raw)
        except Exception as exc:
            logger.warning("parse_intake LLM call failed (%s); using skeleton", exc)
            data = _skeleton(intake_text)

        return _build_simspec(data)

    def apply_research_hints(
        self,
        simspec: SimSpec,
        research_context: "ResearchContext",
    ) -> None:
        """
        Merge parameter_estimates from research into initial_environment.
        Does not overwrite values already explicitly set.
        """
        env = dict(simspec.initial_environment)
        added = 0
        for key, value in research_context.parameter_estimates.items():
            if key not in env:
                env[key] = float(max(0.0, min(1.0, value)))
                added += 1
        if added:
            object.__setattr__(simspec, "initial_environment", env)
            logger.debug("apply_research_hints: added %d env keys from research", added)

    def apply_user_answer(
        self,
        simspec: SimSpec,
        gaps: "list[SpecGap]",
        answer: str,
    ) -> None:
        """
        Parse a user answer via Claude haiku and apply structural updates to the SimSpec.
        Also marks any resolved gaps as filled.
        """
        open_gap_text = "\n".join(
            f"- {g.field_path}: {g.description}"
            for g in gaps if not g.filled
        )
        if not open_gap_text:
            return

        prompt = (
            f"Open gaps:\n{open_gap_text}\n\n"
            f"User's answer: {answer}"
        )

        try:
            resp = self._client.messages.create(
                model=_MODEL,
                max_tokens=512,
                system=_ANSWER_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = _strip_fences(resp.content[0].text.strip())
            updates = json.loads(raw)
        except Exception as exc:
            logger.warning("apply_user_answer parse failed: %s", exc)
            return

        # env updates
        env_updates: dict[str, float] = updates.get("env_updates") or {}
        if env_updates:
            env = dict(simspec.initial_environment)
            for k, v in env_updates.items():
                env[k] = float(max(0.0, min(1.0, v)))
            object.__setattr__(simspec, "initial_environment", env)

        # timeframe
        ticks = updates.get("timeframe_ticks")
        if ticks and isinstance(ticks, int) and ticks > 0:
            object.__setattr__(simspec.timeframe, "total_ticks", ticks)
            _mark_gap_filled(gaps, "timeframe", answer)

        # domain
        domain = updates.get("domain")
        if domain:
            object.__setattr__(simspec, "domain", domain)
            _mark_gap_filled(gaps, "domain", answer)

        # actor updates
        for actor_data in updates.get("actor_updates") or []:
            _upsert_actor(simspec, actor_data, answer)
            _mark_gap_filled(gaps, "actors", answer)

        # metadata updates (e.g. outcome_focus)
        metadata_updates: dict = updates.get("metadata_updates") or {}
        if metadata_updates:
            meta = dict(simspec.metadata)
            meta.update(metadata_updates)
            object.__setattr__(simspec, "metadata", meta)
            if metadata_updates.get("outcome_focus"):
                _mark_gap_filled(gaps, "outcome_focus", answer)

        # explicit gap_paths_filled
        for path in updates.get("gap_paths_filled") or []:
            _mark_gap_filled(gaps, path, answer)

    def infer_gap(
        self,
        simspec: SimSpec,
        gap: "SpecGap",
        research_context: "ResearchContext",
    ) -> None:
        """
        Auto-fill a gap using research context + reasonable defaults.
        Called when max_turns is reached and gaps remain open.
        """
        if gap.field_path == "timeframe" and simspec.timeframe.total_ticks == 0:
            object.__setattr__(simspec.timeframe, "total_ticks", 24)
            logger.debug("infer_gap: timeframe defaulted to 24 ticks")

        elif gap.field_path == "domain" and not simspec.domain:
            # infer from theory_candidates if available
            candidates = research_context.theory_candidates
            domain = "geopolitics" if any(
                "richard" in c or "fearon" in c or "conflict" in c
                for c in candidates
            ) else "market" if any(
                "porter" in c or "market" in c
                for c in candidates
            ) else "macro"
            object.__setattr__(simspec, "domain", domain)
            logger.debug("infer_gap: domain inferred as %s", domain)

        elif gap.field_path == "initial_environment" and not simspec.initial_environment:
            # seed a minimal environment from research parameter estimates
            env = {
                k: v for k, v in research_context.parameter_estimates.items()
            }
            if not env:
                env = {"global__stress": 0.3}
            object.__setattr__(simspec, "initial_environment", env)
            logger.debug("infer_gap: initial_environment seeded with %d keys", len(env))


# ── Helpers ────────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1]
        elif len(parts) == 2:
            text = parts[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def _skeleton(intake_text: str) -> dict[str, Any]:
    """Minimal skeleton when LLM parse fails."""
    return {
        "name":        intake_text[:60],
        "description": intake_text,
        "domain":      "",
        "actors":      [],
        "timeframe":   {"total_ticks": 0, "tick_unit": "month", "start_date": "2025-01-01"},
        "initial_environment": {},
    }


def _build_simspec(data: dict[str, Any]) -> SimSpec:
    """Build a SimSpec from parsed dict, handling missing fields gracefully."""
    actors = [
        ActorSpec(
            actor_id=a.get("actor_id", f"actor_{i}"),
            name=a.get("name", f"Actor {i}"),
            role=a.get("role", "other"),
            belief_state=a.get("belief_state") or {},
        )
        for i, a in enumerate(data.get("actors") or [])
    ]

    tf = data.get("timeframe") or {}
    timeframe = TimeframeSpec(
        total_ticks=tf.get("total_ticks", 0),
        tick_unit=tf.get("tick_unit", "month"),
        start_date=tf.get("start_date", "2025-01-01"),
    )

    env: dict[str, float] = {}
    for k, v in (data.get("initial_environment") or {}).items():
        try:
            env[k] = float(max(0.0, min(1.0, v)))
        except (TypeError, ValueError):
            pass

    return SimSpec(
        name=data.get("name") or data.get("description", "Unnamed Scenario")[:60],
        description=data.get("description", ""),
        domain=data.get("domain", ""),
        actors=actors,
        timeframe=timeframe,
        initial_environment=env,
    )


def _mark_gap_filled(gaps: "list[SpecGap]", path: str, answer: str) -> None:
    for gap in gaps:
        if gap.field_path == path and not gap.filled:
            gap.filled = True
            gap.filled_by = "user"
            gap.answer_received = answer
            return


def _upsert_actor(simspec: SimSpec, actor_data: dict[str, Any], answer: str) -> None:
    actor_id = actor_data.get("actor_id", "")
    existing = next((a for a in simspec.actors if a.actor_id == actor_id), None)
    if existing:
        return  # already present, don't overwrite
    new_actor = ActorSpec(
        actor_id=actor_id or f"actor_{len(simspec.actors)}",
        name=actor_data.get("name", actor_id),
        role=actor_data.get("role", "other"),
        belief_state=actor_data.get("belief_state") or {},
    )
    simspec.actors.append(new_actor)
