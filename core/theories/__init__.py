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


def load_theory_file(path: "str | Path") -> Type[TheoryBase] | None:
    """
    Hot-load a single theory module from an arbitrary file path.

    Imports the file as a fresh module, which fires any @register_theory
    decorators inside it. Call this after writing an approved theory to
    core/theories/discovered/ to make it available without a server restart.

    Args:
        path: Absolute path to a .py file containing a @register_theory class.

    Returns:
        The registered TheoryBase subclass, or None if already registered.

    Raises:
        ImportError:    if the file cannot be loaded.
        ValueError:     if the file contains no TheoryBase subclass.
    """
    import importlib.util
    import inspect
    from pathlib import Path as _Path

    path = _Path(path)
    module_name = f"_crucible_discovered_{path.stem}"

    if any(
        getattr(cls, "__module__", "").endswith(path.stem)
        for cls in _THEORY_REGISTRY.values()
    ):
        logger.debug("load_theory_file: %s already registered, skipping", path.stem)
        return None

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load theory file: {path}")

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)  # fires @register_theory
    except ValueError as exc:
        # Already registered — treat as a no-op (e.g. duplicate hot-load call)
        logger.warning("load_theory_file: %s", exc)
        return None

    # Return the newly registered class
    for cls in vars(module).values():
        if (
            inspect.isclass(cls)
            and issubclass(cls, TheoryBase)
            and cls is not TheoryBase
        ):
            return cls

    raise ValueError(f"No TheoryBase subclass found in {path}")


def _autodiscover() -> None:
    """Import every theory module so @register_theory decorators fire."""
    import importlib
    import pkgutil
    import core.theories as _pkg
    import core.theories.discovered as _discovered_pkg
    from pathlib import Path as _Path

    # Built-in theories
    for _mod in pkgutil.iter_modules(_pkg.__path__):
        if _mod.name not in ("base", "discovered"):
            importlib.import_module(f"core.theories.{_mod.name}")

    # Approved discovered theories — scan .py files directly so we pick up
    # modules written after the package was first imported
    _discovered_dir = _Path(_discovered_pkg.__file__).parent
    for _py in sorted(_discovered_dir.glob("*.py")):
        if _py.name == "__init__.py":
            continue
        try:
            load_theory_file(_py)
        except Exception as exc:
            logger.warning("_autodiscover: failed to load %s — %s", _py.name, exc)


_autodiscover()


# Lazy import for type hint only — avoids circular import at module level
from pathlib import Path  # noqa: E402  (used in load_theory_file signature)
