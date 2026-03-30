"""
forge/scoping_agent.py — ScopingAgent

Claude API tool-use agent that drives a ForgeSession from INTAKE to COMPLETE.
Fires research adapters in parallel on first message, builds SimSpec
incrementally through a dynamic interview, then hands off to TheoryMapper.

State machine:
  INTAKE → PARALLEL_RESEARCH → DYNAMIC_INTERVIEW → THEORY_MAPPING
        → VALIDATION → COMPLETE

Usage:
    agent   = ScopingAgent()
    session = ScopingAgent.create_session("Describe the scenario here...")
    reply   = await agent.turn(session)              # first turn (no user msg)
    # stream version:
    async for chunk in agent.turn_stream(session, user_message="..."):
        print(chunk, end="", flush=True)
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Callable

import httpx
from anthropic import Anthropic

from core.spec import SimSpec, TheoryRef
from forge.gap_detector import detect_gaps, _merge_gaps
from forge.researchers.fred import FredAdapter
from forge.researchers.gdelt import GdeltAdapter
from forge.researchers.guardian import GuardianAdapter
from forge.researchers.news import NewsAdapter
from forge.researchers.newsapi import NewsApiAdapter
from forge.researchers.openalex import OpenAlexAdapter
from forge.researchers.perplexity import PerplexityAdapter
from forge.researchers.semantic_scholar import SemanticScholarAdapter
from forge.researchers.ssrn import SsrnAdapter
from forge.researchers.worldbank import WorldBankAdapter
from forge.session import (
    ForgeMessage,
    ForgeSession,
    ForgeState,
    MessageRole,
    ResearchContext,
    SpecGap,
)
from forge.spec_builder import SpecBuilder
from forge.theory_mapper import TheoryMapper

logger = logging.getLogger(__name__)

MAX_TURNS = 5   # max interview turns before auto-completing the spec
_AGENT_MODEL = "claude-sonnet-4-6"


# ── System prompt ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """
You are the Forge intake agent for the Crucible simulation platform.
Your job: guide a consultant through describing a scenario so you can
build a complete SimSpec — a fully configured simulation specification.

Key rules:
1. Use research tools BEFORE asking any questions. Your questions must be
   informed by research. Never ask for something research already answered.
2. Use consulting language. Never expose model parameters directly.
   ("How do you expect actor X to respond to economic pressure?"
    not "What should I set richardson_arms_race__a to?")
3. Complete the spec in ≤ 5 questions. If a gap cannot be filled with
   certainty, use a reasonable default informed by research and flag it
   in the SimSpec metadata.
4. STRICT TOOL ORDER — follow this exactly, one step per round:
   a. Run research tools (search_news, search_fred, search_world_bank) in parallel.
   b. Call update_simspec ONCE with everything learned from research.
   c. Call ask_user for the highest-priority open gap (outcome_focus first, always).
   d. When the user replies, call update_simspec ONCE with their answer, then ask_user for the next gap.
      When recording the theories answer: use patch={"metadata": {"theories_mode": "empirical"}}
      for empirical selection, or patch={"metadata": {"theories_mode": "<framework name>"}} for
      a specific framework. NEVER write theories answers into outcome_focus.
   CRITICAL: Never call update_simspec twice in a row. After every update_simspec,
   the very next call MUST be ask_user (unless all gaps are filled, then finalize).
5. When all critical gaps are filled, call select_theories then finalize.
"""

# ── Tool schemas ───────────────────────────────────────────────────────────

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_fred",
        "description": (
            "Fetch time series data from FRED. "
            "Use for macroeconomic calibration: GDP, inflation, trade flows, oil prices."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "series_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "FRED series IDs, e.g. ['GDP', 'DCOILWTICO', 'UNRATE']",
                },
            },
            "required": ["series_ids"],
        },
    },
    {
        "name": "search_world_bank",
        "description": (
            "Fetch World Bank development indicators for specified countries. "
            "Use for cross-country calibration: military spend %, trade/GDP, political stability."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "indicators": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "World Bank indicator codes, e.g. ['MS.MIL.XPND.GD.ZS']",
                },
                "countries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "ISO 3166-1 alpha-2 codes, e.g. ['US', 'IR', 'SA']",
                },
            },
            "required": ["indicators", "countries"],
        },
    },
    {
        "name": "search_news",
        "description": "Search recent news for current events relevant to the scenario.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":     {"type": "string"},
                "days_back": {"type": "integer", "default": 90, "maximum": 365},
            },
            "required": ["query"],
        },
    },
    {
        "name": "update_simspec",
        "description": (
            "Apply a patch to the current SimSpec. "
            "Call after each research result or user answer to keep the spec current."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patch": {
                    "type": "object",
                    "description": (
                        "Partial SimSpec fields. Supported keys: "
                        "name, description, domain, initial_environment (dict[str,float]), "
                        "timeframe_ticks (int), actors (list of {actor_id,name,role}), "
                        "metadata (dict — use theories_mode='empirical' when user chooses "
                        "empirical theory selection, outcome_focus for the decision focus)."
                    ),
                },
            },
            "required": ["patch"],
        },
    },
    {
        "name": "identify_gap",
        "description": "Register a gap in the SimSpec that needs to be filled by the user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "field_path":  {"type": "string"},
                "description": {"type": "string"},
                "priority":    {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
            "required": ["field_path", "description", "priority"],
        },
    },
    {
        "name": "ask_user",
        "description": (
            "Ask the consultant a question to fill a gap. "
            "This returns control to the user — be specific and include context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "context":  {"type": "string", "description": "Why you are asking; what research found"},
                "options":  {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional suggested answers",
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "select_theories",
        "description": (
            "Invoke TheoryMapper to select and parameterize theory modules "
            "based on the SimSpec domain and research context. Call when the "
            "spec is otherwise complete."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "finalize",
        "description": (
            "Validate the complete SimSpec and transition to COMPLETE. "
            "Only call when all critical gaps are filled."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


# ── ScopingAgent ───────────────────────────────────────────────────────────

class ScopingAgent:
    """
    Claude API tool-use agent that drives a ForgeSession from INTAKE to COMPLETE.
    """

    def __init__(self, client: Anthropic | None = None) -> None:
        self._client = client or Anthropic()
        self._theory_mapper = TheoryMapper()
        self._spec_builder = SpecBuilder(self._client)

    # ── Session factory ────────────────────────────────────────────────────

    @staticmethod
    def create_session(intake_text: str) -> ForgeSession:
        session = ForgeSession(intake_text=intake_text)
        session.research_context.session_id = session.session_id
        return session

    # ── Main entry points ──────────────────────────────────────────────────

    async def turn(
        self,
        session: ForgeSession,
        user_message: str | None = None,
    ) -> str:
        """
        Drive the session forward by one turn.
        Returns the next message to show the consultant.
        """
        if user_message:
            session.add_message(MessageRole.USER, user_message)
            session.turn_count += 1

        if session.state == ForgeState.INTAKE:
            return await self._run_intake(session)
        if session.state == ForgeState.DYNAMIC_INTERVIEW:
            reply = ""
            async for chunk in self._run_interview_turn(session, user_message):
                reply = chunk
            return reply
        if session.state == ForgeState.THEORY_MAPPING:
            return await self._run_theory_mapping(session)
        if session.state == ForgeState.ENSEMBLE_REVIEW:
            # User message during review = they want to proceed or have modified via API
            return await self._finalize_ensemble(session)
        if session.state == ForgeState.VALIDATION:
            return await self._run_validation(session)
        if session.state == ForgeState.COMPLETE:
            return (
                f"Simulation '{session.simspec.name}' is ready to run. "
                f"Use POST /simulations to launch both ensembles."
            )
        return "Processing..."

    async def turn_stream(
        self,
        session: ForgeSession,
        user_message: str | None = None,
    ) -> AsyncIterator[str]:
        """
        Streaming version of turn(). Yields text chunks as they arrive.
        Final chunk is the complete response.
        """
        if user_message:
            session.add_message(MessageRole.USER, user_message)
            session.turn_count += 1

        if session.state == ForgeState.INTAKE:
            yield "Parsing scenario description...\n"
            skeleton = self._spec_builder.parse_intake(session.intake_text)
            session.simspec = skeleton
            session.domain = skeleton.domain
            session.state = ForgeState.PARALLEL_RESEARCH

            yield "Running parallel research (Perplexity, OpenAlex, FRED, World Bank, GDELT, Guardian, NewsAPI, news)...\n"
            source_status = await self._run_research(session)
            self._spec_builder.apply_research_hints(session.simspec, session.research_context)
            session.gaps = detect_gaps(session.simspec)
            self._mark_research_filled_gaps(session)
            session.state = ForgeState.DYNAMIC_INTERVIEW

            ctx = session.research_context

            # Log source failures internally but don't surface to user
            failed_sources = {k: v for k, v in source_status.items()
                              if v not in ("ok",) and not v.startswith("partial")}
            if failed_sources:
                logger.info("Research sources unavailable: %s", failed_sources)

            if ctx.library_additions:
                yield (
                    f"Added {len(ctx.library_additions)} new theor"
                    f"{'y' if len(ctx.library_additions) == 1 else 'ies'} to library: "
                    f"{', '.join(ctx.library_additions)}.\n"
                )
            if ctx.library_gaps:
                yield (
                    f"{len(ctx.library_gaps)} theor"
                    f"{'y' if len(ctx.library_gaps) == 1 else 'ies'} queued for review "
                    f"(smoke test failed): {', '.join(ctx.library_gaps)}.\n"
                )

            ok_count = sum(1 for v in source_status.values() if v == "ok" or v.startswith("partial"))
            yield f"Research complete ({ok_count}/{len(source_status)} sources).\n"
            reply = ""
            async for chunk in self._run_interview_turn(session, user_message=None):
                yield chunk
                reply = chunk

        elif session.state == ForgeState.DYNAMIC_INTERVIEW:
            async for chunk in self._run_interview_turn(session, user_message):
                yield chunk

        elif session.state == ForgeState.ENSEMBLE_REVIEW:
            # User message during review means "proceed with current ensemble"
            yield "Finalizing ensemble...\n"
            reply = await self._finalize_ensemble(session)
            yield reply

        elif session.state in (ForgeState.THEORY_MAPPING, ForgeState.VALIDATION):
            yield "Selecting theory modules...\n"
            reply = await self.turn(session, user_message=None)
            yield reply

        else:
            reply = await self.turn(session, user_message=None)
            yield reply

    # ── State handlers ─────────────────────────────────────────────────────

    async def _run_intake(self, session: ForgeSession) -> str:
        skeleton = self._spec_builder.parse_intake(session.intake_text)
        session.simspec = skeleton
        session.domain = skeleton.domain
        session.state = ForgeState.PARALLEL_RESEARCH

        await self._run_research(session)  # return value unused in non-streaming path
        self._spec_builder.apply_research_hints(session.simspec, session.research_context)
        session.gaps = detect_gaps(session.simspec)
        self._mark_research_filled_gaps(session)
        session.state = ForgeState.DYNAMIC_INTERVIEW

        reply = ""
        async for chunk in self._run_interview_turn(session, user_message=None):
            reply = chunk
        return reply

    # Verified FRED series IDs by topic — LLM picks from this list only
    _FRED_CATALOG = {
        "rates":      ["FEDFUNDS", "DFF", "DTB3", "DGS10", "DGS2", "T10Y2Y", "MORTGAGE30US"],
        "inflation":  ["CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE", "MICH"],
        "growth":     ["GDP", "GDPC1", "INDPRO", "PAYEMS", "UNRATE", "ICSA"],
        "credit":     ["DPCREDIT", "TOTALSL", "BUSLOANS", "DRSFRMACBS", "DRTSCILM"],
        "fx":         ["DEXUSEU", "DEXJPUS", "DEXCHUS", "DEXKOUS", "DEXBZUS", "DEXMXUS"],
        "energy":     ["DCOILWTICO", "DCOILBRENTEU", "DHHNGSP", "GASREGCOVW"],
        "markets":    ["SP500", "NASDAQ100", "DJIA", "VIXCLS", "WILL5000IND"],
        "sovereign":  ["IRLTLT01USM156N", "IRLTLT01DEA156N", "IRLTLT01JPM156N"],
        "trade":      ["BOPGSTB", "IMPGS", "EXPGS", "TRFVOLUSM227NFWA"],
        "money":      ["M2SL", "M1SL", "BOGMBASE", "WRMFSL"],
        "housing":    ["CSUSHPINSA", "HOUST", "MSPUS", "RHORUSQ156N"],
        "corporate":  ["DPCREDIT", "DISCONTINUED_SERIES", "CPROFIT", "BOGZ1FL104090005Q"],
    }

    async def _suggest_fred_series(self, intake_text: str, domain: str) -> list[str]:
        """Ask Haiku to pick 2-3 FRED series IDs from a verified catalog."""
        catalog_str = "\n".join(f"{k}: {', '.join(v)}" for k, v in self._FRED_CATALOG.items())
        try:
            resp = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=80,
                messages=[{"role": "user", "content": (
                    f"Scenario: {intake_text[:200]}\nDomain: {domain}\n\n"
                    f"Pick 2-3 FRED series IDs most relevant to this scenario.\n"
                    f"You MUST only use IDs from this verified list:\n{catalog_str}\n\n"
                    f"Return ONLY a JSON array: [\"ID1\", \"ID2\"]"
                )}],
            )
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1].lstrip("json").strip()
            ids = json.loads(raw)
            # Only allow IDs that exist in the catalog
            valid = {sid for ids in self._FRED_CATALOG.values() for sid in ids}
            return [str(i).strip().upper() for i in ids if str(i).strip().upper() in valid][:3]
        except Exception:
            return []

    async def _run_research(self, session: ForgeSession) -> dict[str, str]:
        """
        Fan-out research across all adapters in parallel.
        Returns a dict of source → status for user-facing warnings.
        SSRN is excluded (permanently 403-blocked).
        """
        spec = session.simspec
        domain_query = f"{spec.domain} {spec.description} {session.intake_text}"[:200]

        # Distill intake into 4-6 clean keyword phrases for academic search APIs.
        # OpenAlex/S2 return 0 results on long noisy queries; short keywords work well.
        academic_query = await self._build_academic_query(session.intake_text, spec.domain)
        logger.info("Academic query: %r", academic_query)

        # Build a Perplexity research question from the intake
        perplexity_question = (
            f"What are the key quantitative facts, historical precedents, and current data "
            f"relevant to this scenario: {session.intake_text[:300]}? "
            f"Focus on specific numbers, rates, prices, timelines, and market sizes."
        )

        # Pick domain-relevant FRED series instead of hardcoded macro defaults
        fred_series = await self._suggest_fred_series(session.intake_text, spec.domain)

        async with httpx.AsyncClient(timeout=30.0) as http:
            oa         = OpenAlexAdapter(http)
            fred       = FredAdapter(http)
            wb         = WorldBankAdapter(http)
            news       = NewsAdapter(http)
            perplexity = PerplexityAdapter(http)
            gdelt      = GdeltAdapter(http)
            guardian   = GuardianAdapter(http)
            newsapi    = NewsApiAdapter(http)

            tasks = [
                oa.fetch(academic_query, max_results=5),
                wb.fetch("NY.GDP.MKTP.CD MS.MIL.XPND.GD.ZS NE.TRD.GNFS.ZS", max_results=5),
                news.fetch(domain_query, max_results=5),
                perplexity.fetch(perplexity_question, max_results=1),
                gdelt.fetch(domain_query, max_results=5),
                guardian.fetch(domain_query, max_results=5),
                newsapi.fetch(domain_query, max_results=5),
            ]
            fred_labels = []
            for series_id in fred_series:
                tasks.append(fred.fetch(series_id, max_results=1))
                fred_labels.append(f"FRED/{series_id}")

            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        perplexity_result = raw_results[3]
        gdelt_result   = raw_results[4]
        guardian_result = raw_results[5]
        newsapi_result  = raw_results[6]
        fred_raw = raw_results[7:]
        raw_results = list(raw_results[:3]) + list(fred_raw)

        # Semantic Scholar: run sequentially after OA to avoid shared-pool collisions.
        oa_ok_count = sum(1 for r in (raw_results[0] if isinstance(raw_results[0], list) else []) if r.ok)
        async with httpx.AsyncClient(timeout=25.0) as http:
            if oa_ok_count < 3:
                s2_results = await SemanticScholarAdapter(http).fetch(academic_query, max_results=3)
            else:
                s2_results = []

        raw_results = list(raw_results) + [s2_results]

        source_labels = ["OpenAlex", "World Bank", "News feeds"] + fred_labels + ["Semantic Scholar"]

        # Add GDELT, Guardian, NewsAPI results directly to context
        ctx = session.research_context
        for label, result in [("GDELT", gdelt_result), ("Guardian", guardian_result), ("NewsAPI", newsapi_result)]:
            if isinstance(result, list):
                ok = [r for r in result if r.ok]
                ctx.results.extend(result)
                logger.info("%s: %d results (%d ok)", label, len(result), len(ok))

        # Add Perplexity result separately (always include if ok)
        if isinstance(perplexity_result, list) and perplexity_result:
            ctx = session.research_context
            for r in perplexity_result:
                ctx.results.append(r)
            logger.info("Perplexity initial research: ok=%s", perplexity_result[0].ok)
        source_status: dict[str, str] = {}

        ctx = session.research_context
        for label, result in zip(source_labels, raw_results):
            if isinstance(result, Exception):
                logger.warning("Research adapter error (%s): %s", label, result)
                source_status[label] = f"error: {result}"
                continue
            if isinstance(result, list):
                ok = [r for r in result if r.ok]
                failed = [r for r in result if not r.ok]
                ctx.results.extend(result)
                if failed and not ok:
                    source_status[label] = failed[0].error or "unavailable"
                elif failed:
                    source_status[label] = f"partial ({len(ok)}/{len(result)})"
                else:
                    source_status[label] = "ok"

        # Library gap fill: pass successful academic results through TheoryBuilder
        # Include OpenAlex and Semantic Scholar — same academic paper corpus as arXiv/SSRN
        academic = [r for r in ctx.results if r.source_type in ("arxiv", "ssrn", "openalex", "semantic_scholar") and r.ok]
        if academic:
            await self._fill_library_gaps(academic, ctx)

        # Extraction pass: pull theory candidates + param estimates from all results
        await self._extraction_pass(ctx, session.simspec)
        ctx.research_complete = True
        logger.info(
            "Research complete: %d results, %d theory candidates, %d param estimates, "
            "%d library additions, %d queued for review",
            len(ctx.results),
            len(ctx.theory_candidates),
            len(ctx.parameter_estimates),
            len(ctx.library_additions),
            len(ctx.library_gaps),
        )
        return source_status

    async def _build_academic_query(self, intake_text: str, domain: str) -> str:
        """
        Distill a free-text intake into 4-6 short keyword phrases suitable for
        OpenAlex, Semantic Scholar, and arXiv search.

        Long noisy queries return 0 results; clean keywords return thousands.
        Uses haiku (~$0.0001 per call).
        """
        try:
            resp = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=60,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Extract the 3 most important academic search terms from this scenario. "
                        f"Return ONLY a JSON array of exactly 3 short phrases (2-3 words each). "
                        f"Prefer established academic terminology. No explanation.\n\n"
                        f"Domain: {domain}\nScenario: {intake_text[:300]}"
                    ),
                }],
            )
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            keywords = json.loads(raw)
            if isinstance(keywords, list) and keywords:
                # Hard cap: max 3 phrases, max 10 words total — keeps OpenAlex queries effective
                phrases = [str(k) for k in keywords[:3]]
                joined = " ".join(phrases)
                return " ".join(joined.split()[:10])
        except Exception as exc:
            logger.warning("_build_academic_query failed: %s", exc)
        # Fallback: domain + first words of intake
        return f"{domain} {' '.join(intake_text.split()[:5])}"

    async def _fill_library_gaps(
        self,
        academic_results: list,
        ctx: ResearchContext,
    ) -> None:
        """
        Pass academic research results (arXiv, SSRN) through TheoryBuilder.

        For each paper:
        - If it contains a formal model AND the theory_id is not already in
          the library: generate code, run smoke test.
          - Smoke PASS  → auto-approve: write to discovered/, hot-load, available immediately.
          - Smoke FAIL  → save to pending queue for human review.
        - If theory_id is already in the library: skip.

        Results are recorded in ctx.library_additions and ctx.library_gaps.
        """
        from forge.theory_builder import TheoryBuilder, auto_approve_if_passing
        from core.theories import list_theories

        builder = TheoryBuilder()
        existing = set(list_theories())

        for result in academic_results:
            try:
                pending = await builder.process(result)
            except Exception as exc:
                logger.warning("TheoryBuilder.process failed for '%s': %s", result.title, exc)
                continue

            if pending is None:
                continue  # no formal model in this paper

            if pending.theory_id in existing:
                logger.debug(
                    "Library gap fill: '%s' already in library, skipping", pending.theory_id
                )
                continue

            if auto_approve_if_passing(pending):
                ctx.library_additions.append(pending.theory_id)
                existing.add(pending.theory_id)  # update local set for this session
                logger.info(
                    "Library gap filled: '%s' auto-approved from '%s'",
                    pending.theory_id, result.title,
                )
            else:
                ctx.library_gaps.append(pending.theory_id)
                logger.info(
                    "Library gap queued: '%s' needs review (smoke test failed)",
                    pending.theory_id,
                )

    async def _extraction_pass(
        self,
        ctx: ResearchContext,
        simspec: SimSpec,
    ) -> None:
        """
        Single Claude haiku call that reads all research summaries and extracts:
        - theory_candidates: list of Crucible theory IDs likely relevant
        - parameter_estimates: env_key → [0,1] normalized value
        """
        if not ctx.results:
            return

        snippets = "\n\n".join(
            r.to_context_snippet() for r in ctx.results if r.ok
        )[:6000]  # token budget

        from core.theories import list_theories
        available = ", ".join(list_theories())

        prompt = f"""
Scenario domain: {simspec.domain}
Scenario description: {simspec.description}

Available Crucible theory modules: {available}

Research summaries:
{snippets}

Extract and return JSON:
{{
  "theory_candidates": ["module_id_1", "module_id_2"],
  "parameter_estimates": {{"env_key": 0.0_to_1.0}}
}}

Rules:
- theory_candidates: only modules from the available list
- parameter_estimates: only env keys grounded in the research above
- Return ONLY valid JSON
"""
        try:
            resp = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1][4:] if parts[1].startswith("json") else parts[1]
            extracted = json.loads(raw)
            ctx.theory_candidates = extracted.get("theory_candidates", [])
            ctx.parameter_estimates = {
                k: float(max(0.0, min(1.0, float(v))))
                for k, v in (extracted.get("parameter_estimates") or {}).items()
            }
            ctx.env_keys_calibrated = set(ctx.parameter_estimates.keys())
        except Exception as exc:
            logger.warning("_extraction_pass failed: %s", exc)

    async def _run_interview_turn(
        self,
        session: ForgeSession,
        user_message: str | None,
    ) -> AsyncIterator[str]:
        deep_dive_summary: str | None = None
        just_filled: set[str] = set()

        if user_message:
            previously_open = {g.field_path for g in session.open_gaps()}
            self._spec_builder.apply_user_answer(
                session.simspec, session.gaps, user_message
            )
            new_gaps = detect_gaps(session.simspec)
            _merge_gaps(session.gaps, new_gaps)
            self._mark_research_filled_gaps(session)

            now_open = {g.field_path for g in session.open_gaps()}
            just_filled = previously_open - now_open

            # Clean up raw outcome_focus text → concise summary
            if "outcome_focus" in just_filled:
                raw_focus = session.simspec.metadata.get("outcome_focus", "")
                if raw_focus and len(raw_focus) > 80:
                    try:
                        clean_resp = self._client.messages.create(
                            model="claude-haiku-4-5-20251001",
                            max_tokens=80,
                            messages=[{
                                "role": "user",
                                "content": (
                                    f"Summarize this simulation outcome focus in 1-2 concise sentences "
                                    f"suitable as a document heading. Focus on what metrics to track and "
                                    f"what decision it informs. No filler words.\n\n{raw_focus}"
                                ),
                            }],
                        )
                        session.simspec.metadata["outcome_focus"] = clean_resp.content[0].text.strip()
                    except Exception:
                        pass  # keep raw if haiku fails

            # If outcome_focus was just filled: run targeted theory deep-dive
            if "outcome_focus" in just_filled and not session.deep_dive_complete:
                deep_dive_summary = await self._run_outcome_deepdive(session)
                session.deep_dive_complete = True

        open_gaps = session.open_gaps()
        logger.info(
            "_run_interview_turn: turn_count=%d open_gaps=%s all_gaps=%s metadata=%s",
            session.turn_count,
            [g.field_path for g in open_gaps],
            [(g.field_path, g.filled) for g in session.gaps],
            session.simspec.metadata if session.simspec else {},
        )
        if not open_gaps or session.turn_count >= MAX_TURNS:
            self._auto_fill_gaps(session)
            session.state = ForgeState.THEORY_MAPPING
            reply = await self._run_theory_mapping(session)
            yield reply
            return

        # Use Claude tool-use for the next question, streaming status updates
        status_queue: asyncio.Queue = asyncio.Queue()

        def _on_round(round_num: int, tool_names: list[str]) -> None:
            search_tools = [t for t in tool_names if t.startswith("search_")]
            if search_tools and round_num > 0:
                queries = ", ".join(t.replace("search_", "") for t in search_tools[:2])
                status_queue.put_nowait(f"Still researching ({queries})...\n")

        messages = _build_claude_messages(session)
        agent_task = asyncio.create_task(
            self._agent_turn(session, messages=messages, on_round=_on_round)
        )

        while not agent_task.done():
            await asyncio.sleep(0.5)
            while not status_queue.empty():
                yield status_queue.get_nowait()

        next_reply = await agent_task
        # Drain any remaining status messages
        while not status_queue.empty():
            yield status_queue.get_nowait()

        if deep_dive_summary:
            yield f"{deep_dive_summary}\n\n---\n\n{next_reply}"
        else:
            yield next_reply

    async def _agent_turn(
        self,
        session: ForgeSession,
        messages: list | None = None,
        on_round: Callable[[int, list[str]], None] | None = None,
    ) -> str:
        """
        Run one Claude tool-use turn. The agent can call research tools,
        update_simspec, identify_gap, and ask_user. We loop until ask_user
        or finalize is called, then return.
        """
        # Build conversation for Claude
        if messages is None:
            messages = _build_claude_messages(session)

        # Inject current spec state as context
        spec_summary = _spec_summary(session.simspec)
        open_gap_text = "\n".join(
            f"- [{g.priority:.1f}] {g.field_path}: {g.description}"
            for g in session.open_gaps()[:5]
        )
        top_gap = session.open_gaps()[0] if session.open_gaps() else None
        research_done = session.research_context.research_complete
        if research_done and top_gap:
            next_action = (
                f"Research is complete. Call update_simspec ONCE with research findings, "
                f"then immediately call ask_user for gap '{top_gap.field_path}': "
                f"{top_gap.description}"
            )
        elif top_gap:
            next_action = (
                f"Run research first, then call update_simspec once, "
                f"then ask_user for gap '{top_gap.field_path}'."
            )
        else:
            next_action = "All gaps filled — call select_theories then finalize."
        context_injection = (
            f"\n\nCurrent SimSpec state:\n{spec_summary}"
            f"\n\nOpen gaps:\n{open_gap_text}"
            f"\n\nNext action: {next_action}"
            f"\n\nTurn {session.turn_count}/{MAX_TURNS}."
        )
        if messages and messages[-1]["role"] == "user":
            messages[-1]["content"] += context_injection
        else:
            messages.append({"role": "user", "content": context_injection})

        # Tool-use loop
        max_tool_rounds = 20
        simspec_update_count = 0  # guard: force ask_user after first update_simspec
        for round_num in range(max_tool_rounds):
            resp = self._client.messages.create(
                model=_AGENT_MODEL,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                tools=_TOOLS,
                messages=messages,
            )

            # Extract text and tool calls
            text_blocks = [b for b in resp.content if b.type == "text"]
            tool_blocks = [b for b in resp.content if b.type == "tool_use"]
            tool_names = [b.name for b in tool_blocks]
            logger.info("_agent_turn round %d: tools=%s", round_num, tool_names)
            if on_round:
                on_round(round_num, tool_names)

            if not tool_blocks:
                # Pure text response — return it
                reply = " ".join(b.text for b in text_blocks).strip()
                session.add_message(MessageRole.ASSISTANT, reply)
                return reply

            # Add assistant message to conversation
            messages.append({"role": "assistant", "content": resp.content})

            # Process tool calls
            tool_results = []
            asked_user = False
            final_reply = ""

            for tool_call in tool_blocks:
                result, stop = await self._dispatch_tool(
                    tool_call.name, tool_call.input, session
                )
                if tool_call.name == "update_simspec":
                    simspec_update_count += 1
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": json.dumps(result),
                })
                if stop:
                    asked_user = True
                    final_reply = result.get("question", str(result))

            messages.append({"role": "user", "content": tool_results})

            # After first update_simspec without ask_user: force a constrained ask call
            if simspec_update_count >= 1 and "ask_user" not in tool_names and not asked_user:
                open_gaps = session.open_gaps()
                if open_gaps:
                    question = await self._force_ask_user(session, messages)
                    session.add_message(MessageRole.ASSISTANT, question)
                    return question

            if asked_user:
                session.add_message(MessageRole.ASSISTANT, final_reply)
                return final_reply

            if session.state == ForgeState.COMPLETE:
                reply = (
                    f"Your simulation '{session.simspec.name}' is configured and ready. "
                    f"Actors: {len(session.simspec.actors)}. "
                    f"Theories: {', '.join(t.theory_id for t in session.simspec.theories)}. "
                    f"Use POST /simulations to launch."
                )
                session.add_message(MessageRole.ASSISTANT, reply)
                return reply

        # Fallback: hit tool limit
        reply = "I've gathered enough information to build your simulation. Let me finalize it."
        self._auto_fill_gaps(session)
        session.state = ForgeState.THEORY_MAPPING
        await self._run_theory_mapping(session)
        session.add_message(MessageRole.ASSISTANT, reply)
        return reply

    async def _force_ask_user(
        self,
        session: ForgeSession,
        prior_messages: list[dict[str, Any]],
    ) -> str:
        """
        Make a constrained Claude call with ONLY ask_user available.
        Called after update_simspec to guarantee the agent asks a question
        rather than calling update_simspec again.
        """
        top_gap = session.open_gaps()[0]
        spec_summary = _spec_summary(session.simspec)
        ask_tool = next(t for t in _TOOLS if t["name"] == "ask_user")

        system = (
            "You are conducting a simulation scoping interview. "
            "The SimSpec has been updated with research findings. "
            "You must now ask the consultant ONE question about the following gap. "
            "Use consulting language — no technical parameters. "
            "You MUST call the ask_user tool."
        )
        if top_gap.field_path == "theories":
            extra = (
                "\n\nIMPORTANT: Always include 'Let the model select theories empirically "
                "based on research findings' as the first or last suggested option."
            )
        else:
            extra = ""
        user_msg = (
            f"Current SimSpec:\n{spec_summary}\n\n"
            f"Ask the consultant about this gap:\n"
            f"  Field: {top_gap.field_path}\n"
            f"  Question: {top_gap.description}"
            f"{extra}"
        )

        try:
            resp = self._client.messages.create(
                model=_AGENT_MODEL,
                max_tokens=512,
                system=system,
                tools=[ask_tool],
                tool_choice={"type": "any"},
                messages=[{"role": "user", "content": user_msg}],
            )
            for block in resp.content:
                if hasattr(block, "type") and block.type == "tool_use" and block.name == "ask_user":
                    question = block.input.get("question", "")
                    context  = block.input.get("context", "")
                    options  = block.input.get("options", [])
                    full_q = question
                    if context:
                        full_q += f"\n\n*Context: {context}*"
                    if options:
                        full_q += "\n\nSuggested options:\n" + "\n".join(f"- {o}" for o in options)
                    logger.info("_force_ask_user: asked about '%s'", top_gap.field_path)
                    return full_q
                if hasattr(block, "type") and block.type == "text":
                    return block.text
        except Exception as exc:
            logger.warning("_force_ask_user failed: %s", exc)

        # Fallback: return the gap description directly
        return top_gap.description

    async def _run_outcome_deepdive(self, session: ForgeSession) -> str:
        """
        After outcome_focus is filled, run a targeted theory deep-dive:
        - 2 focused arXiv searches scoped to the refined outcome
        - Re-run extraction pass to update theory_candidates
        - Present findings as a formatted consulting summary
        """
        outcome_focus = session.simspec.metadata.get("outcome_focus", "")
        domain = session.simspec.domain or "market"
        scenario_name = session.simspec.name or "the scenario"

        logger.info("_run_outcome_deepdive: outcome_focus='%s'", outcome_focus[:80])

        # Strip markdown formatting before distilling to academic query keywords
        import re as _re
        outcome_clean = _re.sub(r'\*+|#{1,6}\s?|`+|\[|\]|\(.*?\)', '', outcome_focus).strip()
        # Distill outcome_focus to clean keywords before hitting academic APIs
        academic_query = await self._build_academic_query(outcome_clean, domain)
        q_theory = f"{academic_query} formal model theory dynamics"
        q_empirical = f"{academic_query} empirical analysis calibration"

        new_results = []
        async with httpx.AsyncClient(timeout=20.0) as http:
            # Run OpenAlex in parallel (no rate limit), arXiv sequentially after
            oa_results, oa_empirical = await asyncio.gather(
                OpenAlexAdapter(http).fetch(q_theory, max_results=5),
                OpenAlexAdapter(http).fetch(q_empirical, max_results=5),
            )
            new_results.extend([r for r in oa_results if r.ok])
            new_results.extend([r for r in oa_empirical if r.ok])
            # arXiv removed — OpenAlex + S2 cover academic paper corpus without 429s

        if new_results:
            session.research_context.results.extend(new_results)
            await self._extraction_pass(session.research_context, session.simspec)

        candidates = session.research_context.theory_candidates
        param_est  = session.research_context.parameter_estimates

        # Format summary via haiku
        snippets = "\n\n".join(r.to_context_snippet() for r in new_results)[:4000]
        prompt = f"""
You are a simulation consultant presenting theory findings to a client.

Scenario: {scenario_name}
Outcome focus: {outcome_focus}
Theory candidates identified: {', '.join(candidates) if candidates else 'none yet'}
Parameter estimates: {json.dumps(param_est, indent=2) if param_est else 'none'}

New research findings:
{snippets}

Write a concise theory deep-dive (3–5 bullet points) in consulting language:
- Which theoretical frameworks are most relevant to this outcome focus
- What each framework reveals about the key dynamics
- Any calibration anchors found in the research (cite values where found)

End with one sentence on which framework should anchor the ensemble.
Do NOT mention tool parameters or code. Write for a strategy consultant, not a developer.
"""
        try:
            resp = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            summary = resp.content[0].text.strip()
        except Exception as exc:
            logger.warning("_run_outcome_deepdive summary failed: %s", exc)
            summary = (
                f"Deep-dive complete. Theory candidates: {', '.join(candidates) or 'none'}."
            )

        return f"**Theory deep-dive — {outcome_focus[:60]}**\n\n{summary}"

    async def _run_theory_mapping(self, session: ForgeSession) -> str:
        # Include any theories auto-added to the library during research
        # in the mapper's candidate pool (they're already registered).
        #
        # Domain override: if simspec.domain is a pure geopolitical label but
        # outcome_focus signals economics/supply-chain, remap to a richer domain
        # string so the theory mapper scores commodity/market/logistics theories.
        spec = session.simspec
        meta = spec.metadata or {} if spec else {}
        outcome = meta.get("outcome_focus", "").lower()
        channels = " ".join(meta.get("transmission_channels", [])).lower()
        economic_signals = {"supply chain", "logistics", "cost", "commodity", "margin",
                            "pricing", "procurement", "freight", "inflation", "hedging",
                            "sourcing", "input cost", "fuel", "shipping"}
        if spec and spec.domain in ("geopolitics", "conflict", "crisis") and any(
            sig in outcome or sig in channels for sig in economic_signals
        ):
            import dataclasses
            spec = dataclasses.replace(
                spec,
                domain=f"{spec.domain} supply_chain commodity market logistics economics"
            )
            logger.info("_run_theory_mapping: expanded domain from '%s' to include economic signals",
                        session.simspec.domain)
        recommendations = self._theory_mapper.recommend_from_spec(spec)

        # Split into Tier 1 (library) and Tier 2 (discovered this session).
        # discovered theories have source == "discovered" from TheoryMapper.
        all_recs = [
            {
                "theory_id":          r.theory_id,
                "display_name":       r.display_name,
                "score":              r.score,
                "rationale":          r.rationale,
                "suggested_priority": r.suggested_priority,
                "domains":            r.domains,
                "source":             r.source,
            }
            for r in recommendations
        ]
        # Only show theories actually discovered in THIS session's research phase
        session_discoveries = set(session.research_context.library_additions or [])
        session.recommended_theories = [t for t in all_recs if t["source"] != "discovered"]
        session.discovered_theories  = [
            t for t in all_recs
            if t["source"] == "discovered" and t["theory_id"] in session_discoveries
        ]
        session.state = ForgeState.ENSEMBLE_REVIEW

        additions = session.research_context.library_additions
        gaps = session.research_context.library_gaps
        if additions or gaps:
            logger.info(
                "Theory mapping: %d new theories added to library, %d queued for review.",
                len(additions), len(gaps),
            )

        return await self._run_ensemble_review(session)

    async def _run_ensemble_review(self, session: ForgeSession) -> str:
        """
        Enrich recommended_theories with application_note per theory, then
        present the ensemble. The frontend renders the detailed card view.
        """
        recs = session.recommended_theories
        discovered = session.discovered_theories
        if not recs and not discovered:
            return await self._finalize_ensemble(session)

        # Enrich all theories with application notes (single haiku call)
        await self._add_application_notes(session)
        # Identify data gaps now so the frontend panel is populated at ensemble review time
        await self._identify_data_gaps(session)
        recs = session.recommended_theories
        discovered = session.discovered_theories

        lines = []

        # Tier 1 — library
        lines.append("**Tier 1 — Library ensemble** (domain-matched from built-in library):\n")
        for i, r in enumerate(recs):
            note = r.get("application_note") or r.get("rationale", "")
            lines.append(
                f"{i+1}. **{r['display_name']}** — score {r['score']:.2f}  \n"
                f"   {note}"
            )

        # Tier 2 — discovered (only shown if non-empty)
        if discovered:
            lines.append(
                f"\n**Tier 2 — Discovered ensemble** "
                f"({len(discovered)} theor{'y' if len(discovered) == 1 else 'ies'} built from research):\n"
            )
            for i, r in enumerate(discovered):
                note = r.get("application_note") or r.get("rationale", "")
                lines.append(
                    f"{i+1}. **{r['display_name']}** *(new)*  \n"
                    f"   {note}"
                )

        additions = session.research_context.library_additions
        if additions:
            lines.append(
                f"\n*{len(additions)} new theor"
                f"{'y' if len(additions) == 1 else 'ies'} added to library: "
                f"{', '.join(additions)}.*"
            )

        if discovered:
            lines.append(
                "\n\nReview the ensembles in the panel. You can:\n"
                "- **Accept library** — use the domain-matched library ensemble\n"
                "- **Use discovered** — use the research-specific ensemble\n"
                "- **Merge both** — combine unique theories from each tier\n"
                "- **Customize** — build your own from the library\n\n"
                "When ready, hit **Go** to launch."
            )
        else:
            lines.append(
                "\n\nReview the theory cards in the panel. You can:\n"
                "- **Accept** the recommended ensemble as-is\n"
                "- **Customize** — add, remove, or reorder theories from the library\n\n"
                "When ready, hit **Go** to launch."
            )

        reply = "\n".join(lines)
        session.add_message(MessageRole.ASSISTANT, reply)
        return reply

    async def _add_application_notes(self, session: ForgeSession) -> None:
        """
        Add application_note to each theory (library + discovered) via a single haiku call.
        Explains how each theory specifically applies to this SimSpec.
        """
        all_theories = session.recommended_theories + session.discovered_theories
        if not all_theories:
            return

        spec = session.simspec
        outcome_focus = (spec.metadata or {}).get("outcome_focus", "") if spec else ""
        actors_str = ", ".join(a.name for a in spec.actors[:5]) if spec and spec.actors else "unknown actors"

        theory_list = "\n".join(
            f"{i+1}. {r['theory_id']}: {r.get('rationale', '')}"
            for i, r in enumerate(all_theories)
        )

        prompt = f"""Scenario: {spec.name if spec else 'Unknown'}
Domain: {spec.domain if spec else 'unknown'}
Outcome focus: {outcome_focus}
Key actors: {actors_str}

Theory ensemble:
{theory_list}

For each theory, write a 1-2 sentence "application note" explaining HOW it specifically
applies to this scenario — in consulting language, not technical parameters.
Connect the theory mechanism to the actual actors and outcome focus.

Return JSON: {{"notes": ["note for theory 1", "note for theory 2", ...]}}
One note per theory in the same order. Return ONLY valid JSON."""

        try:
            resp = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=900,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            notes = json.loads(raw).get("notes", [])
            for i, note in enumerate(notes):
                if i < len(all_theories):
                    all_theories[i]["application_note"] = note
            logger.info("_add_application_notes: enriched %d theories", len(notes))
        except Exception as exc:
            logger.warning("_add_application_notes failed: %s", exc)

    async def _identify_data_gaps(self, session: ForgeSession) -> None:
        """
        Identify data gaps based on research results and scenario spec.
        Populates session.data_gaps before ensemble review so the frontend can show them.
        """
        if session.data_gaps:
            return  # already populated (e.g. from a previous call)

        ctx = session.research_context
        spec = session.simspec
        if not spec:
            return

        # Summarise what data was found vs missing
        sources_ok = [r.source_type for r in ctx.results if r.ok]
        sources_failed = [r.source_type for r in ctx.results if not r.ok]
        param_names = list(ctx.parameter_estimates.keys()) if ctx.parameter_estimates else []

        prompt = f"""Scenario: {spec.name}
Domain: {spec.domain}
Actors: {', '.join(a.name for a in spec.actors[:5]) if spec.actors else 'unknown'}
Outcome focus: {(spec.metadata or {}).get('outcome_focus', '')}

Research sources that returned data: {', '.join(set(sources_ok)) or 'none'}
Research sources that failed/returned nothing: {', '.join(set(sources_failed)) or 'none'}
Parameters calibrated from data: {', '.join(param_names[:10]) or 'none'}

Identify data gaps in two categories:

1. PROPRIETARY gaps — firm-level or confidential data that public sources cannot provide
   (e.g. internal inventory levels, franchise margin data, company-specific hedging positions)

2. RESOLVABLE gaps — gaps that public data can plausibly fill.
   Frame each gap around the PHENOMENON, not a specific database or report.
   Use broad, proxy-friendly language so a web search can answer it.
   Good: "historical oil price spikes during Middle East conflict episodes"
   Bad:  "Platts spot crude procurement data from IEA monthly reports"
   Good: "US military response timelines in comparable Gulf crises"
   Bad:  "DoD Congressional appropriations cycle lead times"
   Prefer questions answerable from news archives, academic papers, FRED, or World Bank.

Return 2-4 of each type. Keep each gap description under 120 characters.

Return JSON:
{{
  "proprietary_gaps": ["gap 1", "gap 2"],
  "resolvable_gaps": ["gap 1", "gap 2", "gap 3"]
}}
Return ONLY valid JSON."""

        try:
            resp = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            parsed = json.loads(raw)
            session.data_gaps = [
                str(g).lstrip("- ").strip()
                for g in parsed.get("resolvable_gaps", []) if g
            ]
            session.proprietary_gaps = [
                str(g).lstrip("- ").strip()
                for g in parsed.get("proprietary_gaps", []) if g
            ]
            logger.info(
                "_identify_data_gaps: %d resolvable, %d proprietary",
                len(session.data_gaps), len(session.proprietary_gaps)
            )
        except Exception as exc:
            import traceback
            logger.error("_identify_data_gaps failed: %s\n%s", exc, traceback.format_exc())

    # ── Gap research loop ──────────────────────────────────────────────────

    async def run_gap_research(self, session: ForgeSession) -> AsyncIterator[str]:
        """
        Perplexity Sonar-powered gap research agent.

        For each resolvable data gap:
          1. Sonnet formulates a precise quantitative research question
          2. Perplexity Sonar answers with cited prose (full web index)
          3. Sonnet extracts: grounded?, value_note, param_key/value
          4. If not grounded and Perplexity key is absent, falls back to
             OpenAlex + FRED parallel fetch with haiku evaluation.
        """
        yield "Launching targeted gap research...\n"
        session.gap_research_running = True

        # On re-run, only research gaps not yet closed
        already_closed = set(session.closed_gaps or [])
        logger.info("GAP RERUN: already_closed=%d, data_gaps=%d, closed=%s",
                    len(already_closed), len(session.data_gaps),
                    [g[:40] for g in session.closed_gaps or []])
        gaps = [g for g in session.data_gaps if g not in already_closed]
        if not gaps:
            session.gap_research_running = False
            yield "No data gaps to research.\n"
            return

        ctx = session.research_context
        spec = session.simspec
        scenario_ctx = (
            f"{spec.name} | domain: {spec.domain} | "
            f"outcome: {(spec.metadata or {}).get('outcome_focus', '')}"
            if spec else "unknown scenario"
        )

        closed_gaps: list[str] = []
        all_param_updates: dict[str, float] = {}

        env_keys = list((session.simspec.initial_environment or {}).keys()) if session.simspec else []

        async with httpx.AsyncClient(timeout=35.0) as http:
            perplexity = PerplexityAdapter(http)
            oa         = OpenAlexAdapter(http)
            fred       = FredAdapter(http)

            for idx, gap in enumerate(gaps):
                yield f"[{idx + 1}/{len(gaps)}] {gap[:70]}\n"
                grounded, value_note, updates = await self._research_gap_perplexity(
                    gap, scenario_ctx, perplexity, oa, fred, env_keys=env_keys
                )
                if grounded:
                    closed_gaps.append(gap)
                    suffix = f": {value_note}" if value_note else ""
                    yield f"  ✓ Grounded{suffix}\n"
                    all_param_updates.update(updates)
                else:
                    yield f"  ○ Insufficient public data found\n"

        # Apply parameter updates
        for k, v in all_param_updates.items():
            try:
                ctx.parameter_estimates[k] = float(max(0.0, min(1.0, float(v))))
            except (ValueError, TypeError):
                pass
        if session.simspec and all_param_updates:
            env = session.simspec.initial_environment or {}
            for k, v in all_param_updates.items():
                try:
                    env[k] = float(max(0.0, min(1.0, float(v))))
                except (ValueError, TypeError):
                    pass

        # Accumulate — don't overwrite previous run's results
        session.closed_gaps = list(set(session.closed_gaps or []) | set(closed_gaps))
        session.remaining_gaps = [g for g in session.data_gaps if g not in session.closed_gaps]
        session.gap_research_running = False
        session.gap_research_complete = True

        yield f"\nClosed {len(closed_gaps)}/{len(gaps)} gaps. Updating ensemble...\n"
        theory_result = await self._run_theory_mapping(session)
        yield theory_result

    async def _research_gap_perplexity(
        self,
        gap: str,
        scenario_ctx: str,
        perplexity: PerplexityAdapter,
        oa: OpenAlexAdapter,
        fred: FredAdapter,
        env_keys: list[str] | None = None,
        max_rounds: int = 2,
    ) -> tuple[bool, str, dict]:
        """
        Research one data gap using Perplexity Sonar as the primary source.

        Flow:
          1. Sonnet formulates a precise quantitative research question for the gap
          2. Perplexity Sonar answers with cited prose
          3. Sonnet evaluates the answer: grounded?, extracts value_note + param hint
          4. If Perplexity unavailable, falls back to OpenAlex + FRED

        Returns (grounded, value_note, param_updates).
        """
        import os as _os

        has_perplexity = bool(_os.environ.get("PERPLEXITY_API_KEY", ""))

        # ── Step 1: Sonnet formulates the research question ────────────────────
        question_prompt = (
            f"Scenario context: {scenario_ctx}\n\n"
            f"Data gap to fill: {gap}\n\n"
            f"Write a single precise research question that would retrieve "
            f"quantitative data to fill this gap. The question should:\n"
            f"- Ask for specific numbers, percentages, rates, or ranges\n"
            f"- Reference the scenario context (industry, region, timeframe)\n"
            f"- Be answerable from public economic, policy, or industry data\n\n"
            f"Return ONLY the question as plain text, no JSON."
        )
        try:
            resp = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=120,
                messages=[{"role": "user", "content": question_prompt}],
            )
            research_question = resp.content[0].text.strip()
        except Exception:
            research_question = gap  # fallback to raw gap text

        # ── Step 2: Fetch answer ───────────────────────────────────────────────
        raw_answer = ""
        source_label = ""

        if has_perplexity:
            results = await perplexity.fetch(research_question, max_results=1)
            if results and results[0].ok:
                raw_answer = results[0].summary
                source_label = "Perplexity Sonar"
                logger.info("GAP [%s] question: %s", gap[:40], research_question[:80])
                logger.info("GAP [%s] perplexity ok, answer len=%d", gap[:40], len(raw_answer))
            else:
                err = results[0].error if results else "no results"
                logger.warning("GAP [%s] perplexity failed: %s", gap[:40], err)

        if not raw_answer:
            # Fallback: OpenAlex + FRED in parallel
            import re as _re
            fred_prompt = (
                f"For this data gap: {gap}\n"
                f"Name ONE FRED series ID (e.g. DCOILWTICO) or null.\n"
                f"Return ONLY JSON: {{\"fred\": \"SERIES_OR_NULL\"}}"
            )
            try:
                fr = self._client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=50,
                    messages=[{"role": "user", "content": fred_prompt}],
                )
                fred_raw = fr.content[0].text.strip()
                if fred_raw.startswith("```"):
                    fred_raw = fred_raw.split("```")[1].lstrip("json")
                fred_id = json.loads(fred_raw).get("fred", None)
                if fred_id:
                    fred_id = _re.split(r"[|,\s]+", str(fred_id).strip())[0].upper()
                    if fred_id in ("NULL", "NONE", "N/A", ""):
                        fred_id = None
            except Exception:
                fred_id = None

            tasks: list = [oa.fetch(gap[:80], max_results=3)]
            if fred_id:
                tasks.append(fred.fetch(fred_id, max_results=1))
            fallback_raw = await asyncio.gather(*tasks, return_exceptions=True)
            fallback_results = []
            for r in fallback_raw:
                if isinstance(r, list):
                    fallback_results.extend(x for x in r if x.ok)

            if fallback_results:
                raw_answer = "\n\n".join(
                    r.to_context_snippet() for r in fallback_results[:4]
                )[:2000]
                source_label = "OpenAlex/FRED"

        if not raw_answer:
            logger.warning("GAP [%s] no answer from any source", gap[:40])
            return False, "", {}

        # ── Step 3: Sonnet evaluates and extracts ──────────────────────────────
        env_keys_hint = (
            f"\nExisting sim environment keys (pick the closest match or null):\n{', '.join(env_keys[:40])}\n"
            if env_keys else ""
        )
        eval_prompt = (
            f"Data gap: {gap}\n"
            f"Scenario: {scenario_ctx}\n\n"
            f"Research answer ({source_label}):\n{raw_answer}\n\n"
            f"Does this answer provide a quantitative calibration anchor?\n"
            f"  grounded = contains a specific %, rate, price, elasticity, or range\n"
            f"  insufficient = only qualitative, no usable numbers\n"
            f"{env_keys_hint}\n"
            f"Return ONLY JSON:\n"
            f'{{"grounded": true/false, '
            f'"value_note": "e.g. freight rates +40% during 1984 tanker war", '
            f'"param_key": "exact_key_from_list_above_or_null", '
            f'"param_value_0_to_1": 0.4}}'
        )
        try:
            resp2 = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=200,
                messages=[{"role": "user", "content": eval_prompt}],
            )
            raw2 = resp2.content[0].text.strip()
            if raw2.startswith("```"):
                raw2 = raw2.split("```")[1].lstrip("json")
            ev = json.loads(raw2)
            logger.info("GAP [%s] eval: grounded=%s note=%s", gap[:40], ev.get("grounded"), ev.get("value_note", "")[:60])
            if ev.get("grounded"):
                value_note = ev.get("value_note") or ""
                updates: dict[str, float] = {}
                pk = ev.get("param_key")
                pv = ev.get("param_value_0_to_1")
                if pk and pv is not None and str(pk).lower() not in ("null", "none"):
                    try:
                        updates[str(pk)] = float(max(0.0, min(1.0, float(pv))))
                    except (ValueError, TypeError):
                        pass
                return True, value_note, updates
        except Exception as _exc:
            logger.error("GAP [%s] eval exception: %s", gap[:40], _exc)

        # ── Round 2: reframe using proxy angle ────────────────────────────────
        if not has_perplexity:
            return False, "", {}

        reframe_prompt = (
            f"The following research question did not yield quantitative data:\n"
            f"Original question: {research_question}\n\n"
            f"Data gap: {gap}\n"
            f"Scenario: {scenario_ctx}\n\n"
            f"Reframe this as a PROXY question — ask for related or analogous data "
            f"that could serve as a calibration anchor even if it doesn't directly "
            f"answer the original gap. Examples:\n"
            f"  - If direct shipping rate data is paywalled, ask about Baltic Dry Index "
            f"    or historical tanker war freight impacts\n"
            f"  - If franchise-specific data is unavailable, ask about food service "
            f"    industry margin compression during oil price shocks\n"
            f"Write ONE reframed question as plain text only."
        )
        try:
            resp_reframe = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=120,
                messages=[{"role": "user", "content": reframe_prompt}],
            )
            proxy_question = resp_reframe.content[0].text.strip()
        except Exception:
            return False, "", {}

        # Fetch proxy answer from Perplexity
        proxy_results = await perplexity.fetch(proxy_question, max_results=1)
        if not proxy_results or not proxy_results[0].ok:
            return False, "", {}

        proxy_answer = proxy_results[0].summary

        # Re-evaluate with proxy answer
        proxy_eval_prompt = (
            f"Data gap: {gap}\n"
            f"Scenario: {scenario_ctx}\n\n"
            f"We couldn't find direct data, so we searched for a proxy:\n"
            f"Proxy question: {proxy_question}\n"
            f"Proxy answer:\n{proxy_answer}\n\n"
            f"Can this proxy data serve as a calibration anchor for the original gap?\n"
            f"  grounded = yes, contains usable numbers that could substitute\n"
            f"  insufficient = proxy is too distant or still qualitative only\n\n"
            f"Return ONLY JSON:\n"
            f'{{"grounded": true/false, '
            f'"value_note": "proxy: e.g. Baltic Dry Index fell 60% during Gulf War", '
            f'"param_key": "snake_case_sim_env_key_or_null", '
            f'"param_value_0_to_1": 0.4}}'
        )
        try:
            resp3 = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=200,
                messages=[{"role": "user", "content": proxy_eval_prompt}],
            )
            raw3 = resp3.content[0].text.strip()
            if raw3.startswith("```"):
                raw3 = raw3.split("```")[1].lstrip("json")
            ev3 = json.loads(raw3)
            if ev3.get("grounded"):
                value_note = ev3.get("value_note") or ""
                updates: dict[str, float] = {}
                pk = ev3.get("param_key")
                pv = ev3.get("param_value_0_to_1")
                if pk and pv is not None and str(pk).lower() not in ("null", "none"):
                    try:
                        updates[str(pk)] = float(max(0.0, min(1.0, float(pv))))
                    except (ValueError, TypeError):
                        pass
                return True, value_note, updates
        except Exception:
            pass

        return False, "", {}

    async def _finalize_ensemble(self, session: ForgeSession) -> str:
        """
        Commit the active ensemble (custom if set, else recommended) to simspec.theories
        and run validation.
        """
        active = session.active_theories
        theories = [
            TheoryRef(
                theory_id=t["theory_id"],
                priority=t.get("suggested_priority", t.get("priority", 0)),
                parameters=t.get("parameters", {}),
            )
            for t in active
        ]
        object.__setattr__(session.simspec, "theories", theories)
        session.state = ForgeState.VALIDATION
        return await self._run_validation(session)

    async def _run_validation(self, session: ForgeSession) -> str:
        from pydantic import ValidationError
        try:
            # ensure metrics reference existing env keys
            _ensure_metrics_consistent(session.simspec)
            SimSpec.model_validate(session.simspec.model_dump())
            session.mark_complete()
            theory_names = ", ".join(t.theory_id for t in session.simspec.theories)
            return (
                f"Your simulation **'{session.simspec.name}'** is configured and ready to run.\n\n"
                f"- **Actors:** {len(session.simspec.actors)}\n"
                f"- **Theories:** {theory_names or 'none selected'}\n"
                f"- **Timeframe:** {session.simspec.timeframe.total_ticks} "
                f"{session.simspec.timeframe.tick_unit}s\n\n"
                f"Use `POST /simulations` to launch the simulation."
            )
        except (ValidationError, ValueError) as e:
            logger.warning("Validation failed: %s", e)
            # re-open gaps for any validation errors
            for err in (e.errors() if hasattr(e, "errors") else []):
                path = ".".join(str(x) for x in err.get("loc", []))
                gap = SpecGap(field_path=path, description=err["msg"], priority=1.0)
                session.gaps.append(gap)
            if session.turn_count < MAX_TURNS:
                session.state = ForgeState.DYNAMIC_INTERVIEW
                reply = ""
                async for chunk in self._run_interview_turn(session, user_message=None):
                    reply = chunk
                return reply
            # Give up and return partial
            session.mark_complete()
            return (
                f"Simulation '{session.simspec.name}' configured with some gaps remaining. "
                f"Review with GET /forge/intake/{session.session_id}."
            )

    # ── Tool dispatch ──────────────────────────────────────────────────────

    async def _dispatch_tool(
        self,
        name: str,
        inputs: dict[str, Any],
        session: ForgeSession,
    ) -> tuple[Any, bool]:
        """
        Execute a tool call. Returns (result, stop_for_user).
        stop_for_user=True means ask_user was called — return to caller.
        """
        ctx = session.research_context

        if name == "search_ssrn":
            async with httpx.AsyncClient(timeout=15.0) as http:
                results = await SsrnAdapter(http).fetch(
                    inputs["query"], max_results=inputs.get("max_results", 5)
                )
            ctx.results.extend(results)
            return [r.to_context_snippet() for r in results if r.ok], False

        if name == "search_fred":
            series_ids = inputs.get("series_ids", [])
            results: list = []
            async with httpx.AsyncClient(timeout=15.0) as http:
                adapter = FredAdapter(http)
                for sid in series_ids[:5]:
                    r = await adapter.fetch(sid, max_results=1)
                    results.extend(r)
            ctx.results.extend(results)
            return [r.to_context_snippet() for r in results if r.ok], False

        if name == "search_world_bank":
            indicators = " ".join(inputs.get("indicators", []))
            async with httpx.AsyncClient(timeout=15.0) as http:
                results = await WorldBankAdapter(http).fetch(indicators, max_results=5)
            ctx.results.extend(results)
            return [r.to_context_snippet() for r in results if r.ok], False

        if name == "search_news":
            async with httpx.AsyncClient(timeout=15.0) as http:
                results = await NewsAdapter(http).fetch(
                    inputs["query"], max_results=5
                )
            ctx.results.extend(results)
            return [r.to_context_snippet() for r in results if r.ok], False

        if name == "update_simspec":
            patch = inputs.get("patch", {})
            # Block timeframe_ticks from being auto-filled before the user is asked.
            # Only allow it once the timeframe gap has been explicitly filled by the user.
            if "timeframe_ticks" in patch:
                timeframe_gap = next(
                    (g for g in session.gaps if g.field_path == "timeframe"), None
                )
                if not (timeframe_gap and timeframe_gap.filled):
                    patch = {k: v for k, v in patch.items() if k != "timeframe_ticks"}
                    logger.debug("update_simspec: blocked auto-fill of timeframe_ticks")
            _apply_patch(session.simspec, patch)
            open_gaps = session.open_gaps()
            remaining = [
                {"field_path": g.field_path, "description": g.description}
                for g in open_gaps[:5]
            ]
            return {
                "ok": True,
                "spec_name": session.simspec.name,
                "remaining_gaps": remaining,
                "next_step": (
                    "Call ask_user for the highest-priority gap above."
                    if remaining else
                    "All gaps filled — call select_theories then finalize."
                ),
            }, False

        if name == "identify_gap":
            gap = SpecGap(
                field_path=inputs["field_path"],
                description=inputs["description"],
                priority=float(inputs.get("priority", 0.5)),
            )
            _merge_gaps(session.gaps, [gap])
            return {"gap_id": gap.gap_id}, False

        if name == "ask_user":
            question = inputs["question"]
            context  = inputs.get("context", "")
            options  = inputs.get("options", [])
            full_question = question
            if context:
                full_question = f"{question}\n\n*Context: {context}*"
            if options:
                opts = "\n".join(f"- {o}" for o in options)
                full_question += f"\n\nSuggested options:\n{opts}"
            return {"question": full_question}, True  # stop_for_user=True

        if name == "select_theories":
            theories_mode = (session.simspec.metadata or {}).get("theories_mode", "empirical")
            recs = self._theory_mapper.recommend_from_spec(
                session.simspec,
                preferred_framework=None if theories_mode == "empirical" else theories_mode,
            )
            theories = [
                TheoryRef(theory_id=r.theory_id, priority=r.suggested_priority)
                for r in recs
            ]
            object.__setattr__(session.simspec, "theories", theories)
            session.state = ForgeState.VALIDATION
            return {"theories": [t.theory_id for t in theories]}, False

        if name == "finalize":
            reply = await self._run_validation(session)
            return {"status": session.state.value, "message": reply}, False

        return {"error": f"Unknown tool: {name}"}, False

    # ── Helpers ────────────────────────────────────────────────────────────

    def _mark_research_filled_gaps(self, session: ForgeSession) -> None:
        calibrated = session.research_context.env_keys_calibrated
        for gap in session.gaps:
            if not gap.filled and gap.field_path in calibrated:
                gap.filled = True
                gap.filled_by = "research"

    def _auto_fill_gaps(self, session: ForgeSession) -> None:
        for gap in session.open_gaps():
            self._spec_builder.infer_gap(session.simspec, gap, session.research_context)
            gap.filled = True
            gap.filled_by = "inference"


# ── Helpers ────────────────────────────────────────────────────────────────

def _build_claude_messages(session: ForgeSession) -> list[dict[str, Any]]:
    """Build the messages list for the Claude API from conversation history."""
    messages = []
    # system message is passed separately; only include user/assistant here
    if session.intake_text and not session.conversation_history:
        messages.append({"role": "user", "content": session.intake_text})
        return messages

    for msg in session.conversation_history:
        if msg.role in (MessageRole.USER, MessageRole.ASSISTANT):
            messages.append({"role": msg.role.value, "content": msg.content})

    # ensure alternating roles (Claude API requirement)
    if not messages:
        messages.append({"role": "user", "content": session.intake_text})

    return messages


def _spec_summary(simspec: SimSpec | None) -> str:
    if not simspec:
        return "No SimSpec yet."
    actors = ", ".join(a.name for a in simspec.actors[:5]) or "none"
    theories = ", ".join(t.theory_id for t in simspec.theories) or "none"
    return (
        f"Name: {simspec.name}\n"
        f"Domain: {simspec.domain or 'unknown'}\n"
        f"Actors: {actors}\n"
        f"Theories: {theories}\n"
        f"Timeframe: {simspec.timeframe.total_ticks} {simspec.timeframe.tick_unit}s\n"
        f"Env keys: {len(simspec.initial_environment)}"
    )


def _apply_patch(simspec: SimSpec, patch: dict[str, Any]) -> None:
    """Apply a partial patch dict to a SimSpec in place."""
    if "name" in patch:
        object.__setattr__(simspec, "name", patch["name"])
    if "description" in patch:
        object.__setattr__(simspec, "description", patch["description"])
    if "domain" in patch:
        object.__setattr__(simspec, "domain", patch["domain"])
    if "initial_environment" in patch:
        env = dict(simspec.initial_environment)
        env.update({
            k: float(max(0.0, min(1.0, float(v))))
            for k, v in patch["initial_environment"].items()
        })
        object.__setattr__(simspec, "initial_environment", env)
    if "timeframe_ticks" in patch:
        ticks = patch["timeframe_ticks"]
        if isinstance(ticks, int) and ticks > 0:
            object.__setattr__(simspec.timeframe, "total_ticks", ticks)
    if "metadata" in patch:
        meta = dict(simspec.metadata)
        meta.update(patch["metadata"])
        # If agent is recording a theories answer that isn't actual TheoryRef objects,
        # treat it as "empirical" mode so gap_detector won't re-flag theories.
        if "theories" in patch["metadata"] and not simspec.theories:
            meta["theories_mode"] = "empirical"
        object.__setattr__(simspec, "metadata", meta)
    if "theories_mode" in patch:
        meta = dict(simspec.metadata)
        meta["theories_mode"] = patch["theories_mode"]
        object.__setattr__(simspec, "metadata", meta)
    if "actors" in patch:
        from core.spec import ActorSpec
        for actor_data in patch["actors"]:
            actor_id = actor_data.get("actor_id", "")
            if not any(a.actor_id == actor_id for a in simspec.actors):
                simspec.actors.append(ActorSpec(
                    actor_id=actor_id or f"actor_{len(simspec.actors)}",
                    name=actor_data.get("name", actor_id),
                    metadata={
                        "role": actor_data.get("role", "other"),
                        "belief_state": actor_data.get("belief_state") or {},
                        "description": actor_data.get("description", ""),
                    },
                ))


def _ensure_metrics_consistent(simspec: SimSpec) -> None:
    """
    Remove any metrics whose env_key is not in initial_environment.
    If no metrics exist, auto-generate them from the most interesting env keys.
    Prevents ValidationError from stale metrics.
    """
    from core.spec import OutcomeMetricSpec
    env_keys = set(simspec.initial_environment.keys())

    # Remove stale metrics
    valid_metrics = [m for m in simspec.metrics if m.env_key in env_keys]

    # Auto-generate metrics if none defined
    if not valid_metrics and env_keys:
        # Skip internal/structural keys and static baseline/parameter keys
        skip_prefixes = (
            "cobweb__", "richardson__", "wittman__", "global__",
            "baseline_", "initial_", "param_", "config_", "default_",
        )
        skip_suffixes = ("_tick", "_seed", "_rng", "_baseline", "_initial", "_param")
        candidates = [
            k for k in sorted(env_keys)
            if not any(k.startswith(p) for p in skip_prefixes)
            and not any(k.endswith(s) for s in skip_suffixes)
        ]
        # If filtering removes everything, fall back to all keys (better than nothing)
        if not candidates:
            candidates = [k for k in sorted(env_keys)
                          if not any(k.endswith(s) for s in ("_tick", "_seed", "_rng"))]
        # Cap at 8 metrics
        for key in candidates[:8]:
            label = key.replace("__", ": ").replace("_", " ").title()
            valid_metrics.append(OutcomeMetricSpec(
                name=label,
                env_key=key,
            ))

    object.__setattr__(simspec, "metrics", valid_metrics)
