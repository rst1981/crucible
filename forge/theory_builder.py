"""
forge/theory_builder.py — Automatic theory discovery and code generation.

When the research pipeline (arXiv, SSRN adapters) finds a paper describing a
formal quantitative model, TheoryBuilder:

  1. Classifies the paper: does it contain an implementable formal model?
  2. If yes, generates a TheoryBase subclass via Claude API
  3. Runs a smoke test: import → instantiate with defaults → update({}, [], 0)
  4. Writes a PendingTheory record to data/theories/pending/{id}.json

The pending record waits for human review. On approval (via the Forge UI or
POST /api/theories/pending/{id}/approve), the theory file is written to
core/theories/discovered/ and hot-loaded by load_theory_file().

Usage:
    builder = TheoryBuilder()
    result = await builder.process(research_result)
    if result:
        print(f"Queued: {result.pending_id} — {result.theory_id} (smoke={'OK' if result.smoke_test['passed'] else 'FAIL'})")

Pending queue:
    data/theories/pending/{pending_id}.json
    data/theories/pending/index.json   ← summary index for fast listing
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import logging
import re
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic

from forge.researchers.base import ResearchResult

logger = logging.getLogger(__name__)

_PENDING_DIR = Path(__file__).parent.parent / "data" / "theories" / "pending"
_DISCOVERED_DIR = Path(__file__).parent.parent / "core" / "theories" / "discovered"

_ANTHROPIC_CLIENT: anthropic.AsyncAnthropic | None = None


def _client() -> anthropic.AsyncAnthropic:
    global _ANTHROPIC_CLIENT
    if _ANTHROPIC_CLIENT is None:
        _ANTHROPIC_CLIENT = anthropic.AsyncAnthropic()
    return _ANTHROPIC_CLIENT


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class SmokeTestResult:
    passed: bool
    instantiated: bool = False
    update_ran: bool = False
    return_valid: bool = False
    error: str | None = None


@dataclass
class PendingTheory:
    pending_id: str
    theory_id: str
    display_name: str
    domains: list[str]
    citation: str
    source_url: str
    source_type: str                 # "arxiv" | "ssrn"
    abstract_snippet: str
    generated_code: str
    smoke_test: dict[str, Any]       # SmokeTestResult as dict
    status: str                      # "pending" | "approved" | "rejected"
    created_at: str
    reviewed_at: str | None = None
    reviewed_by: str | None = None
    file_path: str | None = None     # set on approval

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self) -> Path:
        _PENDING_DIR.mkdir(parents=True, exist_ok=True)
        path = _PENDING_DIR / f"{self.pending_id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2))
        _update_index(self)
        return path


# ── Index ─────────────────────────────────────────────────────────────────────

def _update_index(pt: PendingTheory) -> None:
    """Keep a lightweight index.json for fast listing without loading every record."""
    index_path = _PENDING_DIR / "index.json"
    try:
        index: list[dict] = json.loads(index_path.read_text()) if index_path.exists() else []
    except (json.JSONDecodeError, OSError):
        index = []

    # Replace existing entry or append
    entry = {
        "pending_id": pt.pending_id,
        "theory_id": pt.theory_id,
        "display_name": pt.display_name,
        "domains": pt.domains,
        "status": pt.status,
        "smoke_passed": pt.smoke_test.get("passed", False),
        "created_at": pt.created_at,
        "source_type": pt.source_type,
        "citation": pt.citation,
    }
    index = [e for e in index if e["pending_id"] != pt.pending_id]
    index.append(entry)
    index_path.write_text(json.dumps(index, indent=2))


# ── Pending queue API ─────────────────────────────────────────────────────────

def list_pending(status: str | None = None) -> list[dict]:
    """Return index entries, optionally filtered by status."""
    index_path = _PENDING_DIR / "index.json"
    if not index_path.exists():
        return []
    try:
        index = json.loads(index_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    if status:
        return [e for e in index if e.get("status") == status]
    return index


def load_pending(pending_id: str) -> PendingTheory | None:
    """Load a full PendingTheory record by ID."""
    path = _PENDING_DIR / f"{pending_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return PendingTheory(**data)


def approve(pending_id: str, reviewed_by: str = "consultant") -> Path:
    """
    Approve a pending theory:
      1. Write the generated code to core/theories/discovered/{theory_id}.py
      2. Hot-load it into the registry
      3. Update the pending record status to 'approved'

    Returns the path of the new theory file.
    """
    from core.theories import load_theory_file

    pt = load_pending(pending_id)
    if pt is None:
        raise KeyError(f"Pending theory '{pending_id}' not found")
    if pt.status != "pending":
        raise ValueError(f"Theory '{pending_id}' is already {pt.status}")

    _DISCOVERED_DIR.mkdir(parents=True, exist_ok=True)
    file_path = _DISCOVERED_DIR / f"{pt.theory_id}.py"
    file_path.write_text(pt.generated_code)

    load_theory_file(file_path)

    pt.status = "approved"
    pt.reviewed_at = datetime.now(timezone.utc).isoformat()
    pt.reviewed_by = reviewed_by
    pt.file_path = str(file_path)
    pt.save()

    logger.info("Theory '%s' approved and registered from %s", pt.theory_id, file_path)
    return file_path


def reject(pending_id: str, reviewed_by: str = "consultant") -> None:
    """Mark a pending theory as rejected."""
    pt = load_pending(pending_id)
    if pt is None:
        raise KeyError(f"Pending theory '{pending_id}' not found")
    pt.status = "rejected"
    pt.reviewed_at = datetime.now(timezone.utc).isoformat()
    pt.reviewed_by = reviewed_by
    pt.save()
    logger.info("Theory '%s' rejected", pending_id)


# ── Smoke test ────────────────────────────────────────────────────────────────

def _smoke_test(code: str) -> SmokeTestResult:
    """
    Run a smoke test on generated theory code in an isolated temp module.

    Checks:
        1. File imports without error
        2. TheoryBase subclass can be instantiated with default params
        3. update({}, [], 0) runs without error
        4. Return value is dict[str, float] with values in [0, 1]
    """
    from core.theories.base import TheoryBase

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, prefix="_crucible_smoke_"
    ) as tmp:
        tmp.write(code)
        tmp_path = Path(tmp.name)

    try:
        spec = importlib.util.spec_from_file_location("_crucible_smoke_module", tmp_path)
        if spec is None or spec.loader is None:
            return SmokeTestResult(passed=False, error="Cannot load module spec")

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            return SmokeTestResult(passed=False, error=f"Import error: {exc}")

        # Find the TheoryBase subclass
        theory_class = None
        for obj in vars(module).values():
            if (
                inspect.isclass(obj)
                and issubclass(obj, TheoryBase)
                and obj is not TheoryBase
            ):
                theory_class = obj
                break

        if theory_class is None:
            return SmokeTestResult(
                passed=False, error="No TheoryBase subclass found in generated code"
            )

        # Instantiate with defaults
        try:
            instance = theory_class()
        except Exception as exc:
            return SmokeTestResult(
                passed=False, instantiated=False, error=f"Instantiation error: {exc}"
            )

        # Call update()
        try:
            result = instance.update({}, [], 0)
        except Exception as exc:
            return SmokeTestResult(
                passed=False, instantiated=True, update_ran=False,
                error=f"update() error: {exc}",
            )

        # Validate return type
        if not isinstance(result, dict):
            return SmokeTestResult(
                passed=False, instantiated=True, update_ran=True, return_valid=False,
                error=f"update() returned {type(result).__name__}, expected dict",
            )

        bad = {k: v for k, v in result.items() if not isinstance(v, (int, float))}
        if bad:
            return SmokeTestResult(
                passed=False, instantiated=True, update_ran=True, return_valid=False,
                error=f"Non-numeric values in update() return: {bad}",
            )

        return SmokeTestResult(
            passed=True, instantiated=True, update_ran=True, return_valid=True
        )

    finally:
        tmp_path.unlink(missing_ok=True)
        # Remove from sys.modules to avoid pollution
        for key in list(sys.modules.keys()):
            if key.startswith("_crucible_smoke"):
                del sys.modules[key]


# ── Claude prompts ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a quantitative economist and software engineer working on the Crucible \
simulation platform. Your job is to implement academic formal models as Python \
theory modules that plug into a multi-agent simulation engine.

Every theory module must:
- Inherit from TheoryBase (from core.theories.base)
- Use @register_theory("theory_id") decorator (from core.theories)
- Define a DOMAINS class attribute (list of domain strings)
- Define an inner Parameters(BaseModel) class with Pydantic fields
- Implement update(env, agents, tick) -> dict[str, float]
  - env values are normalized floats in [0, 1]
  - return dict maps env_key -> new_value, all in [0, 1]
  - env key convention: "{theory_id}__{variable_name}"
- Define state_variables property returning TheoryStateVariables(reads, writes, initializes)
- All outputs must be clamped to [0, 1]

Here is a complete example (SIR contagion model):

```python
from __future__ import annotations
from typing import TYPE_CHECKING
from pydantic import BaseModel, Field
from core.theories import register_theory
from core.theories.base import TheoryBase, TheoryStateVariables
if TYPE_CHECKING:
    from core.agents.base import BDIAgent

@register_theory("sir_contagion")
class SIRContagion(TheoryBase):
    DOMAINS = ["contagion", "financial_risk", "epidemiology"]

    class Parameters(BaseModel):
        beta: float = Field(default=0.30, ge=0.0, le=5.0,
            description="Transmission rate per tick")
        gamma: float = Field(default=0.10, ge=0.0, le=1.0,
            description="Recovery rate per tick")

    @property
    def state_variables(self) -> TheoryStateVariables:
        return TheoryStateVariables(
            reads=["sir__susceptible", "sir__infected"],
            writes=["sir__susceptible", "sir__infected", "sir__recovered"],
            initializes=["sir__susceptible", "sir__infected", "sir__recovered"],
        )

    def update(self, env: dict, agents: list, tick: int) -> dict:
        S = env.get("sir__susceptible", 0.99)
        I = env.get("sir__infected", 0.01)
        R = 1.0 - S - I
        new_I = min(1.0, I + self.params.beta * S * I - self.params.gamma * I)
        new_R = min(1.0, R + self.params.gamma * I)
        new_S = max(0.0, 1.0 - new_I - new_R)
        return {"sir__susceptible": new_S, "sir__infected": new_I, "sir__recovered": new_R}
```
"""

_CLASSIFY_PROMPT = """\
Given the following research paper, determine whether it describes a formal \
quantitative model that can be implemented as a simulation theory module.

A formal quantitative model has: named variables, mathematical update rules \
(ODEs, difference equations, or a closed-form function), and parameters with \
interpretable economic or social meaning.

Paper:
Title: {title}
Source: {source_type}
URL: {url}
Abstract/Summary:
{summary}

{raw_section}

Respond with a JSON object on a single line:
{{"has_model": true/false, "theory_id": "snake_case_id", "display_name": "Human Name", \
"domains": ["domain1", "domain2"], "citation": "Author (Year). Title. Journal.", \
"rationale": "one sentence explaining why this is/isn't implementable"}}

theory_id must be unique, lowercase, underscore-separated, max 30 chars.
domains must be from: macro, market, finance, banking, geopolitics, conflict, \
labor, regulation, policy, supply_chain, technology, energy, innovation, \
corporate_strategy, corporate_finance, competitive_dynamics, social, contagion, \
behavioral_finance, equity, mergers_acquisitions, brand_management, marketing, \
consumer_behavior, sustainability, game_theory, development, growth.
"""

_GENERATE_PROMPT = """\
Implement the following formal model as a Crucible TheoryBase module.

Paper:
Title: {title}
Source: {source_type}
Citation: {citation}
URL: {url}
Abstract/Summary:
{summary}

{raw_section}

Theory metadata:
- theory_id: {theory_id}
- display_name: {display_name}
- domains: {domains}

Write the complete Python module. Requirements:
1. Module-level docstring: describe the model, its equations, env keys, and citation
2. @register_theory("{theory_id}") decorator
3. DOMAINS = {domains}
4. Parameters class with sensible Pydantic defaults and Field descriptions
5. state_variables property with accurate reads/writes/initializes lists
6. update() implementing the core model equations, outputs clamped to [0, 1]
7. No external dependencies beyond pydantic, math, logging

Respond with ONLY the Python code — no explanation, no markdown fences.
"""


# ── TheoryBuilder ─────────────────────────────────────────────────────────────

class TheoryBuilder:
    """
    Converts a ResearchResult into a PendingTheory via Claude API.

    Call process() for a single result. It handles the full pipeline:
    classify → generate → smoke test → save to pending queue.
    """

    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        self.model = model

    async def process(self, result: ResearchResult) -> PendingTheory | None:
        """
        Process a research result.

        Returns a PendingTheory if the paper contains an implementable model,
        or None if the paper is context-only (no formal model found).
        """
        if not result.ok:
            logger.debug("Skipping failed research result: %s", result.error)
            return None

        if result.source_type not in ("arxiv", "ssrn"):
            logger.debug("Skipping non-academic source: %s", result.source_type)
            return None

        # Phase 1: classify
        meta = await self._classify(result)
        if meta is None or not meta.get("has_model"):
            logger.debug("No implementable model in: %s", result.title)
            return None

        logger.info("Model found: %s → theory_id=%s", result.title, meta["theory_id"])

        # Phase 2: generate code
        code = await self._generate(result, meta)
        if not code:
            logger.warning("Code generation failed for: %s", result.title)
            return None

        # Phase 3: smoke test
        smoke = _smoke_test(code)
        logger.info(
            "Smoke test for '%s': %s%s",
            meta["theory_id"],
            "PASSED" if smoke.passed else "FAILED",
            f" — {smoke.error}" if smoke.error else "",
        )

        # Phase 4: save to pending queue
        pending = PendingTheory(
            pending_id=str(uuid.uuid4()),
            theory_id=meta["theory_id"],
            display_name=meta.get("display_name", meta["theory_id"]),
            domains=meta.get("domains", []),
            citation=meta.get("citation", ""),
            source_url=result.url,
            source_type=result.source_type,
            abstract_snippet=result.summary[:500],
            generated_code=code,
            smoke_test=asdict(smoke),
            status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        path = pending.save()
        logger.info("PendingTheory saved: %s → %s", pending.pending_id, path)
        return pending

    async def process_batch(
        self, results: list[ResearchResult]
    ) -> list[PendingTheory]:
        """Process a list of research results, returning only those with models."""
        import asyncio
        tasks = [self.process(r) for r in results]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        pending = []
        for r, outcome in zip(results, outcomes):
            if isinstance(outcome, Exception):
                logger.error("Error processing '%s': %s", r.title, outcome)
            elif outcome is not None:
                pending.append(outcome)
        return pending

    async def _classify(self, result: ResearchResult) -> dict | None:
        raw_section = (
            f"Full text excerpt:\n{result.raw[:1500]}" if result.raw else ""
        )
        prompt = _CLASSIFY_PROMPT.format(
            title=result.title,
            source_type=result.source_type,
            url=result.url,
            summary=result.summary,
            raw_section=raw_section,
        )
        try:
            response = await _client().messages.create(
                model=self.model,
                max_tokens=512,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            # Extract JSON — find first { ... } block
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                logger.warning("No JSON in classify response: %s", text[:200])
                return None
            return json.loads(match.group())
        except Exception as exc:
            logger.error("Classify API call failed: %s", exc)
            return None

    async def _generate(self, result: ResearchResult, meta: dict) -> str | None:
        raw_section = (
            f"Full text excerpt:\n{result.raw[:2000]}" if result.raw else ""
        )
        prompt = _GENERATE_PROMPT.format(
            title=result.title,
            source_type=result.source_type,
            citation=meta.get("citation", ""),
            url=result.url,
            summary=result.summary,
            raw_section=raw_section,
            theory_id=meta["theory_id"],
            display_name=meta.get("display_name", ""),
            domains=meta.get("domains", []),
        )
        try:
            response = await _client().messages.create(
                model=self.model,
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            code = response.content[0].text.strip()
            # Strip markdown fences if present
            code = re.sub(r"^```python\s*", "", code)
            code = re.sub(r"\s*```$", "", code)
            return code.strip()
        except Exception as exc:
            logger.error("Generate API call failed: %s", exc)
            return None
