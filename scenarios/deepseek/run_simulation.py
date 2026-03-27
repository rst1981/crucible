"""
DeepSeek R1 / NVIDIA AI Infrastructure Shock — Simulation Runner
Jan 2025 – Jun 2026 (18 monthly ticks)

Usage:
    python scenarios/deepseek/run_simulation.py
    python scenarios/deepseek/run_simulation.py --ticks 5    # smoke test
    python scenarios/deepseek/run_simulation.py --seed 42
    python scenarios/deepseek/run_simulation.py --no-mc      # deterministic only

Output:
    scenarios/deepseek/results.json  (v2 format: deterministic + monte_carlo)
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.spec import (
    ActorSpec, BeliefSpec, BeliefDistType, CapabilitySpec, DesireSpec,
    OutcomeMetricSpec, SimSpec, TheoryRef, TimeframeSpec, UncertaintySpec,
)
from core.sim_runner import SimRunner
from scenarios.deepseek.params import (
    SCENARIO_ID, TITLE, DOMAIN, TICK_UNIT, TOTAL_TICKS, START_DATE,
    PLATFORM_TIPPING, COMPUTE_EFFICIENCY, NARRATIVE_CONTAGION,
    SCHUMPETER, FISHER_PRY, MINSKY, OPINION, PORTER, BASS,
    INITIAL_ENV, SHOCKS, METRICS,
)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

_OUT = Path(__file__).parent / "results.json"

# ── MC configuration ──────────────────────────────────────────────────────────

MC_RUNS = 300
MC_SCENARIO_WEIGHTS = {"base": 0.55, "bull": 0.25, "bear": 0.20}


# ── Actor definitions ─────────────────────────────────────────────────────────

def _market_actor(
    actor_id: str,
    name: str,
    platform_belief: float = 0.87,
    sentiment: float = 0.65,
    obs_noise: float = 0.04,
) -> ActorSpec:
    """Build a market participant actor."""
    return ActorSpec(
        actor_id=actor_id,
        name=name,
        agent_class="core.agents.base.DefaultBDIAgent",
        observation_noise_sigma=obs_noise,
        beliefs=[
            BeliefSpec(
                name="platform_dominance",
                dist_type=BeliefDistType.BETA,
                alpha=platform_belief * 10,
                beta=(1 - platform_belief) * 10,
                decay_rate=0.97,
                maps_to_env_key="platform_tipping__incumbent_share",
            ),
            BeliefSpec(
                name="market_sentiment",
                dist_type=BeliefDistType.GAUSSIAN,
                mean=sentiment,
                variance=0.08,
                process_noise=0.02,
                maps_to_env_key="opinion__mean",
            ),
        ],
        desires=[
            DesireSpec(
                name="maximize_returns",
                target_env_key="event__cumulative_ar",
                direction=1.0,
                weight=0.9,
            ),
            DesireSpec(
                name="minimize_fragility",
                target_env_key="minsky__financial_fragility",
                direction=-1.0,
                weight=0.7,
            ),
        ],
        capabilities=[
            CapabilitySpec(
                name="position_adjustment",
                capacity=1.0,
                cost=0.10,
                recovery_rate=0.15,
                cooldown_ticks=1,
            ),
        ],
    )


def _tech_actor(
    actor_id: str,
    name: str,
    cuda_dependency: float = 0.70,
    innovation_rate: float = 0.10,
    obs_noise: float = 0.03,
) -> ActorSpec:
    """Build a technology actor (hyperscaler, AI lab)."""
    return ActorSpec(
        actor_id=actor_id,
        name=name,
        agent_class="core.agents.base.DefaultBDIAgent",
        observation_noise_sigma=obs_noise,
        beliefs=[
            BeliefSpec(
                name="efficiency_trajectory",
                dist_type=BeliefDistType.GAUSSIAN,
                mean=0.20,
                variance=0.05,
                process_noise=0.02,
                maps_to_env_key="compute_efficiency__efficiency_gain",
            ),
            BeliefSpec(
                name="platform_lock_in",
                dist_type=BeliefDistType.BETA,
                alpha=cuda_dependency * 8,
                beta=(1 - cuda_dependency) * 8,
                decay_rate=0.98,
                maps_to_env_key="platform_tipping__incumbent_share",
            ),
        ],
        desires=[
            DesireSpec(
                name="reduce_compute_costs",
                target_env_key="compute_efficiency__entry_barrier",
                direction=-1.0,
                weight=0.85,
            ),
            DesireSpec(
                name="maintain_ai_capability",
                target_env_key="fisher__new_tech_share",
                direction=1.0,
                weight=0.70,
            ),
        ],
        capabilities=[
            CapabilitySpec(
                name="capex_deployment",
                capacity=1.0,
                cost=0.20,
                recovery_rate=0.05,
                cooldown_ticks=2,
            ),
            CapabilitySpec(
                name="custom_silicon",
                capacity=innovation_rate,
                cost=0.35,
                recovery_rate=0.03,
                cooldown_ticks=3,
            ),
        ],
        initial_env_contributions={
            "schumpeter__rd_investment": innovation_rate,
        },
    )


def _build_actors() -> list[ActorSpec]:
    return [
        # Platform incumbent
        _tech_actor("nvidia",   "NVIDIA",           cuda_dependency=0.95, innovation_rate=0.85, obs_noise=0.02),
        # Disruptor
        _tech_actor("deepseek", "DeepSeek / Chinese Labs", cuda_dependency=0.15, innovation_rate=0.90, obs_noise=0.06),
        # Hyperscalers (major CUDA customers + custom silicon builders)
        _tech_actor("microsoft","Microsoft / Azure", cuda_dependency=0.75, innovation_rate=0.40, obs_noise=0.03),
        _tech_actor("google",   "Google / GCP",      cuda_dependency=0.50, innovation_rate=0.65, obs_noise=0.03),
        _tech_actor("amazon",   "Amazon / AWS",      cuda_dependency=0.65, innovation_rate=0.45, obs_noise=0.03),
        _tech_actor("meta",     "Meta (open-weight sponsor)", cuda_dependency=0.60, innovation_rate=0.70, obs_noise=0.03),
        # Institutional investors (primary sentiment actors)
        _market_actor("inst_growth",  "Growth / Momentum Funds", platform_belief=0.80, sentiment=0.72, obs_noise=0.03),
        _market_actor("inst_value",   "Value / Fundamental Funds", platform_belief=0.70, sentiment=0.60, obs_noise=0.03),
        _market_actor("hedge_funds",  "Hedge Funds / Quant",      platform_belief=0.75, sentiment=0.65, obs_noise=0.04),
        # Retail / narrative-driven
        _market_actor("retail",       "Retail Investors",          platform_belief=0.82, sentiment=0.68, obs_noise=0.07),
    ]


# ── Theory stack ──────────────────────────────────────────────────────────────

def _build_theories(params_override: dict | None = None) -> list[TheoryRef]:
    """Build theory stack, optionally with MC parameter overrides."""
    p = params_override or {}

    def _p(base: dict, key: str) -> dict:
        """Return base params merged with any MC override for this theory."""
        overrides = p.get(key, {})
        return {**base, **overrides}

    return [
        # Priority 0 — Shock initialization
        TheoryRef(theory_id="event_study",      priority=0, parameters={}),
        TheoryRef(theory_id="platform_tipping", priority=0, parameters=_p(PLATFORM_TIPPING, "platform_tipping")),

        # Priority 1 — Structural dynamics
        TheoryRef(theory_id="compute_efficiency",  priority=1, parameters=_p(COMPUTE_EFFICIENCY, "compute_efficiency")),
        TheoryRef(theory_id="narrative_contagion", priority=1, parameters=_p(NARRATIVE_CONTAGION, "narrative_contagion")),

        # Priority 2 — Competitive response
        TheoryRef(theory_id="schumpeter_disruption", priority=2, parameters=_p(SCHUMPETER, "schumpeter")),
        TheoryRef(theory_id="fisher_pry",             priority=2, parameters=_p(FISHER_PRY, "fisher_pry")),

        # Priority 3 — Macro feedback
        TheoryRef(theory_id="minsky_instability", priority=3, parameters=_p(MINSKY, "minsky")),
        TheoryRef(theory_id="opinion_dynamics",   priority=3, parameters=_p(OPINION, "opinion")),

        # Priority 4 — Synthesis
        TheoryRef(theory_id="porter_five_forces", priority=4, parameters=_p(PORTER, "porter")),
        TheoryRef(theory_id="bass_diffusion",     priority=4, parameters=_p(BASS, "bass")),
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


# ── SimSpec builder ───────────────────────────────────────────────────────────

def build_spec(total_ticks: int = TOTAL_TICKS, params_override: dict | None = None) -> SimSpec:
    return SimSpec(
        name=TITLE,
        description=(
            "Models NVIDIA's market position shock following DeepSeek R1 release "
            "(Jan 20 2025) through Jun 2026. Tracks platform tipping dynamics, "
            "compute efficiency erosion, competing narrative contagion, and creative "
            "destruction. 10 theory modules: 3 NEW (platform_tipping, compute_efficiency, "
            "narrative_contagion) + 7 built-in. Primary metric: event__cumulative_ar "
            "(NVIDIA sentiment proxy)."
        ),
        domain=DOMAIN,
        actors=_build_actors(),
        theories=_build_theories(params_override),
        timeframe=TimeframeSpec(
            total_ticks=total_ticks,
            tick_unit=TICK_UNIT,
            start_date=START_DATE,
        ),
        uncertainty=UncertaintySpec(
            observation_noise_sigma=0.02,
            shock_probability=0.00,
            shock_magnitude=0.0,
            scheduled_shocks={
                k: v for k, v in SHOCKS.items() if k < total_ticks
            },
        ),
        metrics=_build_metrics(),
        initial_environment=copy.deepcopy(INITIAL_ENV),
    )


# ── Single deterministic run ─────────────────────────────────────────────────

def run(total_ticks: int = TOTAL_TICKS, seed: int = 0,
        params_override: dict | None = None) -> dict:
    spec = build_spec(total_ticks=total_ticks, params_override=params_override)
    runner = SimRunner(spec, rng_seed=seed)
    runner.setup()
    runner.run()

    series: dict[str, list[dict]] = {}
    for rec in runner.metric_history:
        series.setdefault(rec.env_key, []).append(
            {"tick": rec.tick, "value": rec.value}
        )

    return {
        "scenario_id": SCENARIO_ID,
        "total_ticks": total_ticks,
        "tick_unit": TICK_UNIT,
        "n_actors": len(spec.actors),
        "n_theories": len(spec.theories),
        "series": series,
        "final_env": runner.get_current_env(),
        "snapshots": [
            {"tick": s.tick, "label": s.label, "env": s.env}
            for s in runner.snapshots
        ],
    }


# ── Monte Carlo ───────────────────────────────────────────────────────────────

def _perturb_params(scenario: str, rng: random.Random) -> dict:
    """Generate parameter perturbations for a given MC scenario."""
    def g(mu, sigma):
        return max(0.0, min(1.0, rng.gauss(mu, sigma)))

    if scenario == "bull":
        return {
            "compute_efficiency": {
                "efficiency_doubling_period": rng.gauss(15.0, 2.0),  # slower erosion
                "moat_erosion_sensitivity": rng.gauss(1.2, 0.2),
            },
            "narrative_contagion": {
                "beta_bull": g(0.32, 0.04),   # stronger bull re-infection
                "beta_bear": g(0.25, 0.04),   # weaker bear
                "initial_bull_share": g(0.70, 0.03),
            },
            "platform_tipping": {
                "cross_side_network_effect": g(0.35, 0.03),  # stronger moat
                "switching_cost": g(0.18, 0.02),
                "initial_incumbent_share": g(0.87, 0.02),
            },
        }
    elif scenario == "bear":
        return {
            "compute_efficiency": {
                "efficiency_doubling_period": rng.gauss(9.0, 2.0),   # faster erosion
                "moat_erosion_sensitivity": rng.gauss(2.8, 0.3),
            },
            "narrative_contagion": {
                "beta_bull": g(0.18, 0.04),   # weaker bull recovery
                "beta_bear": g(0.42, 0.05),   # stronger bear contagion
                "initial_bear_share": g(0.08, 0.02),
            },
            "platform_tipping": {
                "cross_side_network_effect": g(0.24, 0.03),  # weaker moat
                "switching_cost": g(0.12, 0.02),
                "initial_incumbent_share": g(0.87, 0.02),
            },
        }
    else:  # base
        return {
            "compute_efficiency": {
                "efficiency_doubling_period": rng.gauss(12.0, 1.5),
                "moat_erosion_sensitivity": rng.gauss(2.0, 0.25),
            },
            "narrative_contagion": {
                "beta_bull": g(0.25, 0.03),
                "beta_bear": g(0.35, 0.03),
            },
            "platform_tipping": {
                "cross_side_network_effect": g(0.30, 0.02),
                "switching_cost": g(0.15, 0.015),
                "initial_incumbent_share": g(0.87, 0.02),
            },
        }


def run_monte_carlo(
    total_ticks: int = TOTAL_TICKS,
    n_runs: int = MC_RUNS,
    scenario_weights: dict | None = None,
    seed: int = 42,
) -> dict:
    """Run N Monte Carlo simulations and compute percentile bands."""
    rng = random.Random(seed)
    weights = scenario_weights or MC_SCENARIO_WEIGHTS
    scenarios = list(weights.keys())
    scenario_probs = [weights[s] for s in scenarios]

    # Cumulative distribution for scenario sampling
    cum = []
    total = 0.0
    for p in scenario_probs:
        total += p
        cum.append(total)

    def _sample_scenario() -> str:
        r = rng.random()
        for i, c in enumerate(cum):
            if r <= c:
                return scenarios[i]
        return scenarios[-1]

    all_series: dict[str, list[list[float]]] = {}
    scenario_counts: dict[str, int] = {s: 0 for s in scenarios}

    for run_idx in range(n_runs):
        scenario = _sample_scenario()
        scenario_counts[scenario] += 1
        params = _perturb_params(scenario, rng)
        try:
            result = run(total_ticks=total_ticks, seed=run_idx, params_override=params)
            for env_key, ticks_data in result["series"].items():
                if env_key not in all_series:
                    all_series[env_key] = []
                values = [r["value"] for r in ticks_data]
                all_series[env_key].append(values)
        except Exception as e:
            logger.warning("MC run %d failed: %s", run_idx, e)

    # Compute percentile bands
    bands: dict[str, dict] = {}
    for env_key, runs_data in all_series.items():
        if not runs_data:
            continue
        arr = np.array(runs_data)  # shape: (n_runs, n_ticks)
        final_vals = arr[:, -1] if arr.ndim == 2 and arr.shape[1] > 0 else arr

        # Per-tick bands
        tick_bands: list[dict] = []
        if arr.ndim == 2:
            for t in range(arr.shape[1]):
                col = arr[:, t]
                tick_bands.append({
                    "tick": t,
                    "p5":  float(np.percentile(col, 5)),
                    "p25": float(np.percentile(col, 25)),
                    "p50": float(np.percentile(col, 50)),
                    "p75": float(np.percentile(col, 75)),
                    "p95": float(np.percentile(col, 95)),
                })

        bands[env_key] = {
            "p5":   float(np.percentile(final_vals, 5)),
            "p25":  float(np.percentile(final_vals, 25)),
            "p50":  float(np.percentile(final_vals, 50)),
            "p75":  float(np.percentile(final_vals, 75)),
            "p95":  float(np.percentile(final_vals, 95)),
            "mean": float(np.mean(final_vals)),
            "tick_bands": tick_bands,
        }

    return {
        "n_runs": n_runs,
        "scenario_counts": scenario_counts,
        "bands": bands,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="DeepSeek scenario simulation")
    parser.add_argument("--ticks",  type=int, default=TOTAL_TICKS)
    parser.add_argument("--seed",   type=int, default=0)
    parser.add_argument("--out",    type=str, default=str(_OUT))
    parser.add_argument("--no-mc",  action="store_true", help="Skip Monte Carlo")
    parser.add_argument("--mc-runs", type=int, default=MC_RUNS)
    args = parser.parse_args()

    # ── Deterministic run
    logger.warning("Running DeepSeek deterministic simulation: %d ticks, seed=%d",
                   args.ticks, args.seed)
    det_results = run(total_ticks=args.ticks, seed=args.seed)
    print(f"Deterministic run: {det_results['n_actors']} actors, "
          f"{det_results['n_theories']} theories, {det_results['total_ticks']} ticks")

    # ── Monte Carlo
    mc_results = {}
    if not args.no_mc:
        logger.warning("Running Monte Carlo: %d runs", args.mc_runs)
        mc_results = run_monte_carlo(
            total_ticks=args.ticks,
            n_runs=args.mc_runs,
            seed=args.seed + 1,
        )
        counts = mc_results["scenario_counts"]
        print(f"Monte Carlo: {mc_results['n_runs']} runs "
              f"(base={counts['base']}, bull={counts['bull']}, bear={counts['bear']})")

    # ── v2 output format
    output = {
        "scenario_id": SCENARIO_ID,
        "version": "v2",
        "deterministic": det_results,
        "monte_carlo": mc_results,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))
    print(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
