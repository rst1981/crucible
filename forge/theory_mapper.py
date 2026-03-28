"""
forge/theory_mapper.py — Maps scenario domain + description → theory ensemble.

TheoryMapper scores all registered theories (built-ins + approved discovered)
against a scenario domain and free-text description, then returns a ranked
ensemble recommendation.

The scoping agent calls this once a SimSpec domain and description are known.
The EnsembleBuilder UI surfaces the top-N as the "Claude recommends" panel,
letting the consultant accept, swap, or augment before launching.

Scoring is deterministic and purely rule-based (no API call):
  - Domain exact match:  scenario.domain in theory.DOMAINS              × 0.45
  - Domain token overlap: shared tokens between scenario domain and DOMAINS × 0.35
  - Description overlap:  shared tokens between description and DOMAINS     × 0.20

Usage:
    mapper = TheoryMapper()
    recs = mapper.recommend(domain="geopolitics conflict", description="...", n=5)
    for r in recs:
        print(r.theory_id, f"{r.score:.2f}", r.rationale)

    # With a SimSpec:
    recs = mapper.recommend_from_spec(spec, n=6)
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Type

from core.theories import get_theory, list_theories
from core.theories.base import TheoryBase

if TYPE_CHECKING:
    from core.spec import SimSpec

logger = logging.getLogger(__name__)

# Tokens to ignore when scoring description overlap
_STOP_WORDS = frozenset({
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or", "but",
    "with", "from", "by", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "it", "its", "how", "what", "which",
    "will", "would", "could", "should", "may", "might", "model", "models",
    "market", "over", "after", "due", "following", "under", "new",
})


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class TheoryRecommendation:
    theory_id: str
    display_name: str
    domains: list[str]
    score: float             # 0.0 – 1.0; higher = more relevant
    rationale: str           # one sentence explaining the score
    suggested_priority: int  # suggested priority in cascade (lower = runs first)
    source: str              # "builtin" | "discovered"


# ── Scorer ────────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    tokens = re.split(r"[\s,_\-/|+.]+", text.lower())
    return {t for t in tokens if t and t not in _STOP_WORDS and len(t) > 2}


def _score_theory(
    theory_class: Type[TheoryBase],
    domain_tokens: set[str],
    desc_tokens: set[str],
    domain_raw: str,
) -> tuple[float, str]:
    """Return (score, rationale) for one theory against a scenario."""
    domains: list[str] = getattr(theory_class, "DOMAINS", [])
    if not domains:
        return 0.0, "No DOMAINS defined"

    # Flatten all theory domain strings into one token set
    theory_tokens: set[str] = set()
    for d in domains:
        theory_tokens.update(_tokenize(d))
    theory_tokens.update(_tokenize(theory_class.theory_id))

    # 1. Exact domain match
    exact = 1.0 if domain_raw.lower() in [d.lower() for d in domains] else 0.0

    # 2. Domain token overlap (scenario domain ↔ theory DOMAINS)
    if domain_tokens:
        domain_overlap = len(domain_tokens & theory_tokens) / len(domain_tokens)
    else:
        domain_overlap = 0.0

    # 3. Description token overlap (scenario description ↔ theory DOMAINS)
    if theory_tokens:
        desc_overlap = len(desc_tokens & theory_tokens) / len(theory_tokens)
    else:
        desc_overlap = 0.0

    score = 0.45 * exact + 0.35 * domain_overlap + 0.20 * desc_overlap
    score = min(1.0, score)

    # Build rationale
    if score == 0.0:
        rationale = f"No overlap with scenario domain '{domain_raw}'"
    else:
        matched = sorted(domain_tokens & theory_tokens | desc_tokens & theory_tokens)[:4]
        rationale = (
            f"Matched on: {', '.join(matched)}" if matched
            else f"Partial domain overlap with {domains[0]}"
        )
        if exact:
            rationale = f"Direct domain match ({domain_raw}) + " + rationale

    return score, rationale


def _suggest_priority(theory_id: str, score: float, rank: int) -> int:
    """
    Suggest a cascade priority based on theory type and rank.

    Lower priority number = runs first. Rough tiers:
      0 — macro/contagion foundations (SIR, Keynesian, IS-LM, Solow)
      1 — market structure (Porter, Cournot, Stackelberg, Lotka-Volterra)
      2 — entity-level shocks (regulatory_shock, acquirer_discount, brand_equity)
      3 — innovation/disruption (Schumpeter, Bass, Fisher-Pry)
      4 — event/measurement (event_study, opinion_dynamics)
    """
    tier_map = {
        "sir_contagion": 0, "keynesian_multiplier": 0, "is_lm": 0,
        "solow_growth": 0, "minsky_instability": 0, "richardson_arms_race": 0,
        "porter_five_forces": 1, "cournot_oligopoly": 1, "stackelberg_leadership": 1,
        "lotka_volterra": 1, "cobweb_market": 1,
        "regulatory_shock": 2, "acquirer_discount": 2, "brand_equity_decay": 2,
        "principal_agent": 2, "efficiency_wages": 2, "hotelling_cpr": 2,
        "schumpeter_disruption": 3, "bass_diffusion": 3, "fisher_pry": 3,
        "experience_curve": 3,
        "event_study": 4, "opinion_dynamics": 4,
        "fearon_bargaining": 1, "wittman_zartman": 2,
    }
    return tier_map.get(theory_id, min(3, rank // 2))


# ── TheoryMapper ──────────────────────────────────────────────────────────────

class TheoryMapper:
    """
    Maps scenario domain + description to a ranked theory ensemble.

    All registered theories are scored — both built-ins and approved discovered
    theories are in the same registry and treated identically.
    """

    def recommend(
        self,
        domain: str,
        description: str = "",
        n: int = 6,
        min_score: float = 0.05,
    ) -> list[TheoryRecommendation]:
        """
        Return the top-N theory recommendations for a scenario.

        Args:
            domain:      Scenario domain string, e.g. "geopolitics" or
                         "corporate_finance equity mergers_acquisitions"
            description: Free-text scenario description for keyword matching.
            n:           Maximum number of recommendations to return.
            min_score:   Minimum score threshold (filters noise).

        Returns:
            List of TheoryRecommendation sorted by score descending.
        """
        domain_tokens = _tokenize(domain)
        desc_tokens = _tokenize(description)

        scored: list[tuple[float, str, str]] = []  # (score, theory_id, rationale)
        for theory_id in list_theories():
            try:
                cls = get_theory(theory_id)
            except KeyError:
                continue
            score, rationale = _score_theory(cls, domain_tokens, desc_tokens, domain)
            if score >= min_score:
                scored.append((score, theory_id, rationale))

        scored.sort(key=lambda x: x[0], reverse=True)
        scored = scored[:n]

        results = []
        for rank, (score, theory_id, rationale) in enumerate(scored):
            cls = get_theory(theory_id)
            domains = getattr(cls, "DOMAINS", [])
            # Determine provenance
            module = getattr(cls, "__module__", "")
            source = "discovered" if "discovered" in module else "builtin"
            results.append(
                TheoryRecommendation(
                    theory_id=theory_id,
                    display_name=_display_name(theory_id),
                    domains=domains,
                    score=round(score, 3),
                    rationale=rationale,
                    suggested_priority=_suggest_priority(theory_id, score, rank),
                    source=source,
                )
            )

        logger.info(
            "TheoryMapper: domain=%r → %d recommendations (top: %s %.2f)",
            domain,
            len(results),
            results[0].theory_id if results else "none",
            results[0].score if results else 0.0,
        )
        return results

    def recommend_from_spec(self, spec: "SimSpec", n: int = 6) -> list[TheoryRecommendation]:
        """Convenience wrapper — extracts domain and description from a SimSpec.

        Augments description with outcome_focus and transmission channels from metadata
        so that even if the agent sets domain='geopolitics' for a supply-chain scenario,
        the description tokens still drive theory selection toward the right models.
        """
        meta = spec.metadata or {}
        outcome = meta.get("outcome_focus", "")
        channels = " ".join(meta.get("transmission_channels", []))
        description = " ".join(filter(None, [spec.description, outcome, channels]))
        return self.recommend(
            domain=spec.domain,
            description=description,
            n=n,
        )

    def explain(self, domain: str, description: str = "") -> str:
        """
        Return a markdown summary of recommendations — useful for the scoping agent
        to include in its handoff message to the consultant.
        """
        recs = self.recommend(domain=domain, description=description, n=8, min_score=0.0)
        lines = [
            f"## Theory Recommendations for domain: `{domain}`\n",
            "| Priority | Theory | Score | Domains | Rationale |",
            "|----------|--------|-------|---------|-----------|",
        ]
        for r in recs:
            domains_str = ", ".join(r.domains[:3])
            source_tag = " *(discovered)*" if r.source == "discovered" else ""
            lines.append(
                f"| {r.suggested_priority} | **{r.display_name}**{source_tag} "
                f"| {r.score:.2f} | {domains_str} | {r.rationale} |"
            )
        return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _display_name(theory_id: str) -> str:
    """Convert snake_case theory_id to Title Case display name."""
    special = {
        "sir_contagion": "SIR Contagion",
        "is_lm": "IS-LM Model",
        "richardson_arms_race": "Richardson Arms Race",
        "fearon_bargaining": "Fearon Bargaining",
        "wittman_zartman": "Wittman-Zartman Ripeness",
        "porter_five_forces": "Porter's Five Forces",
        "hotelling_cpr": "Hotelling CPR",
        "fisher_pry": "Fisher-Pry Substitution",
        "bass_diffusion": "Bass Diffusion",
        "cournot_oligopoly": "Cournot Oligopoly",
        "stackelberg_leadership": "Stackelberg Leadership",
        "minsky_instability": "Minsky Financial Instability",
        "lotka_volterra": "Lotka-Volterra Competition",
        "cobweb_market": "Cobweb Market",
        "solow_growth": "Solow Growth",
        "keynesian_multiplier": "Keynesian Multiplier",
        "schumpeter_disruption": "Schumpeter Disruption",
        "opinion_dynamics": "Opinion Dynamics",
        "regulatory_shock": "Regulatory Shock",
        "acquirer_discount": "Acquirer's Discount (Roll)",
        "brand_equity_decay": "Brand Equity Decay (Keller)",
        "event_study": "Event Study (MacKinlay)",
        "principal_agent": "Principal-Agent",
        "efficiency_wages": "Efficiency Wages",
        "experience_curve": "Experience Curve",
    }
    return special.get(theory_id, theory_id.replace("_", " ").title())
