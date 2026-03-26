"""
core/theories/base.py — TheoryBase ABC and TheoryStateVariables

Every theory module:
  1. Inherits from TheoryBase
  2. Declares an inner Parameters(BaseModel) for Pydantic-validated params
  3. Declares state_variables (reads / writes / initializes)
  4. Implements update(env, agents, tick) -> dict[str, float]

update() is a pure function over the environment: read from env, return a
delta dict, never mutate env directly. SimRunner accumulates all deltas and
applies them once per tick, preventing ordering race conditions within a
priority bucket.

Key conventions:
  - env keys owned by this theory: "{theory_id}__{variable_name}"
  - actor-specific keys:           "{actor_id}__{variable_name}"
  - cross-theory globals:          "global__{variable_name}"
  - all values normalized to [0, 1]

Tick lifecycle (SimRunner):
    setup(env)          ← called once before tick loop; seeds initializes keys
    for tick in range:
        update(env, agents, tick)  ← pure; returns delta dict

    SimRunner merges delta back into env after all theories at the same
    priority level have run (order within a bucket is deterministic but
    should not be load-bearing).
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from core.agents.base import BDIAgent

logger = logging.getLogger(__name__)


@dataclass
class TheoryStateVariables:
    """
    Declares which environment keys this theory reads, writes, and initializes.

    SimRunner uses this at setup() to:
      - validate no two theories write the same key (collision detection)
      - seed the environment with initial values for keys this theory owns
        (only keys absent from initial_environment get seeded with 0.0)

    Attributes:
        reads:       keys this theory reads from env each tick
        writes:      keys this theory returns in the delta dict
        initializes: keys this theory will seed if absent from env at setup()
                     (subset of writes; order does not matter)
    """

    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    initializes: list[str] = field(default_factory=list)


class TheoryBase(ABC):
    """
    Abstract base for all Crucible theory modules.

    Subclass, override Parameters and state_variables, implement update().
    Use @register_theory("your_theory_id") to auto-register in the global
    registry so SimRunner can instantiate by string ID.

    Example:
        @register_theory("my_theory")
        class MyTheory(TheoryBase):
            class Parameters(BaseModel):
                alpha: float = Field(default=0.5, ge=0.0, le=1.0)

            @property
            def state_variables(self) -> TheoryStateVariables:
                return TheoryStateVariables(
                    reads=["some_actor__readiness"],
                    writes=["my_theory__output"],
                    initializes=["my_theory__output"],
                )

            def update(self, env, agents, tick):
                val = env.get("some_actor__readiness", 0.5)
                return {"my_theory__output": val * self.params.alpha}
    """

    theory_id: str = "base"

    class Parameters(BaseModel):
        """Override in subclasses to declare theory-specific parameters."""

        pass

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        """
        Args:
            parameters: dict of parameter overrides (passed via TheoryRef.parameters
                        in SimSpec). Keys must match the inner Parameters model.
        """
        self.params = self.Parameters(**(parameters or {}))
        logger.debug(
            "Theory '%s' initialized with params: %s",
            self.theory_id,
            self.params.model_dump(),
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        """
        Declare reads / writes / initializes for this theory.

        Override in subclasses. The default returns empty lists (safe but
        provides no env integration). SimRunner calls this at setup() to
        validate write-key uniqueness across all theories.
        """
        return TheoryStateVariables()

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        """
        Called once by SimRunner before the tick loop starts.

        Returns a dict of {key: 0.0} for every key in state_variables.initializes
        that is NOT already present in env. This lets SimSpec's
        initial_environment take precedence over theory defaults.

        Do not override unless you need non-zero initial values — in that case,
        override and call super().setup(env) first, then update the result.
        """
        inits: dict[str, float] = {}
        for key in self.state_variables.initializes:
            if key not in env:
                inits[key] = 0.0
                logger.debug("Theory '%s': seeding env key '%s' = 0.0", self.theory_id, key)
        return inits

    @abstractmethod
    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Core theory update. Called once per tick by SimRunner.

        Args:
            env:    current normalized environment (read-only by convention)
            agents: list of all active BDIAgent instances (read their beliefs,
                    not their owned env keys directly — prefer reading env)
            tick:   zero-based tick counter

        Returns:
            dict mapping env_key -> new_value for every key in state_variables.writes.
            Values must be in [0, 1]. SimRunner merges this delta into env after
            all theories at the same priority level have completed.

        Constraints:
            - Do NOT mutate env in place.
            - Only return keys declared in state_variables.writes.
            - Clamp outputs: max(0.0, min(1.0, value)).
        """
        ...

    def get_state_snapshot(self) -> dict[str, Any]:
        """Return serializable snapshot for logging / API responses."""
        return {
            "theory_id": self.theory_id,
            "parameters": self.params.model_dump(),
        }
