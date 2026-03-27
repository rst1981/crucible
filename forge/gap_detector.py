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
            description="Simulation timeframe not set — how long should the scenario run?",
            priority=0.80,
        ))

    if not simspec.theories:
        gaps.append(SpecGap(
            field_path="theories",
            description="No theory modules selected — theory mapping will handle this automatically.",
            priority=0.50,  # low: theory mapper handles this after interview
        ))

    if not simspec.metrics:
        gaps.append(SpecGap(
            field_path="metrics",
            description="No outcome metrics defined — what should we track and report?",
            priority=0.40,
        ))

    return gaps


def _merge_gaps(existing: list[SpecGap], new_gaps: list[SpecGap]) -> None:
    """
    Add any new gaps not already tracked. Does not duplicate.
    Mutates `existing` in place.
    """
    existing_paths = {g.field_path for g in existing if not g.filled}
    for gap in new_gaps:
        if gap.field_path not in existing_paths:
            existing.append(gap)
