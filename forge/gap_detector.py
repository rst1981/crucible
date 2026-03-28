"""
forge/gap_detector.py — SimSpec gap detection

Inspects a (possibly partial) SimSpec and returns a list of SpecGap
for anything missing or under-specified. Called after parse_intake and
after each user answer to keep the gap list current.
"""
from __future__ import annotations

from core.spec import SimSpec
from forge.session import SpecGap


def detect_gaps(simspec: SimSpec) -> list[SpecGap]:
    """
    Return a list of SpecGap for missing or under-specified fields.
    Ordered with highest priority first.
    """
    gaps: list[SpecGap] = []

    # Outcome focus is always required — research can never fill this.
    # The consultant must state what decision this simulation should inform
    # and what outcomes they want to surface.
    if not simspec.metadata.get("outcome_focus"):
        gaps.append(SpecGap(
            field_path="outcome_focus",
            description=(
                "What are the 1–3 outcomes this simulation should surface, "
                "and what specific decision should it inform?"
            ),
            priority=0.99,
        ))

    # Theories — ask to give the client agency over theoretical framing.
    # Always offer "let the model decide empirically" as the default option.
    # Suppressed if: theories already set, OR user chose empirical mode.
    if not simspec.theories and not simspec.metadata.get("theories_mode"):
        gaps.append(SpecGap(
            field_path="theories",
            description=(
                "Should this simulation apply a specific theoretical framework, "
                "or let the model select theories empirically from research?"
            ),
            priority=0.50,
        ))

    if not simspec.domain:
        gaps.append(SpecGap(
            field_path="domain",
            description="Scenario domain not identified (geopolitics, market, macro, corporate, etc.)",
            priority=1.0,
        ))

    if not simspec.actors:
        gaps.append(SpecGap(
            field_path="actors",
            description="No actors defined — who are the key decision-makers in this scenario?",
            priority=0.95,
        ))

    if not simspec.initial_environment:
        gaps.append(SpecGap(
            field_path="initial_environment",
            description="No initial conditions set — what is the baseline state of the system?",
            priority=0.90,
        ))

    if simspec.timeframe.total_ticks == 0:
        gaps.append(SpecGap(
            field_path="timeframe",
            description=(
                "What timeframe should this simulation cover — "
                "how many months or years, and from what start date?"
            ),
            priority=0.70,
        ))

    return gaps


def _merge_gaps(existing: list[SpecGap], new_gaps: list[SpecGap]) -> None:
    """
    Add any new gaps not already tracked. Does not duplicate.
    Mutates `existing` in place.
    """
    existing_paths = {g.field_path for g in existing}  # include filled — never re-add
    for gap in new_gaps:
        if gap.field_path not in existing_paths:
            existing.append(gap)
