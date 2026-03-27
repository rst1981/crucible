"""
Hormuz Scenario — Simulation Runner
Strait of Hormuz 2025 Escalation & Resolution

Usage:
    python scenarios/hormuz/run_simulation.py
    python scenarios/hormuz/run_simulation.py --ticks 10   # smoke test
    python scenarios/hormuz/run_simulation.py --seed 42

Output:
    scenarios/hormuz/results.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.spec import (
    ActorSpec, BeliefSpec, BeliefDistType, CapabilitySpec, DesireSpec,
    OutcomeMetricSpec, SimSpec, TheoryRef, TimeframeSpec, UncertaintySpec,
)
from core.sim_runner import SimRunner
from scenarios.hormuz.params import (
    SCENARIO_ID, TITLE, DOMAIN, TICK_UNIT, TOTAL_TICKS, START_DATE,
    RICHARDSON, FEARON, WITTMAN_ZARTMAN, SIR_ECONOMIC, KEYNESIAN, PORTER,
    INITIAL_ENV, SHOCKS, METRICS,
)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

_OUT = Path(__file__).parent / "results.json"


# ── Actor definitions ─────────────────────────────────────────────────────────

def _state_actor(
    actor_id: str,
    name: str,
    military_readiness: float,
    economic_pressure: float = 0.3,
    resolve: float = 0.6,
    obs_noise: float = 0.03,
) -> ActorSpec:
    """Build a state actor (military + economic beliefs, escalate/negotiate desires)."""
    return ActorSpec(
        actor_id=actor_id,
        name=name,
        agent_class="core.agents.base.DefaultBDIAgent",
        observation_noise_sigma=obs_noise,
        beliefs=[
            BeliefSpec(
                name="adversary_resolve",
                dist_type=BeliefDistType.BETA,
                alpha=resolve * 10, beta=(1 - resolve) * 10,
                decay_rate=0.97,
                maps_to_env_key="fearon__win_prob_a",
            ),
            BeliefSpec(
                name="own_military",
                dist_type=BeliefDistType.BETA,
                alpha=military_readiness * 10, beta=(1 - military_readiness) * 10,
                decay_rate=0.99,
                maps_to_env_key=f"{actor_id}__military_readiness",
            ),
            BeliefSpec(
                name="economic_stress",
                dist_type=BeliefDistType.GAUSSIAN,
                mean=economic_pressure, variance=0.05,
                process_noise=0.01,
                maps_to_env_key="global__economic_stress",
            ),
        ],
        desires=[
            DesireSpec(
                name="minimize_disruption",
                target_env_key="strait__shipping_disruption",
                direction=-1.0, weight=0.8,
            ),
            DesireSpec(
                name="maximize_negotiation",
                target_env_key="global__negotiation_progress",
                direction=1.0, weight=0.6,
            ),
        ],
        capabilities=[
            CapabilitySpec(
                name="diplomatic",
                capacity=1.0, cost=0.15, recovery_rate=0.10, cooldown_ticks=1,
            ),
        ],
        initial_env_contributions={
            f"{actor_id}__military_readiness": military_readiness,
        },
    )


def _importer_actor(actor_id: str, name: str, oil_dependency: float = 0.6) -> ActorSpec:
    """Build an oil-importing state actor (economic vulnerability focus)."""
    return ActorSpec(
        actor_id=actor_id,
        name=name,
        agent_class="core.agents.base.DefaultBDIAgent",
        observation_noise_sigma=0.04,
        beliefs=[
            BeliefSpec(
                name="oil_price_stress",
                dist_type=BeliefDistType.GAUSSIAN,
                mean=oil_dependency, variance=0.08,
                process_noise=0.02,
                maps_to_env_key="global__oil_price",
            ),
            BeliefSpec(
                name="supply_security",
                dist_type=BeliefDistType.BETA,
                alpha=(1 - oil_dependency) * 8, beta=oil_dependency * 8,
                decay_rate=0.98,
                maps_to_env_key="global__trade_volume",
            ),
        ],
        desires=[
            DesireSpec(
                name="oil_supply_stability",
                target_env_key="global__trade_volume",
                direction=1.0, weight=0.9,
            ),
            DesireSpec(
                name="price_stability",
                target_env_key="global__oil_price",
                direction=-1.0, weight=0.7,
            ),
        ],
        capabilities=[
            CapabilitySpec(
                name="strategic_reserve",
                capacity=1.0, cost=0.20, recovery_rate=0.05, cooldown_ticks=2,
            ),
        ],
    )


def _commercial_actor(
    actor_id: str, name: str, risk_tolerance: float = 0.4
) -> ActorSpec:
    """Build a commercial actor (shipping, insurance, trading)."""
    return ActorSpec(
        actor_id=actor_id,
        name=name,
        agent_class="core.agents.base.DefaultBDIAgent",
        observation_noise_sigma=0.05,
        beliefs=[
            BeliefSpec(
                name="route_risk",
                dist_type=BeliefDistType.BETA,
                alpha=risk_tolerance * 6, beta=(1 - risk_tolerance) * 6,
                decay_rate=0.96,
                maps_to_env_key="strait__shipping_disruption",
            ),
        ],
        desires=[
            DesireSpec(
                name="minimize_route_risk",
                target_env_key="strait__shipping_disruption",
                direction=-1.0, weight=1.0,
            ),
            DesireSpec(
                name="trade_volume",
                target_env_key="global__trade_volume",
                direction=1.0, weight=0.8,
            ),
        ],
        capabilities=[
            CapabilitySpec(
                name="reroute",
                capacity=1.0, cost=0.25, recovery_rate=0.08, cooldown_ticks=2,
            ),
        ],
    )


def _build_actors() -> list[ActorSpec]:
    return [
        # ── State actors — primary belligerents
        _state_actor("iran",          "Iran",          military_readiness=0.62, economic_pressure=0.75, resolve=0.70, obs_noise=0.05),
        _state_actor("us",            "United States", military_readiness=0.78, economic_pressure=0.15, resolve=0.65, obs_noise=0.02),

        # ── State actors — Gulf states
        _state_actor("saudi_arabia",  "Saudi Arabia",  military_readiness=0.55, economic_pressure=0.20, resolve=0.50, obs_noise=0.03),
        _state_actor("uae",           "UAE",           military_readiness=0.45, economic_pressure=0.18, resolve=0.45, obs_noise=0.03),
        _state_actor("qatar",         "Qatar",         military_readiness=0.35, economic_pressure=0.20, resolve=0.40, obs_noise=0.04),
        _state_actor("kuwait",        "Kuwait",        military_readiness=0.30, economic_pressure=0.22, resolve=0.35, obs_noise=0.04),

        # ── Western allies
        _state_actor("united_kingdom","United Kingdom",military_readiness=0.40, economic_pressure=0.25, resolve=0.55, obs_noise=0.03),

        # ── Great power observers
        _state_actor("russia",        "Russia",        military_readiness=0.70, economic_pressure=0.45, resolve=0.60, obs_noise=0.05),
        _state_actor("china",         "China",         military_readiness=0.65, economic_pressure=0.20, resolve=0.55, obs_noise=0.04),

        # ── Oil-importing states
        _importer_actor("japan",       "Japan",       oil_dependency=0.85),
        _importer_actor("south_korea", "South Korea", oil_dependency=0.80),
        _importer_actor("india",       "India",       oil_dependency=0.65),

        # ── OPEC / cartel
        ActorSpec(
            actor_id="opec", name="OPEC",
            agent_class="core.agents.base.DefaultBDIAgent",
            observation_noise_sigma=0.03,
            beliefs=[
                BeliefSpec(
                    name="price_target",
                    dist_type=BeliefDistType.GAUSSIAN,
                    mean=0.65, variance=0.05, process_noise=0.01,
                    maps_to_env_key="global__oil_price",
                ),
            ],
            desires=[
                DesireSpec(name="price_floor", target_env_key="global__oil_price", direction=1.0, weight=1.0),
            ],
            capabilities=[
                CapabilitySpec(name="production_cut", capacity=1.0, cost=0.30, recovery_rate=0.10, cooldown_ticks=3),
            ],
        ),

        # ── Commercial actors
        _commercial_actor("oil_majors",        "Oil Majors",        risk_tolerance=0.35),
        _commercial_actor("tanker_operators",  "Tanker Operators",  risk_tolerance=0.30),
        _commercial_actor("marine_insurers",   "Marine Insurers",   risk_tolerance=0.25),
        _commercial_actor("commodity_traders", "Commodity Traders", risk_tolerance=0.45),
        _commercial_actor("shipping_logistics","Shipping & Logistics", risk_tolerance=0.30),
    ]


# ── Theory stack ──────────────────────────────────────────────────────────────

def _build_theories() -> list[TheoryRef]:
    return [
        TheoryRef(theory_id="richardson_arms_race", priority=0, parameters=RICHARDSON),
        TheoryRef(theory_id="fearon_bargaining",    priority=1, parameters=FEARON),
        TheoryRef(theory_id="wittman_zartman",      priority=2, parameters=WITTMAN_ZARTMAN),
        TheoryRef(theory_id="sir_contagion",        priority=3, parameters=SIR_ECONOMIC),
        TheoryRef(theory_id="keynesian_multiplier", priority=4, parameters=KEYNESIAN),
        TheoryRef(theory_id="porter_five_forces",   priority=5, parameters=PORTER),
    ]


# ── Metrics ───────────────────────────────────────────────────────────────────

def _build_metrics() -> list[OutcomeMetricSpec]:
    return [
        OutcomeMetricSpec(
            name=m["name"],
            env_key=m["env_key"],
            snapshot_threshold=m.get("snapshot_threshold"),
            snapshot_direction=m.get("snapshot_direction", 1.0),
        )
        for m in METRICS
    ]


# ── SimSpec ───────────────────────────────────────────────────────────────────

def build_spec(total_ticks: int = TOTAL_TICKS) -> SimSpec:
    return SimSpec(
        name=TITLE,
        description=(
            "Models military escalation and economic disruption in the Strait of Hormuz "
            "following an Iranian navigation restriction, international coalition response, "
            "and eventual Oman-mediated negotiation. 18 actors across state, economic, and "
            "commercial categories. Theory cascade: Richardson (arms race) → Fearon (conflict "
            "probability) → Wittman-Zartman (ripeness/negotiation) → SIR (economic contagion) "
            "→ Keynesian (GDP impact) → Porter (shipping industry)."
        ),
        domain=DOMAIN,
        actors=_build_actors(),
        theories=_build_theories(),
        timeframe=TimeframeSpec(
            total_ticks=total_ticks,
            tick_unit=TICK_UNIT,
            start_date=START_DATE,
        ),
        uncertainty=UncertaintySpec(
            observation_noise_sigma=0.02,
            shock_probability=0.00,   # all shocks are scheduled
            shock_magnitude=0.0,
            scheduled_shocks={
                k: v for k, v in SHOCKS.items() if k < total_ticks
            },
        ),
        metrics=_build_metrics(),
        initial_environment=INITIAL_ENV,
    )


# ── Runner ────────────────────────────────────────────────────────────────────

def run(total_ticks: int = TOTAL_TICKS, seed: int = 0) -> dict:
    spec = build_spec(total_ticks=total_ticks)
    runner = SimRunner(spec, rng_seed=seed)
    runner.setup()
    runner.run()

    # Serialize series
    series: dict[str, list[dict]] = {}
    for rec in runner.metric_history:
        series.setdefault(rec.env_key, []).append(
            {"tick": rec.tick, "value": rec.value}
        )

    results = {
        "scenario_id": SCENARIO_ID,
        "total_ticks": total_ticks,
        "tick_unit": TICK_UNIT,
        "n_actors": len(spec.actors),
        "n_theories": len(spec.theories),
        "series": series,
        "final_env": runner.get_current_env(),
        "snapshots": [
            {
                "tick": s.tick,
                "label": s.label,
                "env": s.env,
            }
            for s in runner.snapshots
        ],
    }
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Hormuz scenario simulation")
    parser.add_argument("--ticks", type=int, default=TOTAL_TICKS)
    parser.add_argument("--seed",  type=int, default=0)
    parser.add_argument("--out",   type=str, default=str(_OUT))
    args = parser.parse_args()

    logger.warning("Running Hormuz simulation: %d ticks, seed=%d", args.ticks, args.seed)
    results = run(total_ticks=args.ticks, seed=args.seed)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"Results saved to {out_path}")
    print(f"Actors: {results['n_actors']}  Theories: {results['n_theories']}  Ticks: {results['total_ticks']}")


if __name__ == "__main__":
    main()
