"""
api/catalog.py — Theory catalog introspection

Builds TheoryCatalogEntry objects from registered theory classes by reading:
  - cls.DOMAINS           → domains list
  - cls.Parameters        → parameter names, types, descriptions, defaults
  - cls.state_variables   → reads / writes / initializes
  - cls.__doc__           → description (first paragraph) + Reference: line
  - cls.__module__        → source ("builtin" | "discovered")

The catalog is built once at first call and cached. Call invalidate_cache()
after hot-loading a new theory (e.g. after approve()).
"""
from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field
from typing import Any

_catalog_cache: list["TheoryCatalogEntry"] | None = None


@dataclass
class ParameterInfo:
    name: str
    type: str
    description: str
    default: Any = None
    has_default: bool = True


@dataclass
class TheoryCatalogEntry:
    theory_id: str
    name: str
    domains: list[str]
    description: str
    reference: str
    parameters: list[ParameterInfo]
    reads: list[str]
    writes: list[str]
    initializes: list[str]
    source: str          # "builtin" | "discovered"
    parameter_count: int = 0

    def __post_init__(self):
        self.parameter_count = len(self.parameters)

    def to_dict(self) -> dict:
        return {
            "theory_id":       self.theory_id,
            "name":            self.name,
            "domains":         self.domains,
            "description":     self.description,
            "reference":       self.reference,
            "parameters":      [
                {
                    "name":        p.name,
                    "type":        p.type,
                    "description": p.description,
                    "default":     p.default,
                    "has_default": p.has_default,
                }
                for p in self.parameters
            ],
            "parameter_count": self.parameter_count,
            "reads":           self.reads,
            "writes":          self.writes,
            "initializes":     self.initializes,
            "source":          self.source,
        }

    def to_summary_dict(self) -> dict:
        """Lighter version for list endpoints — no reads/writes/initializes."""
        return {
            "theory_id":       self.theory_id,
            "name":            self.name,
            "domains":         self.domains,
            "description":     self.description[:200] + ("…" if len(self.description) > 200 else ""),
            "reference":       self.reference,
            "parameter_count": self.parameter_count,
            "source":          self.source,
        }


def _extract_description(docstring: str | None) -> str:
    """Return the first non-empty paragraph of a docstring."""
    if not docstring:
        return ""
    lines = inspect.cleandoc(docstring).splitlines()
    para: list[str] = []
    for line in lines:
        if line.strip() == "" and para:
            break
        if line.strip():
            para.append(line.strip())
    return " ".join(para)


def _extract_reference(docstring: str | None) -> str:
    """Extract the 'Reference: ...' line from a docstring."""
    if not docstring:
        return ""
    for line in docstring.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("reference:"):
            return stripped[len("reference:"):].strip()
    return ""


def _extract_parameters(cls) -> list[ParameterInfo]:
    """Introspect cls.Parameters (Pydantic BaseModel) for field info."""
    params_cls = getattr(cls, "Parameters", None)
    if params_cls is None:
        return []
    try:
        fields = params_cls.model_fields
    except AttributeError:
        return []

    result: list[ParameterInfo] = []
    for name, field_info in fields.items():
        annotation = params_cls.__annotations__.get(name, Any)
        # Get clean type name
        if hasattr(annotation, "__name__"):
            type_str = annotation.__name__
        else:
            type_str = str(annotation).replace("typing.", "")

        description = ""
        if field_info.description:
            description = field_info.description

        default = field_info.default
        has_default = default is not inspect.Parameter.empty and default is not None

        result.append(ParameterInfo(
            name=name,
            type=type_str,
            description=description,
            default=default if has_default else None,
            has_default=has_default,
        ))
    return result


def _extract_state_variables(cls) -> tuple[list[str], list[str], list[str]]:
    """Return (reads, writes, initializes) from cls.state_variables."""
    sv = getattr(cls, "state_variables", None)
    if sv is None:
        return [], [], []
    return (
        list(getattr(sv, "reads", [])),
        list(getattr(sv, "writes", [])),
        list(getattr(sv, "initializes", [])),
    )


def _class_to_name(cls) -> str:
    """Convert CamelCase class name to a display name, e.g. RichardsonArmsRace → Richardson Arms Race."""
    name = cls.__name__
    # Insert spaces before uppercase letters that follow lowercase
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    return spaced


def _build_entry(theory_id: str, cls) -> TheoryCatalogEntry:
    module = getattr(cls, "__module__", "")
    source = "discovered" if "discovered" in module else "builtin"

    docstring = cls.__doc__
    description = _extract_description(docstring)
    reference   = _extract_reference(docstring)
    domains     = list(getattr(cls, "DOMAINS", []))
    parameters  = _extract_parameters(cls)
    reads, writes, initializes = _extract_state_variables(cls)

    return TheoryCatalogEntry(
        theory_id   = theory_id,
        name        = _class_to_name(cls),
        domains     = domains,
        description = description,
        reference   = reference,
        parameters  = parameters,
        reads       = reads,
        writes      = writes,
        initializes = initializes,
        source      = source,
    )


def build_catalog() -> list[TheoryCatalogEntry]:
    """Build and cache the full theory catalog from the registry."""
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache

    from core.theories import list_theories, get_theory
    entries = []
    for tid in list_theories():
        try:
            cls = get_theory(tid)
            entries.append(_build_entry(tid, cls))
        except Exception:
            pass  # skip broken theory modules

    _catalog_cache = entries
    return entries


def invalidate_cache() -> None:
    """Clear the catalog cache. Call after hot-loading a new theory."""
    global _catalog_cache
    _catalog_cache = None


def get_entry(theory_id: str) -> TheoryCatalogEntry | None:
    """Return the catalog entry for a single theory, or None if not found."""
    for entry in build_catalog():
        if entry.theory_id == theory_id:
            return entry
    return None


# Domain → canonical theory IDs fast-path map (no API call needed)
DOMAIN_MAP: dict[str, list[str]] = {
    "geopolitics": [
        "richardson_arms_race",
        "fearon_bargaining",
        "wittman_zartman_ripeness",
        "prospect_theory",
        "selectorate_theory",
    ],
    "conflict": [
        "richardson_arms_race",
        "fearon_bargaining",
        "wittman_zartman_ripeness",
        "prospect_theory",
    ],
    "market": [
        "porters_five_forces",
        "cournot_bertrand_competition",
        "supply_demand_shock",
        "bass_diffusion",
        "hotelling_spatial_competition",
        "schumpeter_disruption",
    ],
    "corporate": [
        "principal_agent",
        "institutional_theory",
        "diffusion_of_innovation",
        "stakeholder_salience",
        "brand_equity_decay",
        "acquirer_discount",
        "event_study",
    ],
    "macro": [
        "keynesian_multiplier",
        "regulatory_shock_propagation",
        "is_lm_as_ad",
        "debt_sustainability",
        "input_output_leontief",
    ],
    "social": [
        "schelling_segregation",
        "opinion_dynamics",
        "sir_seir_contagion",
        "tipping_point_threshold",
    ],
    "technology": [
        "bass_diffusion",
        "schumpeter_disruption",
        "platform_tipping",
        "compute_efficiency",
        "narrative_contagion",
    ],
    "ecology": [
        "sir_seir_contagion",
        "schelling_segregation",
    ],
}
