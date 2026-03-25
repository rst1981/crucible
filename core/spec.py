from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ── Belief distribution types ───────────────────────────────────────────────

class BeliefDistType(str, Enum):
    BETA     = "beta"      # probability beliefs (0–1), e.g. "P(actor cooperates)"
    GAUSSIAN = "gaussian"  # continuous beliefs, e.g. "estimated GDP growth"
    POINT    = "point"     # known value, no uncertainty


class BeliefSpec(BaseModel):
    belief_id:   str            = Field(default_factory=lambda: str(uuid.uuid4()))
    name:        str
    description: str            = ""
    dist_type:   BeliefDistType = BeliefDistType.BETA
    # BETA: initial alpha and beta (both > 0)
    alpha:       float          = 1.0
    beta:        float          = 1.0
    # GAUSSIAN: initial mean and variance
    mean:        float          = 0.0
    variance:    float          = 1.0
    # POINT: fixed value
    value:       float          = 0.0
    # which env key this belief tracks (if different from belief name)
    maps_to_env_key: str | None = None


# ── Desires / objectives ────────────────────────────────────────────────────

class DesireSpec(BaseModel):
    desire_id:      str   = Field(default_factory=lambda: str(uuid.uuid4()))
    name:           str
    description:    str   = ""
    # environment key this desire targets
    target_env_key: str
    # direction: +1 = maximize, -1 = minimize
    direction:      float = 1.0
    # salience weight (0–1) — how much this desire drives behavior
    weight:         float = 1.0


# ── Capabilities ────────────────────────────────────────────────────────────

class CapabilitySpec(BaseModel):
    capability_id: str   = Field(default_factory=lambda: str(uuid.uuid4()))
    name:          str
    description:   str   = ""
    # max capacity units
    capacity:      float = 1.0
    # units consumed per use
    cost:          float = 0.1
    # recovery rate per tick
    recovery_rate: float = 0.05
    # cooldown ticks after use
    cooldown_ticks: int  = 0


# ── Actors ──────────────────────────────────────────────────────────────────

class ActorSpec(BaseModel):
    actor_id:    str  = Field(default_factory=lambda: str(uuid.uuid4()))
    name:        str
    description: str  = ""
    # fully-qualified agent class, e.g. "scenarios.hormuz.agents.IranAgent"
    agent_class: str  = "core.agents.base.BDIAgent"
    beliefs:      list[BeliefSpec]      = Field(default_factory=list)
    desires:      list[DesireSpec]      = Field(default_factory=list)
    capabilities: list[CapabilitySpec]  = Field(default_factory=list)
    # initial environment keys this actor owns
    # e.g. {"iran__military_readiness": 0.7, "iran__oil_revenue": 0.4}
    initial_env_contributions: dict[str, float] = Field(default_factory=dict)
    # arbitrary scenario-specific metadata
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Timeframe ───────────────────────────────────────────────────────────────

class TimeframeSpec(BaseModel):
    total_ticks: int      = 365
    tick_unit:   str      = "day"  # "hour", "day", "week", "month", "quarter", "year"
    # real-world anchor date (ISO 8601), optional
    start_date:  str | None = None


# ── Uncertainty ─────────────────────────────────────────────────────────────

class UncertaintySpec(BaseModel):
    # global observation noise applied to all env readings by agents
    observation_noise_sigma: float = 0.02
    # probability of an external shock per tick (0–1)
    shock_probability:       float = 0.01
    # max magnitude of a random shock to any single env key
    shock_magnitude:         float = 0.1
    # optional named shocks: {tick: {env_key: delta}}
    scheduled_shocks: dict[int, dict[str, float]] = Field(default_factory=dict)


# ── Outcome metrics ─────────────────────────────────────────────────────────

class OutcomeMetricSpec(BaseModel):
    metric_id:   str        = Field(default_factory=lambda: str(uuid.uuid4()))
    name:        str
    description: str        = ""
    # environment key to track
    env_key:     str
    # optional threshold that triggers a named snapshot when crossed
    snapshot_threshold: float | None = None
    snapshot_direction: float        = 1.0  # +1 = above threshold, -1 = below


# ── Research sources ────────────────────────────────────────────────────────

class ResearchSourceSpec(BaseModel):
    source_id:   str  = Field(default_factory=lambda: str(uuid.uuid4()))
    source_type: str  # "arxiv", "ssrn", "fred", "world_bank", "news"
    query:       str
    # calibration target: which env key this source informs
    calibrates:    str | None        = None
    # raw data snapshot (filled by research pipeline)
    data_snapshot: dict[str, Any]    = Field(default_factory=dict)


# ── Theory references ───────────────────────────────────────────────────────

class TheoryRef(BaseModel):
    theory_id:  str            # matches registry key, e.g. "richardson_arms_race"
    priority:   int            = 0  # lower = runs first in tick loop
    parameters: dict[str, float] = Field(default_factory=dict)


# ── Display annotations for env keys ───────────────────────────────────────

class EnvKeySpec(BaseModel):
    """
    Display metadata for a normalized environment key.
    SimRunner operates on the normalized float [0, 1].
    API and NarrativeAgent use display_value = normalized * scale.
    """
    key:          str   # matches a key in initial_environment
    scale:        float = 1.0   # multiply normalized to get display value
    unit:         str   = ""    # "USD", "billion USD", "% of GDP", "index", "bbl"
    display_name: str   = ""    # human-readable label: "Iranian Military Readiness"
    # optional: log-scale display (e.g. for GDP values)
    log_scale:    bool  = False


# ── SimSpec (root) ──────────────────────────────────────────────────────────

class SimSpec(BaseModel):
    spec_id:     str = Field(default_factory=lambda: str(uuid.uuid4()))
    name:        str
    description: str = ""
    domain:      str = ""  # "geopolitics", "market", "macro", etc.

    actors:           list[ActorSpec]          = Field(default_factory=list)
    theories:         list[TheoryRef]          = Field(default_factory=list)
    timeframe:        TimeframeSpec            = Field(default_factory=TimeframeSpec)
    uncertainty:      UncertaintySpec          = Field(default_factory=UncertaintySpec)
    metrics:          list[OutcomeMetricSpec]  = Field(default_factory=list)
    research_sources: list[ResearchSourceSpec] = Field(default_factory=list)
    env_key_specs:    list[EnvKeySpec]         = Field(default_factory=list)

    # global environment seed values (all floats — no nested objects)
    # key convention: "{theory_id}__{var}", "{actor_id}__{var}", "global__{var}"
    initial_environment: dict[str, float]  = Field(default_factory=dict)

    # arbitrary metadata for the scoping agent to attach
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def actor_ids_unique(self) -> "SimSpec":
        ids = [a.actor_id for a in self.actors]
        if len(ids) != len(set(ids)):
            raise ValueError("actor_ids must be unique")
        return self

    @model_validator(mode="after")
    def metric_env_keys_exist(self) -> "SimSpec":
        env_keys = set(self.initial_environment.keys())
        for metric in self.metrics:
            if metric.env_key not in env_keys:
                raise ValueError(
                    f"OutcomeMetric '{metric.name}' references env_key "
                    f"'{metric.env_key}' which is not in initial_environment"
                )
        return self

    def display_env(self, normalized: dict[str, float]) -> dict[str, Any]:
        """
        Convert a normalized env dict to display values.
        Keys without an EnvKeySpec are returned as-is (normalized == display).
        Engine always stays in [0, 1]; this is called only at the API / report layer.
        """
        index = {s.key: s for s in self.env_key_specs}
        out: dict[str, Any] = {}
        for k, v in normalized.items():
            spec = index.get(k)
            if spec:
                out[k] = {
                    "normalized":   v,
                    "display":      v * spec.scale,
                    "unit":         spec.unit,
                    "display_name": spec.display_name or k,
                }
            else:
                out[k] = {"normalized": v, "display": v, "unit": "", "display_name": k}
        return out


# ── SpecDiff ────────────────────────────────────────────────────────────────

@dataclass
class SpecDiff:
    """One changed field between two SimSpec versions."""
    field_path: str
    old_value:  Any
    new_value:  Any


# ── Version helpers ─────────────────────────────────────────────────────────

def diff_simspecs(v1: SimSpec, v2: SimSpec) -> list[SpecDiff]:
    """
    Compare two SimSpec instances field by field.
    Returns list[SpecDiff] — changes from v1 to v2.

    Checks:
    - initial_environment: per-key value changes
    - actors: added/removed (by actor_id)
    - theories: added/removed, changed parameters
    - timeframe: field-level diffs
    - env_key_specs: added/removed annotations
    """
    diffs: list[SpecDiff] = []

    # Environment diffs
    env1, env2 = v1.initial_environment, v2.initial_environment
    for key in set(env1) | set(env2):
        old = env1.get(key)
        new = env2.get(key)
        if old != new:
            diffs.append(SpecDiff(
                field_path=f"initial_environment.{key}",
                old_value=old,
                new_value=new,
            ))

    # Theory parameter diffs
    t1 = {t.theory_id: t for t in v1.theories}
    t2 = {t.theory_id: t for t in v2.theories}
    for tid in set(t1) | set(t2):
        if tid not in t1:
            diffs.append(SpecDiff(f"theories.{tid}", None, t2[tid].model_dump()))
        elif tid not in t2:
            diffs.append(SpecDiff(f"theories.{tid}", t1[tid].model_dump(), None))
        else:
            for param, val in t2[tid].parameters.items():
                old_val = t1[tid].parameters.get(param)
                if old_val != val:
                    diffs.append(SpecDiff(
                        f"theories.{tid}.parameters.{param}", old_val, val
                    ))

    # Timeframe diffs
    for field in ("total_ticks", "tick_unit", "start_date"):
        old = getattr(v1.timeframe, field)
        new = getattr(v2.timeframe, field)
        if old != new:
            diffs.append(SpecDiff(f"timeframe.{field}", old, new))

    # Actor diffs (presence only — deep diff is handled per-actor downstream)
    a1 = {a.actor_id for a in v1.actors}
    a2 = {a.actor_id for a in v2.actors}
    for aid in a1 - a2:
        diffs.append(SpecDiff(f"actors.{aid}", "present", None))
    for aid in a2 - a1:
        diffs.append(SpecDiff(f"actors.{aid}", None, "present"))

    return diffs


def branch_simspec(
    base: SimSpec,
    branch_name: str,
    change_reason: str = "",
) -> SimSpec:
    """
    Create a new SimSpec branched from base.
    Assigns a new spec_id. The parent_spec_id relationship is recorded in the
    database (sim_specs.parent_spec_id), not on SimSpec itself.
    """
    return base.model_copy(update={
        "spec_id":     str(uuid.uuid4()),
        "name":        f"{base.name} — {branch_name}",
        "description": f"Branch of '{base.name}': {change_reason}",
    })
