"""
core/theories/__init__.py — Theory registry

Auto-discovery pattern: importing a theory module registers it. SimRunner
never needs a manual registry list — it imports theories by ID string via
get_theory(), and the import itself triggers @register_theory.

Usage:
    from core.theories import get_theory, list_theories, register_theory

    # Instantiate a theory by ID (SimRunner does this from TheoryRef):
    cls = get_theory("richardson_arms_race")
    theory = cls(parameters={"k": 0.4, "l": 0.35})

    # Register a new theory (applied as class decorator in the theory module):
    @register_theory("my_theory")
    class MyTheory(TheoryBase):
        ...
"""
from __future__ import annotations

from typing import Callable, Type

from core.theories.base import TheoryBase, TheoryStateVariables

_THEORY_REGISTRY: dict[str, Type[TheoryBase]] = {}


def register_theory(theory_id: str) -> Callable[[Type[TheoryBase]], Type[TheoryBase]]:
    """
    Class decorator. Registers the theory class under ``theory_id``.

    Sets ``cls.theory_id = theory_id`` on the class so instances can
    identify themselves without reading the registry.

    Args:
        theory_id: unique string key, e.g. "richardson_arms_race".
                   Must match the ``theory_id`` field in TheoryRef.

    Returns:
        The unmodified class (decorator is transparent at runtime).

    Raises:
        ValueError: if ``theory_id`` is already registered (prevents
                    silent overwrites from duplicate imports).

    Example:
        @register_theory("richardson_arms_race")
        class RichardsonArmsRace(TheoryBase):
            ...
    """

    def decorator(cls: Type[TheoryBase]) -> Type[TheoryBase]:
        if theory_id in _THEORY_REGISTRY:
            raise ValueError(
                f"Theory '{theory_id}' is already registered by "
                f"{_THEORY_REGISTRY[theory_id].__qualname__}. "
                f"Cannot register {cls.__qualname__} under the same ID."
            )
        cls.theory_id = theory_id
        _THEORY_REGISTRY[theory_id] = cls
        return cls

    return decorator


def get_theory(theory_id: str) -> Type[TheoryBase]:
    """
    Retrieve a registered theory class by ID.

    Args:
        theory_id: the key used in @register_theory and TheoryRef.theory_id

    Returns:
        The theory class (not an instance — caller instantiates with parameters).

    Raises:
        KeyError: if theory_id is not registered. Imports the module first if
                  you're seeing unexpected KeyErrors — auto-discovery requires
                  the module to be imported before get_theory() is called.
    """
    if theory_id not in _THEORY_REGISTRY:
        raise KeyError(
            f"Theory '{theory_id}' not registered. "
            f"Available: {list(_THEORY_REGISTRY.keys())}. "
            f"Did you import the theory module?"
        )
    return _THEORY_REGISTRY[theory_id]


def list_theories() -> list[str]:
    """Return sorted list of all registered theory IDs."""
    return sorted(_THEORY_REGISTRY.keys())


__all__ = [
    "TheoryBase",
    "TheoryStateVariables",
    "register_theory",
    "get_theory",
    "list_theories",
]


def _autodiscover() -> None:
    """Import every theory module so @register_theory decorators fire."""
    import importlib
    import pkgutil
    import core.theories as _pkg
    for _mod in pkgutil.iter_modules(_pkg.__path__):
        if _mod.name not in ("base",):
            importlib.import_module(f"core.theories.{_mod.name}")

_autodiscover()
