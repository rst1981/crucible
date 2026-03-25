"""
Tests for core/agents/base.py

Covers:
- BetaBelief: mean, variance, update, sample
- GaussianBelief: mean, variance, update (Kalman), sample
- Action dataclass
- BDIAgent: observe_environment, update_beliefs, expected_utility,
  can_act, expend_capacity, recharge_capabilities, get_state_snapshot
- Thread-safe RNG (self.rng, not global random)
"""

import math
import random

import pytest

from core.agents.base import Action, BDIAgent, BetaBelief, GaussianBelief


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
        "capacity": capacity,
        "cost": cost,
        "recovery_rate": recovery_rate,
        "cooldown_ticks": cooldown_ticks,
        "current": current if current is not None else capacity,
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
    noise: float = 0.0,   # 0 noise by default makes assertions easy
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
        # bias=-0.5 should shift obs=1.0 → 0.5
        b.update(1.0, precision=1.0, bias=-0.5)
        assert b.alpha == pytest.approx(1.5)
        assert b.beta  == pytest.approx(1.5)

    def test_update_clamps_adjusted_to_01(self):
        b = BetaBelief("coop", alpha=1.0, beta=1.0)
        # obs=0.8 + bias=0.5 → 1.3, clamped to 1.0
        b.update(0.8, bias=0.5)
        assert b.alpha == pytest.approx(2.0)
        assert b.beta  == pytest.approx(1.0)

    def test_update_clamps_below_zero(self):
        b = BetaBelief("coop", alpha=1.0, beta=1.0)
        b.update(0.2, bias=-0.5)  # 0.2 - 0.5 = -0.3 → 0.0
        assert b.alpha == pytest.approx(1.0)
        assert b.beta  == pytest.approx(2.0)

    def test_sample_in_range(self):
        rng = make_rng(1)
        b = BetaBelief("coop", alpha=2.0, beta=2.0)
        samples = [b.sample(rng) for _ in range(200)]
        assert all(0.0 <= s <= 1.0 for s in samples)

    def test_sample_mean_approx(self):
        rng = make_rng(1)
        b = BetaBelief("coop", alpha=5.0, beta=1.0)  # mean = 5/6 ≈ 0.833
        samples = [b.sample(rng) for _ in range(500)]
        assert abs(sum(samples) / len(samples) - b.mean) < 0.05

    def test_deterministic_with_same_rng_seed(self):
        b = BetaBelief("x", alpha=2.0, beta=3.0)
        s1 = b.sample(make_rng(42))
        s2 = b.sample(make_rng(42))
        assert s1 == s2


# ── GaussianBelief ────────────────────────────────────────────────────────────

class TestGaussianBelief:
    def test_defaults(self):
        g = GaussianBelief("gdp")
        assert g.mean == 0.0
        assert g.variance == 1.0

    def test_kalman_update_moves_mean_toward_obs(self):
        g = GaussianBelief("gdp", mean=0.0, variance=1.0)
        g.update(1.0, obs_variance=1.0)
        # kalman_gain = 1/(1+1) = 0.5 → mean = 0 + 0.5*(1-0) = 0.5
        assert g.mean == pytest.approx(0.5)

    def test_kalman_update_reduces_variance(self):
        g = GaussianBelief("gdp", mean=0.0, variance=1.0)
        v_before = g.variance
        g.update(0.5, obs_variance=1.0)
        assert g.variance < v_before

    def test_kalman_variance_formula(self):
        g = GaussianBelief("gdp", mean=0.0, variance=1.0)
        g.update(1.0, obs_variance=1.0)
        # variance = (1 - 0.5) * 1.0 = 0.5
        assert g.variance == pytest.approx(0.5)

    def test_high_obs_variance_small_update(self):
        """Very noisy observation → tiny update."""
        g = GaussianBelief("gdp", mean=0.0, variance=0.1)
        g.update(1.0, obs_variance=1000.0)
        assert g.mean == pytest.approx(0.0, abs=0.01)

    def test_low_obs_variance_big_update(self):
        """Very precise observation → large update."""
        g = GaussianBelief("gdp", mean=0.0, variance=1.0)
        g.update(1.0, obs_variance=0.0001)
        assert g.mean == pytest.approx(1.0, abs=0.01)

    def test_sample_returns_float(self):
        rng = make_rng(0)
        g = GaussianBelief("gdp", mean=0.5, variance=0.01)
        s = g.sample(rng)
        assert isinstance(s, float)

    def test_sample_variance_zero_edge(self):
        """Variance approaching 0 → sample ≈ mean (no crash)."""
        rng = make_rng(0)
        g = GaussianBelief("gdp", mean=0.5, variance=0.0)
        s = g.sample(rng)
        assert s == pytest.approx(0.5)

    def test_repeated_updates_converge(self):
        g = GaussianBelief("gdp", mean=0.0, variance=1.0)
        for _ in range(50):
            g.update(0.8, obs_variance=0.1)
        assert g.mean == pytest.approx(0.8, abs=0.05)


# ── Action ────────────────────────────────────────────────────────────────────

class TestAction:
    def test_construction(self):
        a = Action("act1", "environment", 0.5)
        assert a.action_id == "act1"
        assert a.target == "environment"
        assert a.intensity == 0.5
        assert a.capability_id is None
        assert a.parameters == {}
        assert a.description == ""

    def test_with_capability(self):
        a = Action("act2", "iran", -0.3, capability_id="naval", parameters={"tension": 0.1})
        assert a.capability_id == "naval"
        assert a.parameters["tension"] == 0.1


# ── BDIAgent: construction ────────────────────────────────────────────────────

class TestBDIAgentConstruction:
    def test_defaults(self):
        agent = make_agent()
        assert agent.actor_id == "a1"
        assert agent.name == "Iran"
        assert agent.beliefs == {}
        assert agent.desires == []
        assert agent.capabilities == {}
        assert agent.observation_noise_sigma == 0.0
        assert isinstance(agent.rng, random.Random)

    def test_rng_injection(self):
        rng = make_rng(99)
        agent = make_agent(rng=rng)
        assert agent.rng is rng

    def test_default_rng_created_when_none(self):
        agent = make_agent(rng=None)
        assert isinstance(agent.rng, random.Random)


# ── BDIAgent: observe_environment ────────────────────────────────────────────

class TestObserveEnvironment:
    def test_returns_dict_with_same_keys(self):
        agent = make_agent(noise=0.0)
        env = {"tension": 0.5, "readiness": 0.7}
        obs = agent.observe_environment(env)
        assert set(obs.keys()) == set(env.keys())

    def test_zero_noise_returns_exact_values(self):
        agent = make_agent(noise=0.0)
        env = {"tension": 0.5, "readiness": 0.7}
        obs = agent.observe_environment(env)
        assert obs["tension"]   == pytest.approx(0.5)
        assert obs["readiness"] == pytest.approx(0.7)

    def test_stores_observations(self):
        agent = make_agent(noise=0.0)
        env = {"tension": 0.5}
        agent.observe_environment(env)
        assert agent._observations["tension"] == pytest.approx(0.5)

    def test_clamps_to_0_1(self):
        # With positive noise, values near edges can exceed [0,1]
        rng = make_rng(7)
        agent = make_agent(noise=0.5, rng=rng)
        env = {"x": 0.99, "y": 0.01}
        for _ in range(30):
            obs = agent.observe_environment(env)
            for v in obs.values():
                assert 0.0 <= v <= 1.0

    def test_noisy_observations_differ_from_truth(self):
        agent = make_agent(noise=0.1, rng=make_rng(5))
        env = {"tension": 0.5}
        results = [agent.observe_environment(env)["tension"] for _ in range(20)]
        assert not all(r == pytest.approx(0.5) for r in results)

    def test_deterministic_with_same_seed(self):
        env = {"tension": 0.5}
        a1 = make_agent(noise=0.05, rng=make_rng(42))
        a2 = make_agent(noise=0.05, rng=make_rng(42))
        obs1 = a1.observe_environment(env)
        obs2 = a2.observe_environment(env)
        assert obs1["tension"] == pytest.approx(obs2["tension"])


# ── BDIAgent: update_beliefs ─────────────────────────────────────────────────

class TestUpdateBeliefs:
    def test_beta_belief_updated_from_observations(self):
        belief = BetaBelief("tension", alpha=1.0, beta=1.0)
        agent  = make_agent(beliefs={"tension": belief})
        agent._observations = {"tension": 0.9}
        agent.update_beliefs()
        assert belief.alpha > 1.0

    def test_gaussian_belief_updated_from_observations(self):
        belief = GaussianBelief("gdp", mean=0.0, variance=1.0)
        agent  = make_agent(beliefs={"gdp": belief})
        agent._observations = {"gdp": 0.8}
        agent.update_beliefs()
        assert belief.mean != 0.0

    def test_unmatched_belief_unchanged(self):
        belief = BetaBelief("coop", alpha=1.0, beta=1.0)
        agent  = make_agent(beliefs={"coop": belief})
        agent._observations = {"tension": 0.9}  # different key
        agent.update_beliefs()
        assert belief.alpha == pytest.approx(1.0)
        assert belief.beta  == pytest.approx(1.0)

    def test_explicit_observations_override_stored(self):
        belief = BetaBelief("tension", alpha=1.0, beta=1.0)
        agent  = make_agent(beliefs={"tension": belief})
        agent._observations = {"tension": 0.0}
        agent.update_beliefs(observations={"tension": 1.0})  # override
        assert belief.alpha > belief.beta  # high observation → more alpha


# ── BDIAgent: expected_utility ────────────────────────────────────────────────

class TestExpectedUtility:
    def test_single_desire_maximize(self):
        desires = [{"target_env_key": "revenue", "direction": 1.0, "weight": 1.0}]
        agent   = make_agent(desires=desires)
        eu      = agent.expected_utility({"revenue": 0.8})
        assert eu == pytest.approx(0.8)

    def test_single_desire_minimize(self):
        desires = [{"target_env_key": "tension", "direction": -1.0, "weight": 1.0}]
        agent   = make_agent(desires=desires)
        eu      = agent.expected_utility({"tension": 0.6})
        assert eu == pytest.approx(-0.6)

    def test_weighted_sum(self):
        desires = [
            {"target_env_key": "revenue",  "direction":  1.0, "weight": 2.0},
            {"target_env_key": "tension",  "direction": -1.0, "weight": 1.0},
        ]
        agent = make_agent(desires=desires)
        eu    = agent.expected_utility({"revenue": 0.5, "tension": 0.4})
        assert eu == pytest.approx(2.0 * 0.5 + 1.0 * -1.0 * 0.4)

    def test_missing_env_key_treated_as_zero(self):
        desires = [{"target_env_key": "nonexistent", "direction": 1.0, "weight": 1.0}]
        agent   = make_agent(desires=desires)
        eu      = agent.expected_utility({})
        assert eu == pytest.approx(0.0)

    def test_no_desires_zero_utility(self):
        agent = make_agent()
        assert agent.expected_utility({"tension": 0.9}) == pytest.approx(0.0)


# ── BDIAgent: can_act ─────────────────────────────────────────────────────────

class TestCanAct:
    def test_full_capacity_no_cooldown(self):
        agent = make_agent(capabilities={"naval": make_capability(capacity=1.0, cost=0.2, current=1.0)})
        assert agent.can_act("naval") is True

    def test_insufficient_capacity(self):
        agent = make_agent(capabilities={"naval": make_capability(capacity=1.0, cost=0.5, current=0.1)})
        assert agent.can_act("naval") is False

    def test_on_cooldown(self):
        cap = make_capability(capacity=1.0, cost=0.2, current=1.0, cooldown_remaining=3)
        agent = make_agent(capabilities={"naval": cap})
        assert agent.can_act("naval") is False

    def test_unknown_capability(self):
        agent = make_agent()
        assert agent.can_act("nonexistent") is False

    def test_exact_capacity_boundary(self):
        cap = make_capability(capacity=1.0, cost=0.5, current=0.5)
        agent = make_agent(capabilities={"naval": cap})
        assert agent.can_act("naval") is True


# ── BDIAgent: expend_capacity ─────────────────────────────────────────────────

class TestExpendCapacity:
    def test_returns_true_and_reduces_capacity(self):
        cap   = make_capability(capacity=1.0, cost=0.3, current=1.0)
        agent = make_agent(capabilities={"naval": cap})
        result = agent.expend_capacity("naval")
        assert result is True
        assert cap["current"] == pytest.approx(0.7)

    def test_returns_false_when_cannot_act(self):
        cap   = make_capability(capacity=1.0, cost=0.5, current=0.1)
        agent = make_agent(capabilities={"naval": cap})
        result = agent.expend_capacity("naval")
        assert result is False
        assert cap["current"] == pytest.approx(0.1)  # unchanged

    def test_starts_cooldown(self):
        cap   = make_capability(capacity=1.0, cost=0.1, current=1.0, cooldown_ticks=3)
        agent = make_agent(capabilities={"naval": cap})
        agent.expend_capacity("naval")
        assert cap["cooldown_remaining"] == 3

    def test_cannot_act_twice_when_exhausted(self):
        cap   = make_capability(capacity=0.3, cost=0.3, current=0.3)
        agent = make_agent(capabilities={"naval": cap})
        assert agent.expend_capacity("naval") is True
        assert agent.expend_capacity("naval") is False


# ── BDIAgent: recharge_capabilities ──────────────────────────────────────────

class TestRechargeCapabilities:
    def test_recovers_capacity(self):
        cap   = make_capability(capacity=1.0, cost=0.5, current=0.2, recovery_rate=0.1)
        agent = make_agent(capabilities={"naval": cap})
        agent.recharge_capabilities()
        assert cap["current"] == pytest.approx(0.3)

    def test_does_not_exceed_max(self):
        cap   = make_capability(capacity=1.0, current=0.95, recovery_rate=0.1)
        agent = make_agent(capabilities={"naval": cap})
        agent.recharge_capabilities()
        assert cap["current"] == pytest.approx(1.0)

    def test_decrements_cooldown(self):
        cap   = make_capability(capacity=1.0, current=1.0, cooldown_remaining=5)
        agent = make_agent(capabilities={"naval": cap})
        agent.recharge_capabilities()
        assert cap["cooldown_remaining"] == 4

    def test_cooldown_does_not_go_below_zero(self):
        cap   = make_capability(capacity=1.0, current=1.0, cooldown_remaining=0)
        agent = make_agent(capabilities={"naval": cap})
        agent.recharge_capabilities()
        assert cap["cooldown_remaining"] == 0

    def test_full_cycle_expend_then_recharge(self):
        cap = make_capability(capacity=1.0, cost=0.5, current=1.0,
                              recovery_rate=0.5, cooldown_ticks=2)
        agent = make_agent(capabilities={"naval": cap})
        agent.expend_capacity("naval")
        assert cap["current"] == pytest.approx(0.5)
        assert cap["cooldown_remaining"] == 2
        agent.recharge_capabilities()
        assert cap["current"] == pytest.approx(1.0)  # recovered back to max
        assert cap["cooldown_remaining"] == 1


# ── BDIAgent: get_state_snapshot ─────────────────────────────────────────────

class TestGetStateSnapshot:
    def test_basic_structure(self):
        agent = make_agent()
        snap  = agent.get_state_snapshot()
        assert snap["actor_id"] == "a1"
        assert snap["name"]     == "Iran"
        assert "beliefs"      in snap
        assert "capabilities" in snap

    def test_beta_belief_in_snapshot(self):
        belief = BetaBelief("coop", alpha=3.0, beta=1.0)
        agent  = make_agent(beliefs={"coop": belief})
        snap   = agent.get_state_snapshot()
        assert snap["beliefs"]["coop"]["alpha"] == pytest.approx(3.0)
        assert snap["beliefs"]["coop"]["mean"]  == pytest.approx(0.75)

    def test_gaussian_belief_in_snapshot(self):
        belief = GaussianBelief("gdp", mean=0.5, variance=0.1)
        agent  = make_agent(beliefs={"gdp": belief})
        snap   = agent.get_state_snapshot()
        assert snap["beliefs"]["gdp"]["mean"]     == pytest.approx(0.5)
        assert snap["beliefs"]["gdp"]["variance"] == pytest.approx(0.1)
        assert "alpha" not in snap["beliefs"]["gdp"]

    def test_capability_in_snapshot(self):
        cap   = make_capability(capacity=1.0, cost=0.2, current=0.8)
        agent = make_agent(capabilities={"naval": cap})
        snap  = agent.get_state_snapshot()
        assert snap["capabilities"]["naval"]["current"] == pytest.approx(0.8)

    def test_snapshot_is_serializable(self):
        import json
        belief = BetaBelief("coop", alpha=2.0, beta=2.0)
        cap    = make_capability()
        agent  = make_agent(beliefs={"coop": belief}, capabilities={"naval": cap})
        snap   = agent.get_state_snapshot()
        json.dumps(snap)  # should not raise


# ── Thread-safe RNG ───────────────────────────────────────────────────────────

class TestThreadSafeRng:
    """
    Verify that two agents seeded identically produce identical results,
    and differently-seeded agents diverge. This is the core guarantee
    that makes EnsembleRunner reproducible.
    """

    def test_same_seed_same_observations(self):
        env = {"tension": 0.5, "readiness": 0.7}
        a1  = make_agent(noise=0.05, rng=make_rng(42))
        a2  = make_agent(noise=0.05, rng=make_rng(42))
        obs1 = a1.observe_environment(env)
        obs2 = a2.observe_environment(env)
        for key in env:
            assert obs1[key] == pytest.approx(obs2[key])

    def test_different_seeds_different_observations(self):
        env  = {"tension": 0.5}
        a1   = make_agent(noise=0.1, rng=make_rng(1))
        a2   = make_agent(noise=0.1, rng=make_rng(2))
        obs1 = a1.observe_environment(env)
        obs2 = a2.observe_environment(env)
        assert obs1["tension"] != pytest.approx(obs2["tension"])

    def test_rng_not_global(self):
        """Agents use self.rng, so global random state is not touched."""
        global_state_before = random.getstate()
        agent = make_agent(noise=0.05, rng=make_rng(99))
        env   = {"x": 0.5}
        for _ in range(20):
            agent.observe_environment(env)
        global_state_after = random.getstate()
        assert global_state_before == global_state_after
