"""
Tests for core/theories/base.py and core/theories/__init__.py (registry).
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from core.theories import (
    TheoryBase,
    TheoryStateVariables,
    get_theory,
    list_theories,
    register_theory,
    _THEORY_REGISTRY,
)
from core.theories.base import TheoryStateVariables as TheoryStateVariablesBase


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_concrete_theory(tid: str = "_test_noop") -> type[TheoryBase]:
    """Create a minimal concrete theory class without polluting the registry."""

    class _Noop(TheoryBase):
        def update(self, env, agents, tick):
            return {}

    _Noop.theory_id = tid
    return _Noop


# ── TheoryStateVariables ──────────────────────────────────────────────────────

class TestTheoryStateVariables:
    def test_defaults_are_empty_lists(self):
        sv = TheoryStateVariables()
        assert sv.reads == []
        assert sv.writes == []
        assert sv.initializes == []

    def test_construction_with_values(self):
        sv = TheoryStateVariables(
            reads=["actor_a__x"],
            writes=["theory__y"],
            initializes=["theory__y"],
        )
        assert "actor_a__x" in sv.reads
        assert "theory__y" in sv.writes
        assert "theory__y" in sv.initializes

    def test_imported_from_both_locations(self):
        # Should be the same class regardless of import path
        assert TheoryStateVariables is TheoryStateVariablesBase


# ── TheoryBase ────────────────────────────────────────────────────────────────

class TestTheoryBase:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            TheoryBase()  # update() is abstract

    def test_concrete_subclass_instantiates(self):
        Noop = _make_concrete_theory()
        t = Noop()
        assert t is not None

    def test_default_parameters_empty(self):
        Noop = _make_concrete_theory()
        t = Noop()
        assert t.params.model_dump() == {}

    def test_parameters_override_accepted(self):
        class WithParam(TheoryBase):
            class Parameters(BaseModel):
                alpha: float = 0.5

            def update(self, env, agents, tick):
                return {}

        t = WithParam(parameters={"alpha": 0.9})
        assert t.params.alpha == 0.9

    def test_parameters_override_invalid_rejected(self):
        class WithBounded(TheoryBase):
            class Parameters(BaseModel):
                alpha: float = Field(default=0.5, ge=0.0, le=1.0)

            def update(self, env, agents, tick):
                return {}

        with pytest.raises(Exception):
            WithBounded(parameters={"alpha": 99.0})

    def test_state_variables_default_empty(self):
        Noop = _make_concrete_theory()
        sv = Noop().state_variables
        assert sv.reads == []
        assert sv.writes == []
        assert sv.initializes == []

    def test_setup_seeds_missing_keys(self):
        class WithInits(TheoryBase):
            @property
            def state_variables(self):
                return TheoryStateVariables(initializes=["theory__val"])

            def update(self, env, agents, tick):
                return {}

        t = WithInits()
        inits = t.setup({})
        assert inits == {"theory__val": 0.0}

    def test_setup_does_not_overwrite_existing_env(self):
        class WithInits(TheoryBase):
            @property
            def state_variables(self):
                return TheoryStateVariables(initializes=["theory__val"])

            def update(self, env, agents, tick):
                return {}

        t = WithInits()
        inits = t.setup({"theory__val": 0.7})
        assert "theory__val" not in inits

    def test_setup_empty_initializes_returns_empty(self):
        Noop = _make_concrete_theory()
        inits = Noop().setup({"anything": 1.0})
        assert inits == {}

    def test_get_state_snapshot(self):
        Noop = _make_concrete_theory()
        snap = Noop().get_state_snapshot()
        assert "theory_id" in snap
        assert "parameters" in snap

    def test_update_pure_does_not_mutate_env(self):
        class MutationTest(TheoryBase):
            def update(self, env, agents, tick):
                # Theory should return delta, not mutate env
                return {"theory__x": 0.9}

        t = MutationTest()
        env = {"theory__x": 0.1}
        t.update(env, [], 0)
        # env must not be mutated
        assert env["theory__x"] == 0.1


# ── Registry ──────────────────────────────────────────────────────────────────

class TestRegistry:
    def test_register_theory_sets_theory_id(self):
        @register_theory("_test_reg_id_check")
        class _T(TheoryBase):
            def update(self, env, agents, tick):
                return {}

        try:
            assert _T.theory_id == "_test_reg_id_check"
        finally:
            _THEORY_REGISTRY.pop("_test_reg_id_check", None)

    def test_get_theory_returns_class(self):
        @register_theory("_test_get_cls")
        class _T(TheoryBase):
            def update(self, env, agents, tick):
                return {}

        try:
            cls = get_theory("_test_get_cls")
            assert cls is _T
        finally:
            _THEORY_REGISTRY.pop("_test_get_cls", None)

    def test_get_theory_unknown_raises_keyerror(self):
        with pytest.raises(KeyError, match="not registered"):
            get_theory("_definitely_does_not_exist_xyz")

    def test_list_theories_sorted(self):
        theories = list_theories()
        assert theories == sorted(theories)

    def test_duplicate_registration_raises(self):
        @register_theory("_test_dup")
        class _A(TheoryBase):
            def update(self, env, agents, tick):
                return {}

        try:
            with pytest.raises(ValueError, match="already registered"):
                @register_theory("_test_dup")
                class _B(TheoryBase):
                    def update(self, env, agents, tick):
                        return {}
        finally:
            _THEORY_REGISTRY.pop("_test_dup", None)

    def test_register_returns_original_class(self):
        @register_theory("_test_transparent")
        class _T(TheoryBase):
            custom_attr = 42

            def update(self, env, agents, tick):
                return {}

        try:
            assert _T.custom_attr == 42
            assert _T.theory_id == "_test_transparent"
        finally:
            _THEORY_REGISTRY.pop("_test_transparent", None)

    def test_instantiate_via_registry(self):
        @register_theory("_test_instantiate")
        class _T(TheoryBase):
            def update(self, env, agents, tick):
                return {"_test__val": 0.5}

        try:
            cls = get_theory("_test_instantiate")
            instance = cls()
            delta = instance.update({}, [], 0)
            assert delta == {"_test__val": 0.5}
        finally:
            _THEORY_REGISTRY.pop("_test_instantiate", None)
