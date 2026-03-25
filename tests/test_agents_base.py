"""
Tests for core/agents/base.py

Covers:
- BetaBelief: mean, variance, update, decay, sample
- GaussianBelief: Kalman update, diffuse (process noise), sample
- Action dataclass (no intensity, duration field)
- BDIAgent: from_spec, decay_beliefs, observe_environment, update_beliefs
  (maps_to_env_key), expected_utility (DesireSpec), can_act,
  expend_capacity, recharge_capabilities, get_state_snapshot
- Thread-safe RNG
"""

import math
import random

import pytest

from core.agents.base import Action, BDIAgent, BetaBelief, GaussianBelief
from core.spec import (
    ActorSpec,
    BeliefDistType,
    BeliefSpec,
    CapabilitySpec,
    DesireSpec,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_rng(seed: int = 0) -> random.Random:
    return random.Random(seed)


def make_capability(
    capacity: float = 1.0,
    cost: float = 0.2,
    recovery_rate: float = 0.1,
    cooldown_ticks: int = 0,
    current: float | None = None,
    cooldown_remaining: int = 0,
) -> dict:
    return {
        "capacity":           capacity,
        "cost":               cost,
        "recovery_rate":      recovery_rate,
        "cooldown_ticks":     float(cooldown_ticks),
        "current":            current if current is not None else capacity,
        "cooldown_remaining": cooldown_remaining,
    }


class SimpleAgent(BDIAgent):
    """Minimal concrete agent for testing."""

    def __init__(self, *args, actions=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._actions = actions or []

    def decide(self, env: dict, tick: int) -> list[Action]:
        return list(self._actions)


def make_agent(
    actor_id: str = "a1",
    name: str = "Iran",
    beliefs=None,
    desires=None,
    capabilities=None,
    noise: float = 0.0,
    rng: random.Random | None = None,
    actions=None,
) -> SimpleAgent:
    return SimpleAgent(
        actor_id=actor_id,
        name=name,
        beliefs=beliefs or {},
        desires=desires or [],
        capabilities=capabilities or {},
        observation_noise_sigma=noise,
        rng=rng or make_rng(0),
        actions=actions,
    )


def make_desire(
    name: str = "Maximize revenue",
    target_env_key: str = "revenue",
    direction: float = 1.0,
    weight: float = 1.0,
) -> DesireSpec:
    return DesireSpec(name=name, target_env_key=target_env_key,
                      direction=direction, weight=weight)


# ── BetaBelief ────────────────────────────────────────────────────────────────

class TestBetaBelief:
    def test_initial_mean_uniform(self):
        b = BetaBelief("coop", alpha=1.0, beta=1.0)
        assert b.mean == pytest.approx(0.5)

    def test_mean_formula(self):
        b = BetaBelief("coop", alpha=3.0, beta=1.0)
        assert b.mean == pytest.approx(0.75)

    def test_variance_formula(self):
        b = BetaBelief("coop", alpha=2.0, beta=2.0)
        expected = (2 * 2) / (4 * 4 * 5)
        assert b.variance == pytest.approx(expected)

    def test_update_increases_alpha_on_high_obs(self):
        b = BetaBelief("coop", alpha=1.0, beta=1.0)
        b.update(1.0, precision=1.0)
        assert b.alpha == pytest.approx(2.0)
        assert b.beta  == pytest.approx(1.0)

    def test_update_increases_beta_on_low_obs(self):
        b = BetaBelief("coop", alpha=1.0, beta=1.0)
        b.update(0.0, precision=1.0)
        assert b.alpha == pytest.approx(1.0)
        assert b.beta  == pytest.approx(2.0)

    def test_update_precision_scales(self):
        b = BetaBelief("coop", alpha=1.0, beta=1.0)
        b.update(0.5, precision=2.0)
        assert b.alpha == pytest.approx(2.0)
        assert b.beta  == pytest.approx(2.0)

    def test_update_bias_shifts_observation(self):
        b = BetaBelief("coop", alpha=1.0, beta=1.0)
        b.update(1.0, precision=1.0, bias=-0.5)
        assert b.alpha == pytest.approx(1.5)
        assert b.beta  == pytest.approx(1.5)

    def test_update_clamps_above_one(self):
        b = BetaBelief("coop", alpha=1.0, beta=1.0)
        b.update(0.8, bias=0.5)  # 1.3 → 1.0
        assert b.alpha == pytest.approx(2.0)
        assert b.beta  == pytest.approx(1.0)

    def test_update_clamps_below_zero(self):
        b = BetaBelief("coop", alpha=1.0, beta=1.0)
        b.update(0.2, bias=-0.5)  # -0.3 → 0.0
        assert b.alpha == pytest.approx(1.0)
        assert b.beta  == pytest.approx(2.0)

    def test_sample_in_range(self):
        rng = make_rng(1)
        b = BetaBelief("coop", alpha=2.0, beta=2.0)
        samples = [b.sample(rng) for _ in range(200)]
        assert all(0.0 <= s <= 1.0 for s in samples)

    def test_sample_mean_approx(self):
        rng = make_rng(1)
        b = BetaBelief("coop", alpha=5.0, beta=1.0)
        samples = [b.sample(rng) for _ in range(500)]
        assert abs(sum(samples) / len(samples) - b.mean) < 0.05

    def test_deterministic_with_same_seed(self):
        b = BetaBelief("x", alpha=2.0, beta=3.0)
        assert b.sample(make_rng(42)) == b.sample(make_rng(42))

    # ── decay ──────────────────────────────────────────────────────────────────

    def test_decay_noop_at_rate_one(self):
        b = BetaBelief("x", alpha=10.0, beta=5.0, decay_rate=1.0)
        b.decay()
        assert b.alpha == pytest.approx(10.0)
        assert b.beta  == pytest.approx(5.0)

    def test_decay_pulls_toward_uniform(self):
        b = BetaBelief("x", alpha=10.0, beta=1.0, decay_rate=0.9)
        b.decay()
        # alpha should move from 10 toward 1 (not reach 1, but get closer)
        assert 1.0 < b.alpha < 10.0
        # beta was already at 1 — should stay at 1.0
        assert b.beta == pytest.approx(1.0)

    def test_decay_formula(self):
        b = BetaBelief("x", alpha=5.0, beta=3.0, decay_rate=0.8)
        b.decay()
        assert b.alpha == pytest.approx(1.0 + (5.0 - 1.0) * 0.8)
        assert b.beta  == pytest.approx(1.0 + (3.0 - 1.0) * 0.8)

    def test_decay_repeated_converges_toward_uniform(self):
        b = BetaBelief("x", alpha=100.0, beta=1.0, decay_rate=0.5)
        for _ in range(30):
            b.decay()
        assert b.alpha == pytest.approx(1.0, abs=0.01)
        assert b.beta  == pytest.approx(1.0, abs=0.01)

    def test_decay_does_not_go_below_one(self):
        """decay_rate=0 → immediately collapses to uniform."""
        b = BetaBelief("x", alpha=50.0, beta=20.0, decay_rate=0.0)
        b.decay()
        assert b.alpha == pytest.approx(1.0)
        assert b.beta  == pytest.approx(1.0)

    def test_maps_to_env_key_default_none(self):
        b = BetaBelief("coop")
        assert b.maps_to_env_key is None

    def test_maps_to_env_key_set(self):
        b = BetaBelief("coop", maps_to_env_key="us__strike_prob")
        assert b.maps_to_env_key == "us__strike_prob"


# ── GaussianBelief ────────────────────────────────────────────────────────────

class TestGaussianBelief:
    def test_defaults(self):
        g = GaussianBelief("gdp")
        assert g.mean == 0.0
        assert g.variance == 1.0

    def test_kalman_update_moves_mean_toward_obs(self):
        g = GaussianBelief("gdp", mean=0.0, variance=1.0)
        g.update(1.0, obs_variance=1.0)
        assert g.mean == pytest.approx(0.5)

    def test_kalman_update_reduces_variance(self):
        g = GaussianBelief("gdp", mean=0.0, variance=1.0)
        v_before = g.variance
        g.update(0.5, obs_variance=1.0)
        assert g.variance < v_before

    def test_kalman_variance_formula(self):
        g = GaussianBelief("gdp", mean=0.0, variance=1.0)
        g.update(1.0, obs_variance=1.0)
        assert g.variance == pytest.approx(0.5)

    def test_high_obs_variance_small_update(self):
        g = GaussianBelief("gdp", mean=0.0, variance=0.1)
        g.update(1.0, obs_variance=1000.0)
        assert g.mean == pytest.approx(0.0, abs=0.01)

    def test_low_obs_variance_big_update(self):
        g = GaussianBelief("gdp", mean=0.0, variance=1.0)
        g.update(1.0, obs_variance=0.0001)
        assert g.mean == pytest.approx(1.0, abs=0.01)

    def test_sample_returns_float(self):
        g = GaussianBelief("gdp", mean=0.5, variance=0.01)
        assert isinstance(g.sample(make_rng(0)), float)

    def test_sample_variance_zero_edge(self):
        g = GaussianBelief("gdp", mean=0.5, variance=0.0)
        assert g.sample(make_rng(0)) == pytest.approx(0.5)

    def test_repeated_updates_converge(self):
        g = GaussianBelief("gdp", mean=0.0, variance=1.0)
        for _ in range(50):
            g.update(0.8, obs_variance=0.1)
        assert g.mean == pytest.approx(0.8, abs=0.05)

    # ── diffuse (process noise) ────────────────────────────────────────────────

    def test_diffuse_noop_at_zero(self):
        g = GaussianBelief("gdp", mean=0.5, variance=0.1, process_noise=0.0)
        g.diffuse()
        assert g.variance == pytest.approx(0.1)

    def test_diffuse_increases_variance(self):
        g = GaussianBelief("gdp", mean=0.5, variance=0.1, process_noise=0.05)
        g.diffuse()
        assert g.variance == pytest.approx(0.15)

    def test_diffuse_does_not_change_mean(self):
        g = GaussianBelief("gdp", mean=0.5, variance=0.1, process_noise=0.1)
        g.diffuse()
        assert g.mean == pytest.approx(0.5)

    def test_diffuse_prevents_variance_collapse(self):
        """With process noise, variance stays positive after many Kalman updates."""
        g = GaussianBelief("gdp", mean=0.0, variance=1.0, process_noise=0.01)
        for _ in range(100):
            g.diffuse()
            g.update(0.8, obs_variance=0.01)
        assert g.variance > 0.005

    def test_without_process_noise_variance_collapses(self):
        """Contrast: without process noise, variance approaches 0."""
        g = GaussianBelief("gdp", mean=0.0, variance=1.0, process_noise=0.0)
        for _ in range(100):
            g.update(0.8, obs_variance=0.01)
        assert g.variance < 0.001

    def test_maps_to_env_key_default_none(self):
        g = GaussianBelief("gdp")
        assert g.maps_to_env_key is None

    def test_maps_to_env_key_set(self):
        g = GaussianBelief("gdp", maps_to_env_key="global__gdp_growth")
        assert g.maps_to_env_key == "global__gdp_growth"


# ── Action ────────────────────────────────────────────────────────────────────

class TestAction:
    def test_construction(self):
        a = Action("act1", "environment")
        assert a.action_id == "act1"
        assert a.target == "environment"
        assert a.capability_id is None
        assert a.parameters == {}
        assert a.duration == 1
        assert a.description == ""

    def test_no_intensity_field(self):
        """intensity was removed — accessing it should raise AttributeError."""
        a = Action("act1", "environment")
        assert not hasattr(a, "intensity")

    def test_with_capability_and_parameters(self):
        a = Action("act2", "iran", capability_id="naval",
                   parameters={"tension": 0.1}, duration=3)
        assert a.capability_id == "naval"
        assert a.parameters["tension"] == 0.1
        assert a.duration == 3

    def test_duration_default_one(self):
        a = Action("act1", "environment")
        assert a.duration == 1

    def test_multi_tick_duration(self):
        a = Action("blockade", "strait", duration=30,
                   parameters={"strait__tension": 0.05})
        assert a.duration == 30


# ── BDIAgent: construction ────────────────────────────────────────────────────

class TestBDIAgentConstruction:
    def test_defaults(self):
        agent = make_agent()
        assert agent.actor_id == "a1"
        assert agent.beliefs == {}
        assert agent.desires == []
        assert agent.capabilities == {}

    def test_rng_injection(self):
        rng = make_rng(99)
        agent = make_agent(rng=rng)
        assert agent.rng is rng

    def test_default_rng_created_when_none(self):
        agent = make_agent(rng=None)
        assert isinstance(agent.rng, random.Random)


# ── BDIAgent: from_spec ───────────────────────────────────────────────────────

class TestFromSpec:
    def _make_actor_spec(self, **kwargs) -> ActorSpec:
        defaults = dict(name="Iran")
        defaults.update(kwargs)
        return ActorSpec(**defaults)

    def test_basic_fields(self):
        spec  = self._make_actor_spec(name="Iran")
        agent = SimpleAgent.from_spec(spec, make_rng(0))
        assert agent.actor_id == spec.actor_id
        assert agent.name == "Iran"

    def test_beta_belief_hydrated(self):
        spec = self._make_actor_spec(
            beliefs=[BeliefSpec(name="p_strike", dist_type=BeliefDistType.BETA,
                                alpha=3.0, beta=1.0)]
        )
        agent = SimpleAgent.from_spec(spec, make_rng(0))
        assert "p_strike" in agent.beliefs
        b = agent.beliefs["p_strike"]
        assert isinstance(b, BetaBelief)
        assert b.alpha == pytest.approx(3.0)
        assert b.beta  == pytest.approx(1.0)

    def test_gaussian_belief_hydrated(self):
        spec = self._make_actor_spec(
            beliefs=[BeliefSpec(name="gdp", dist_type=BeliefDistType.GAUSSIAN,
                                mean=0.4, variance=0.2)]
        )
        agent = SimpleAgent.from_spec(spec, make_rng(0))
        g = agent.beliefs["gdp"]
        assert isinstance(g, GaussianBelief)
        assert g.mean == pytest.approx(0.4)
        assert g.variance == pytest.approx(0.2)

    def test_point_belief_becomes_zero_variance_gaussian(self):
        spec = self._make_actor_spec(
            beliefs=[BeliefSpec(name="fixed", dist_type=BeliefDistType.POINT,
                                value=0.7)]
        )
        agent = SimpleAgent.from_spec(spec, make_rng(0))
        g = agent.beliefs["fixed"]
        assert isinstance(g, GaussianBelief)
        assert g.mean == pytest.approx(0.7)
        assert g.variance == pytest.approx(0.0)

    def test_maps_to_env_key_propagated(self):
        spec = self._make_actor_spec(
            beliefs=[BeliefSpec(name="p_strike",
                                maps_to_env_key="us__strike_probability")]
        )
        agent = SimpleAgent.from_spec(spec, make_rng(0))
        assert agent.beliefs["p_strike"].maps_to_env_key == "us__strike_probability"

    def test_desire_hydrated(self):
        spec = self._make_actor_spec(
            desires=[DesireSpec(name="Sovereignty", target_env_key="iran__sovereignty",
                                direction=1.0, weight=2.0)]
        )
        agent = SimpleAgent.from_spec(spec, make_rng(0))
        assert len(agent.desires) == 1
        d = agent.desires[0]
        assert d.target_env_key == "iran__sovereignty"
        assert d.weight == pytest.approx(2.0)

    def test_capability_hydrated_full(self):
        spec = self._make_actor_spec(
            capabilities=[CapabilitySpec(name="Naval", capability_id="naval",
                                         capacity=1.0, cost=0.3,
                                         recovery_rate=0.1, cooldown_ticks=2)]
        )
        agent = SimpleAgent.from_spec(spec, make_rng(0))
        assert "naval" in agent.capabilities
        cap = agent.capabilities["naval"]
        assert cap["capacity"]  == pytest.approx(1.0)
        assert cap["cost"]      == pytest.approx(0.3)
        assert cap["current"]   == pytest.approx(1.0)   # starts full
        assert cap["cooldown_remaining"] == 0.0

    def test_rng_injected(self):
        rng  = make_rng(42)
        spec = self._make_actor_spec()
        agent = SimpleAgent.from_spec(spec, rng)
        assert agent.rng is rng

    def test_returns_subclass_instance(self):
        """from_spec on a subclass returns that subclass, not BDIAgent."""
        spec  = self._make_actor_spec()
        agent = SimpleAgent.from_spec(spec, make_rng(0))
        assert isinstance(agent, SimpleAgent)


# ── BDIAgent: decay_beliefs ───────────────────────────────────────────────────

class TestDecayBeliefs:
    def test_beta_belief_decayed(self):
        b     = BetaBelief("x", alpha=10.0, beta=5.0, decay_rate=0.9)
        agent = make_agent(beliefs={"x": b})
        agent.decay_beliefs()
        assert b.alpha < 10.0
        assert b.beta  < 5.0

    def test_gaussian_belief_diffused(self):
        g     = GaussianBelief("gdp", mean=0.5, variance=0.1, process_noise=0.05)
        agent = make_agent(beliefs={"gdp": g})
        agent.decay_beliefs()
        assert g.variance == pytest.approx(0.15)

    def test_noop_defaults(self):
        """Default decay_rate=1.0 and process_noise=0.0 → no change."""
        b     = BetaBelief("x", alpha=5.0, beta=3.0)          # decay_rate=1.0
        g     = GaussianBelief("gdp", mean=0.5, variance=0.1)  # process_noise=0.0
        agent = make_agent(beliefs={"x": b, "gdp": g})
        agent.decay_beliefs()
        assert b.alpha    == pytest.approx(5.0)
        assert g.variance == pytest.approx(0.1)


# ── BDIAgent: observe_environment ────────────────────────────────────────────

class TestObserveEnvironment:
    def test_returns_dict_with_same_keys(self):
        agent = make_agent(noise=0.0)
        obs   = agent.observe_environment({"tension": 0.5, "readiness": 0.7})
        assert set(obs.keys()) == {"tension", "readiness"}

    def test_zero_noise_exact_values(self):
        agent = make_agent(noise=0.0)
        obs   = agent.observe_environment({"tension": 0.5})
        assert obs["tension"] == pytest.approx(0.5)

    def test_stores_observations(self):
        agent = make_agent(noise=0.0)
        agent.observe_environment({"tension": 0.5})
        assert agent._observations["tension"] == pytest.approx(0.5)

    def test_clamps_to_0_1(self):
        agent = make_agent(noise=0.5, rng=make_rng(7))
        for _ in range(30):
            obs = agent.observe_environment({"x": 0.99, "y": 0.01})
            assert all(0.0 <= v <= 1.0 for v in obs.values())

    def test_deterministic_same_seed(self):
        env  = {"tension": 0.5}
        obs1 = make_agent(noise=0.05, rng=make_rng(42)).observe_environment(env)
        obs2 = make_agent(noise=0.05, rng=make_rng(42)).observe_environment(env)
        assert obs1["tension"] == pytest.approx(obs2["tension"])


# ── BDIAgent: update_beliefs (maps_to_env_key) ────────────────────────────────

class TestUpdateBeliefs:
    def test_beta_matches_by_name(self):
        b     = BetaBelief("tension")
        agent = make_agent(beliefs={"tension": b})
        agent._observations = {"tension": 0.9}
        agent.update_beliefs()
        assert b.alpha > 1.0

    def test_beta_matches_by_maps_to_env_key(self):
        """Belief name != env key, but maps_to_env_key bridges them."""
        b     = BetaBelief("p_us_strike", maps_to_env_key="us__strike_probability")
        agent = make_agent(beliefs={"p_us_strike": b})
        agent._observations = {"us__strike_probability": 0.9}
        agent.update_beliefs()
        # High observation → alpha should grow
        assert b.alpha > 1.0

    def test_name_mismatch_no_maps_to_env_key_skipped(self):
        """Without maps_to_env_key, a name mismatch leaves the belief unchanged."""
        b     = BetaBelief("p_us_strike")  # name ≠ env key, no mapping
        agent = make_agent(beliefs={"p_us_strike": b})
        agent._observations = {"us__strike_probability": 0.9}
        agent.update_beliefs()
        assert b.alpha == pytest.approx(1.0)  # unchanged

    def test_gaussian_updated(self):
        g     = GaussianBelief("gdp")
        agent = make_agent(beliefs={"gdp": g})
        agent._observations = {"gdp": 0.8}
        agent.update_beliefs()
        assert g.mean != 0.0

    def test_gaussian_matches_by_maps_to_env_key(self):
        g     = GaussianBelief("gdp_estimate", maps_to_env_key="global__gdp")
        agent = make_agent(beliefs={"gdp_estimate": g})
        agent._observations = {"global__gdp": 0.6}
        agent.update_beliefs()
        assert g.mean != 0.0

    def test_explicit_observations_override_stored(self):
        b     = BetaBelief("tension")
        agent = make_agent(beliefs={"tension": b})
        agent._observations = {"tension": 0.0}
        agent.update_beliefs(observations={"tension": 1.0})
        assert b.alpha > b.beta


# ── BDIAgent: expected_utility ────────────────────────────────────────────────

class TestExpectedUtility:
    def test_single_maximize(self):
        agent = make_agent(desires=[make_desire("Rev", "revenue", 1.0, 1.0)])
        assert agent.expected_utility({"revenue": 0.8}) == pytest.approx(0.8)

    def test_single_minimize(self):
        agent = make_agent(desires=[make_desire("Tension", "tension", -1.0, 1.0)])
        assert agent.expected_utility({"tension": 0.6}) == pytest.approx(-0.6)

    def test_weighted_sum(self):
        agent = make_agent(desires=[
            make_desire("Rev",     "revenue", 1.0,  2.0),
            make_desire("Tension", "tension", -1.0, 1.0),
        ])
        eu = agent.expected_utility({"revenue": 0.5, "tension": 0.4})
        assert eu == pytest.approx(2.0 * 0.5 + 1.0 * -1.0 * 0.4)

    def test_missing_env_key_zero(self):
        agent = make_agent(desires=[make_desire("x", "nonexistent")])
        assert agent.expected_utility({}) == pytest.approx(0.0)

    def test_no_desires_zero(self):
        agent = make_agent()
        assert agent.expected_utility({"tension": 0.9}) == pytest.approx(0.0)

    def test_uses_desirespec_attributes_not_dict(self):
        """Confirm desires are DesireSpec, not plain dicts."""
        agent = make_agent(desires=[make_desire("Rev", "revenue")])
        assert hasattr(agent.desires[0], "target_env_key")
        assert isinstance(agent.desires[0], DesireSpec)


# ── BDIAgent: can_act / expend / recharge ─────────────────────────────────────

class TestCanAct:
    def test_full_capacity_no_cooldown(self):
        agent = make_agent(capabilities={"naval": make_capability(current=1.0)})
        assert agent.can_act("naval") is True

    def test_insufficient_capacity(self):
        agent = make_agent(capabilities={"naval": make_capability(cost=0.5, current=0.1)})
        assert agent.can_act("naval") is False

    def test_on_cooldown(self):
        cap = make_capability(current=1.0, cooldown_remaining=3)
        agent = make_agent(capabilities={"naval": cap})
        assert agent.can_act("naval") is False

    def test_unknown_capability(self):
        assert make_agent().can_act("nonexistent") is False

    def test_exact_boundary(self):
        cap = make_capability(cost=0.5, current=0.5)
        agent = make_agent(capabilities={"naval": cap})
        assert agent.can_act("naval") is True


class TestExpendCapacity:
    def test_returns_true_reduces_capacity(self):
        cap   = make_capability(cost=0.3, current=1.0)
        agent = make_agent(capabilities={"naval": cap})
        assert agent.expend_capacity("naval") is True
        assert cap["current"] == pytest.approx(0.7)

    def test_returns_false_when_blocked(self):
        cap   = make_capability(cost=0.5, current=0.1)
        agent = make_agent(capabilities={"naval": cap})
        assert agent.expend_capacity("naval") is False
        assert cap["current"] == pytest.approx(0.1)

    def test_starts_cooldown(self):
        cap   = make_capability(cost=0.1, current=1.0, cooldown_ticks=3)
        agent = make_agent(capabilities={"naval": cap})
        agent.expend_capacity("naval")
        assert cap["cooldown_remaining"] == 3.0

    def test_exhaustion_prevents_second_use(self):
        cap   = make_capability(capacity=0.3, cost=0.3, current=0.3)
        agent = make_agent(capabilities={"naval": cap})
        assert agent.expend_capacity("naval") is True
        assert agent.expend_capacity("naval") is False


class TestRechargeCapabilities:
    def test_recovers_capacity(self):
        cap   = make_capability(capacity=1.0, current=0.2, recovery_rate=0.1)
        agent = make_agent(capabilities={"naval": cap})
        agent.recharge_capabilities()
        assert cap["current"] == pytest.approx(0.3)

    def test_does_not_exceed_max(self):
        cap   = make_capability(capacity=1.0, current=0.95, recovery_rate=0.1)
        agent = make_agent(capabilities={"naval": cap})
        agent.recharge_capabilities()
        assert cap["current"] == pytest.approx(1.0)

    def test_decrements_cooldown(self):
        cap   = make_capability(current=1.0, cooldown_remaining=5)
        agent = make_agent(capabilities={"naval": cap})
        agent.recharge_capabilities()
        assert cap["cooldown_remaining"] == 4

    def test_cooldown_floor_zero(self):
        cap   = make_capability(current=1.0, cooldown_remaining=0)
        agent = make_agent(capabilities={"naval": cap})
        agent.recharge_capabilities()
        assert cap["cooldown_remaining"] == 0

    def test_full_expend_recharge_cycle(self):
        cap = make_capability(capacity=1.0, cost=0.5, current=1.0,
                              recovery_rate=0.5, cooldown_ticks=2)
        agent = make_agent(capabilities={"naval": cap})
        agent.expend_capacity("naval")
        assert cap["current"] == pytest.approx(0.5)
        assert cap["cooldown_remaining"] == 2.0
        agent.recharge_capabilities()
        assert cap["current"] == pytest.approx(1.0)
        assert cap["cooldown_remaining"] == 1.0


# ── BDIAgent: get_state_snapshot ─────────────────────────────────────────────

class TestGetStateSnapshot:
    def test_basic_structure(self):
        snap = make_agent().get_state_snapshot()
        assert "actor_id" in snap and "beliefs" in snap and "capabilities" in snap

    def test_beta_belief(self):
        b    = BetaBelief("coop", alpha=3.0, beta=1.0)
        snap = make_agent(beliefs={"coop": b}).get_state_snapshot()
        assert snap["beliefs"]["coop"]["alpha"] == pytest.approx(3.0)
        assert snap["beliefs"]["coop"]["mean"]  == pytest.approx(0.75)

    def test_gaussian_belief(self):
        g    = GaussianBelief("gdp", mean=0.5, variance=0.1)
        snap = make_agent(beliefs={"gdp": g}).get_state_snapshot()
        assert snap["beliefs"]["gdp"]["mean"]     == pytest.approx(0.5)
        assert snap["beliefs"]["gdp"]["variance"] == pytest.approx(0.1)
        assert "alpha" not in snap["beliefs"]["gdp"]

    def test_serializable(self):
        import json
        b   = BetaBelief("coop", alpha=2.0, beta=2.0)
        cap = make_capability()
        snap = make_agent(beliefs={"coop": b}, capabilities={"naval": cap}).get_state_snapshot()
        json.dumps(snap)  # must not raise


# ── Thread-safe RNG ───────────────────────────────────────────────────────────

class TestThreadSafeRng:
    def test_same_seed_same_observations(self):
        env  = {"tension": 0.5, "readiness": 0.7}
        obs1 = make_agent(noise=0.05, rng=make_rng(42)).observe_environment(env)
        obs2 = make_agent(noise=0.05, rng=make_rng(42)).observe_environment(env)
        for key in env:
            assert obs1[key] == pytest.approx(obs2[key])

    def test_different_seeds_different_observations(self):
        env  = {"tension": 0.5}
        obs1 = make_agent(noise=0.1, rng=make_rng(1)).observe_environment(env)
        obs2 = make_agent(noise=0.1, rng=make_rng(2)).observe_environment(env)
        assert obs1["tension"] != pytest.approx(obs2["tension"])

    def test_rng_not_global(self):
        before = random.getstate()
        agent  = make_agent(noise=0.05, rng=make_rng(99))
        for _ in range(20):
            agent.observe_environment({"x": 0.5})
        assert random.getstate() == before


# ── AgentHydrationError ───────────────────────────────────────────────────────

class TestAgentHydrationError:
    def test_raised_on_duplicate_belief_names(self):
        from core.agents.base import AgentHydrationError
        spec = ActorSpec(
            name="Iran",
            beliefs=[
                BeliefSpec(name="p_strike"),
                BeliefSpec(name="p_strike"),  # duplicate
            ],
        )
        with pytest.raises(AgentHydrationError, match="duplicate belief name"):
            SimpleAgent.from_spec(spec, make_rng(0))

    def test_importable_from_core_agents(self):
        from core.agents import AgentHydrationError
        assert AgentHydrationError is not None


# ── BetaBelief: alpha/beta validation ─────────────────────────────────────────

class TestBetaBeliefValidation:
    def test_alpha_zero_raises(self):
        with pytest.raises(ValueError, match="alpha and beta must be > 0"):
            BetaBelief("x", alpha=0.0, beta=1.0)

    def test_beta_zero_raises(self):
        with pytest.raises(ValueError, match="alpha and beta must be > 0"):
            BetaBelief("x", alpha=1.0, beta=0.0)

    def test_negative_alpha_raises(self):
        with pytest.raises(ValueError):
            BetaBelief("x", alpha=-0.5, beta=1.0)

    def test_valid_sub_one_alpha_ok(self):
        b = BetaBelief("x", alpha=0.5, beta=0.5)
        assert b.mean == pytest.approx(0.5)


# ── GaussianBelief: 0/0 guard ─────────────────────────────────────────────────

class TestGaussianBeliefZeroGuard:
    def test_zero_variance_zero_obs_variance_no_crash(self):
        """POINT belief (variance=0) with noise_sigma=0 must not raise ZeroDivisionError."""
        g = GaussianBelief("fixed", mean=0.7, variance=0.0)
        g.update(0.9, obs_variance=0.0)
        assert g.mean == pytest.approx(0.7)  # certain belief unchanged

    def test_zero_obs_variance_nonzero_self_variance_updates(self):
        """Perfect observation (obs_variance=0) with uncertain belief → jump to observation."""
        g = GaussianBelief("gdp", mean=0.0, variance=1.0)
        g.update(0.8, obs_variance=0.0)
        assert g.mean == pytest.approx(0.8)

    def test_nonzero_normal_case_unchanged(self):
        """Normal path still works correctly after adding the guard."""
        g = GaussianBelief("gdp", mean=0.0, variance=1.0)
        g.update(1.0, obs_variance=1.0)
        assert g.mean == pytest.approx(0.5)


# ── from_spec: dynamics propagation ──────────────────────────────────────────

class TestFromSpecDynamicsPropagation:
    def test_decay_rate_propagated(self):
        spec = ActorSpec(
            name="Iran",
            beliefs=[BeliefSpec(name="p", dist_type=BeliefDistType.BETA, decay_rate=0.9)],
        )
        agent = SimpleAgent.from_spec(spec, make_rng(0))
        assert agent.beliefs["p"].decay_rate == pytest.approx(0.9)

    def test_process_noise_propagated(self):
        spec = ActorSpec(
            name="Iran",
            beliefs=[BeliefSpec(name="gdp", dist_type=BeliefDistType.GAUSSIAN,
                                process_noise=0.02)],
        )
        agent = SimpleAgent.from_spec(spec, make_rng(0))
        assert agent.beliefs["gdp"].process_noise == pytest.approx(0.02)

    def test_observation_noise_sigma_propagated(self):
        spec = ActorSpec(name="Iran", observation_noise_sigma=0.05)
        agent = SimpleAgent.from_spec(spec, make_rng(0))
        assert agent.observation_noise_sigma == pytest.approx(0.05)

    def test_default_observation_noise_sigma(self):
        spec  = ActorSpec(name="Iran")
        agent = SimpleAgent.from_spec(spec, make_rng(0))
        assert agent.observation_noise_sigma == pytest.approx(0.02)

    def test_point_belief_process_noise_propagated(self):
        spec = ActorSpec(
            name="Iran",
            beliefs=[BeliefSpec(name="fixed", dist_type=BeliefDistType.POINT,
                                value=0.7, process_noise=0.01)],
        )
        agent = SimpleAgent.from_spec(spec, make_rng(0))
        g = agent.beliefs["fixed"]
        assert isinstance(g, GaussianBelief)
        assert g.process_noise == pytest.approx(0.01)


# ── BDIAgent.tick() coordinator ───────────────────────────────────────────────

class TestTickCoordinator:
    def test_returns_actions(self):
        action = Action("a1", "environment", parameters={"x": 0.1})
        agent  = make_agent(actions=[action])
        result = agent.tick({"x": 0.5}, tick_num=1)
        assert result == [action]

    def test_observations_stored(self):
        agent = make_agent(noise=0.0)
        agent.tick({"tension": 0.5}, tick_num=1)
        assert agent._observations["tension"] == pytest.approx(0.5)

    def test_beliefs_updated_via_tick(self):
        b     = BetaBelief("tension")
        agent = make_agent(beliefs={"tension": b}, noise=0.0)
        agent.tick({"tension": 0.9}, tick_num=1)
        assert b.alpha > 1.0  # updated from observation

    def test_beliefs_decayed_via_tick(self):
        b     = BetaBelief("x", alpha=10.0, beta=1.0, decay_rate=0.8)
        agent = make_agent(beliefs={"x": b}, noise=0.0)
        agent.tick({"x": 0.5}, tick_num=1)
        assert b.alpha < 10.0  # decayed before update

    def test_recharge_not_called_by_tick(self):
        """tick() must NOT recharge capabilities — that's SimRunner's job."""
        cap   = make_capability(capacity=1.0, cost=0.5, current=0.5, recovery_rate=0.5)
        agent = make_agent(capabilities={"naval": cap})
        agent.tick({}, tick_num=1)
        assert cap["current"] == pytest.approx(0.5)  # unchanged

    def test_tick_deterministic_same_seed(self):
        env  = {"tension": 0.5}
        b1   = BetaBelief("tension", alpha=1.0, beta=1.0)
        b2   = BetaBelief("tension", alpha=1.0, beta=1.0)
        a1   = make_agent(beliefs={"tension": b1}, noise=0.05, rng=make_rng(42))
        a2   = make_agent(beliefs={"tension": b2}, noise=0.05, rng=make_rng(42))
        a1.tick(env, 1)
        a2.tick(env, 1)
        assert b1.alpha == pytest.approx(b2.alpha)


# ── DefaultBDIAgent ───────────────────────────────────────────────────────────

class TestDefaultBDIAgent:
    from core.agents.base import DefaultBDIAgent

    def _make_default(
        self,
        owned_env_keys=None,
        desires=None,
        capabilities=None,
        push_delta=0.05,
    ):
        from core.agents.base import DefaultBDIAgent
        return DefaultBDIAgent(
            actor_id="a1",
            name="Iran",
            owned_env_keys=owned_env_keys or [],
            desires=desires or [],
            capabilities=capabilities or {},
            push_delta=push_delta,
            rng=make_rng(0),
        )

    def test_returns_empty_no_desires(self):
        agent = self._make_default(owned_env_keys=["x"], capabilities={"c": make_capability()})
        assert agent.decide({}, 1) == []

    def test_returns_empty_no_capabilities(self):
        agent = self._make_default(
            owned_env_keys=["revenue"],
            desires=[make_desire("Rev", "revenue")],
        )
        assert agent.decide({"revenue": 0.5}, 1) == []

    def test_returns_empty_no_owned_keys(self):
        agent = self._make_default(
            owned_env_keys=[],
            desires=[make_desire("Rev", "revenue")],
            capabilities={"c": make_capability()},
        )
        assert agent.decide({"revenue": 0.5}, 1) == []

    def test_pushes_owned_key_in_desire_direction(self):
        agent = self._make_default(
            owned_env_keys=["revenue"],
            desires=[make_desire("Rev", "revenue", direction=1.0)],
            capabilities={"c": make_capability()},
            push_delta=0.05,
        )
        actions = agent.decide({"revenue": 0.5}, 1)
        assert len(actions) == 1
        assert actions[0].parameters["revenue"] == pytest.approx(0.05)

    def test_pushes_negative_direction(self):
        agent = self._make_default(
            owned_env_keys=["tension"],
            desires=[make_desire("Calm", "tension", direction=-1.0)],
            capabilities={"c": make_capability()},
            push_delta=0.05,
        )
        actions = agent.decide({"tension": 0.5}, 1)
        assert actions[0].parameters["tension"] == pytest.approx(-0.05)

    def test_skips_exhausted_capability(self):
        cap   = make_capability(cost=0.5, current=0.0)  # exhausted
        agent = self._make_default(
            owned_env_keys=["revenue"],
            desires=[make_desire("Rev", "revenue")],
            capabilities={"c": cap},
        )
        assert agent.decide({"revenue": 0.5}, 1) == []

    def test_action_id_contains_tick(self):
        agent = self._make_default(
            owned_env_keys=["revenue"],
            desires=[make_desire("Rev", "revenue")],
            capabilities={"c": make_capability()},
        )
        actions = agent.decide({}, 42)
        assert "42" in actions[0].action_id

    def test_from_spec_sets_owned_env_keys(self):
        from core.agents.base import DefaultBDIAgent
        spec = ActorSpec(
            name="Iran",
            initial_env_contributions={
                "iran__military_readiness": 0.7,
                "iran__oil_revenue": 0.4,
            },
        )
        agent = DefaultBDIAgent.from_spec(spec, make_rng(0))
        assert set(agent.owned_env_keys) == {"iran__military_readiness", "iran__oil_revenue"}

    def test_from_spec_returns_default_agent_instance(self):
        from core.agents.base import DefaultBDIAgent
        spec  = ActorSpec(name="Iran")
        agent = DefaultBDIAgent.from_spec(spec, make_rng(0))
        assert isinstance(agent, DefaultBDIAgent)

    def test_importable_from_core_agents(self):
        from core.agents import DefaultBDIAgent
        assert DefaultBDIAgent is not None


# ── __init__ exports ──────────────────────────────────────────────────────────

class TestCoreAgentsExports:
    def test_all_exports(self):
        from core.agents import (
            Action,
            AgentHydrationError,
            BDIAgent,
            BetaBelief,
            DefaultBDIAgent,
            GaussianBelief,
        )
        assert all([Action, AgentHydrationError, BDIAgent, BetaBelief,
                    DefaultBDIAgent, GaussianBelief])
