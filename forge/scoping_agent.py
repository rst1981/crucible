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
from typing import Any, AsyncIterator

import httpx
from anthropic import Anthropic

from core.spec import SimSpec, TheoryRef
from forge.gap_detector import detect_gaps, _merge_gaps
from forge.researchers.arxiv import ArxivAdapter
from forge.researchers.fred import FredAdapter
from forge.researchers.news import NewsAdapter
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
4. After research completes, call update_simspec with everything you learned,
   then identify_gap for any remaining unknowns, then ask_user for the most
   important gap.
5. When all critical gaps are filled, call select_theories then finalize.
"""

# ── Tool schemas ───────────────────────────────────────────────────────────

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_arxiv",
        "description": (
            "Search arXiv preprints for academic research relevant to the scenario. "
            "Use for theoretical frameworks, empirical studies, domain models."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query":       {"type": "string"},
                "max_results": {"type": "integer", "default": 5, "maximum": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_ssrn",
        "description": "Search SSRN for working papers in economics, finance, law, social science.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":       {"type": "string"},
                "max_results": {"type": "integer", "default": 5, "maximum": 10},
            },
            "required": ["query"],
        },
    },
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
                        "timeframe_ticks (int), actors (list of {actor_id,name,role})."
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
            return await self._run_interview_turn(session, user_message)
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

            yield "Running parallel research (arXiv, SSRN, FRED, World Bank, news)...\n"
            await self._run_research(session)
            self._spec_builder.apply_research_hints(session.simspec, session.research_context)
            session.gaps = detect_gaps(session.simspec)
            self._mark_research_filled_gaps(session)
            session.state = ForgeState.DYNAMIC_INTERVIEW

            ctx = session.research_context
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

            yield "Research complete. Generating first question...\n"
            reply = await self._run_interview_turn(session, user_message=None)
            yield reply

        elif session.state == ForgeState.DYNAMIC_INTERVIEW:
            reply = await self._run_interview_turn(session, user_message)
            yield reply

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

        await self._run_research(session)
        self._spec_builder.apply_research_hints(session.simspec, session.research_context)
        session.gaps = detect_gaps(session.simspec)
        self._mark_research_filled_gaps(session)
        session.state = ForgeState.DYNAMIC_INTERVIEW

        return await self._run_interview_turn(session, user_message=None)

    async def _run_research(self, session: ForgeSession) -> None:
        """Fan-out research across all adapters in parallel."""
        spec = session.simspec
        domain_query = f"{spec.domain} {spec.description} {session.intake_text}"[:200]
        actor_names = " ".join(a.name for a in spec.actors[:5])
        academic_query = f"{domain_query} {actor_names} formal model simulation"

        async with httpx.AsyncClient(timeout=20.0) as http:
            arxiv  = ArxivAdapter(http)
            ssrn   = SsrnAdapter(http)
            fred   = FredAdapter(http)
            wb     = WorldBankAdapter(http)
            news   = NewsAdapter(http)

            results = await asyncio.gather(
                arxiv.fetch(academic_query, max_results=5),
                ssrn.fetch(academic_query, max_results=5),
                fred.fetch("GDP CPIAUCSL DCOILWTICO", max_results=3),
                wb.fetch("NY.GDP.MKTP.CD MS.MIL.XPND.GD.ZS NE.TRD.GNFS.ZS", max_results=5),
                news.fetch(domain_query, max_results=5),
                return_exceptions=True,
            )

        ctx = session.research_context
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Research adapter error: %s", result)
                continue
            if isinstance(result, list):
                ctx.results.extend(result)

        # Library gap fill: run academic results through TheoryBuilder.
        # Papers containing new formal models not yet in the library are
        # auto-approved (if smoke test passes) or queued for review.
        academic = [r for r in ctx.results if r.source_type in ("arxiv", "ssrn") and r.ok]
        if academic:
            await self._fill_library_gaps(academic, ctx)

        # extraction pass: use Claude to pull theory candidates + param estimates
        # (runs after gap fill so newly added theories appear in list_theories())
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
    ) -> str:
        if user_message:
            self._spec_builder.apply_user_answer(
                session.simspec, session.gaps, user_message
            )
            new_gaps = detect_gaps(session.simspec)
            _merge_gaps(session.gaps, new_gaps)
            self._mark_research_filled_gaps(session)

        open_gaps = session.open_gaps()
        if not open_gaps or session.turn_count >= MAX_TURNS:
            self._auto_fill_gaps(session)
            session.state = ForgeState.THEORY_MAPPING
            return await self._run_theory_mapping(session)

        # Use Claude tool-use for the next question
        return await self._agent_turn(session)

    async def _agent_turn(self, session: ForgeSession) -> str:
        """
        Run one Claude tool-use turn. The agent can call research tools,
        update_simspec, identify_gap, and ask_user. We loop until ask_user
        or finalize is called, then return.
        """
        # Build conversation for Claude
        messages = _build_claude_messages(session)

        # Inject current spec state as context
        spec_summary = _spec_summary(session.simspec)
        open_gap_text = "\n".join(
            f"- [{g.priority:.1f}] {g.field_path}: {g.description}"
            for g in session.open_gaps()[:5]
        )
        context_injection = (
            f"\n\nCurrent SimSpec state:\n{spec_summary}"
            f"\n\nOpen gaps:\n{open_gap_text}"
            f"\n\nTurn {session.turn_count}/{MAX_TURNS}."
        )
        if messages and messages[-1]["role"] == "user":
            messages[-1]["content"] += context_injection
        else:
            messages.append({"role": "user", "content": context_injection})

        # Tool-use loop
        max_tool_rounds = 20
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
            logger.info("_agent_turn round %d: tools=%s", round_num, [b.name for b in tool_blocks])

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
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": json.dumps(result),
                })
                if stop:
                    asked_user = True
                    final_reply = result.get("question", str(result))

            messages.append({"role": "user", "content": tool_results})

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

    async def _run_theory_mapping(self, session: ForgeSession) -> str:
        # Include any theories auto-added to the library during research
        # in the mapper's candidate pool (they're already registered).
        recommendations = self._theory_mapper.recommend_from_spec(session.simspec)

        # Store recommendations on session — do NOT commit to simspec.theories yet.
        # The consultant reviews and optionally edits before finalizing.
        session.recommended_theories = [
            {
                "theory_id":         r.theory_id,
                "display_name":      r.display_name,
                "score":             r.score,
                "rationale":         r.rationale,
                "suggested_priority": r.suggested_priority,
                "domains":           r.domains,
                "source":            r.source,
            }
            for r in recommendations
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
        Present the recommended ensemble to the consultant and ask whether they
        want to accept it, modify it, or build a custom ensemble alongside.

        The consultant can:
          - Accept as-is → calls PUT /forge/intake/{id}/theories/accept
          - Submit custom list → PUT /forge/intake/{id}/theories/custom
          - Both run when POST /simulations is called (recommended + custom)
        """
        recs = session.recommended_theories
        if not recs:
            # No recommendations — go straight to validation with empty theories
            return await self._finalize_ensemble(session)

        lines = ["**Recommended theory ensemble** (ranked by domain relevance):\n"]
        for i, r in enumerate(recs):
            src = " *(new — added to library)*" if r["source"] == "discovered" else ""
            lines.append(
                f"{i+1}. **{r['display_name']}**{src} — score {r['score']:.2f}  \n"
                f"   *{r['rationale']}*"
            )

        additions = session.research_context.library_additions
        if additions:
            lines.append(
                f"\n*{len(additions)} new theor"
                f"{'y' if len(additions) == 1 else 'ies'} built from research and added "
                f"to the library: {', '.join(additions)}.*"
            )

        lines.append(
            "\n\nYou can:\n"
            "- **Accept** this ensemble → `PUT /forge/intake/{session_id}/theories/accept`\n"
            "- **Customize** → `PUT /forge/intake/{session_id}/theories/custom` "
            "with `{\"theories\": [{\"theory_id\": \"...\", \"priority\": 0}]}`\n"
            "- Run **both** for comparison once you launch via `POST /simulations`\n\n"
            "What would you like to change, or shall I proceed with the recommended ensemble?"
        )
        reply = "\n".join(lines)
        session.add_message(MessageRole.ASSISTANT, reply)
        return reply

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
                return await self._run_interview_turn(session, user_message=None)
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

        if name == "search_arxiv":
            async with httpx.AsyncClient(timeout=15.0) as http:
                results = await ArxivAdapter(http).fetch(
                    inputs["query"], max_results=inputs.get("max_results", 5)
                )
            ctx.results.extend(results)
            return [r.to_context_snippet() for r in results if r.ok], False

        if name == "search_ssrn":
            async with httpx.AsyncClient(timeout=15.0) as http:
                results = await SsrnAdapter(http).fetch(
                    inputs["query"], max_results=inputs.get("max_results", 5)
                )
            ctx.results.extend(results)
            return [r.to_context_snippet() for r in results if r.ok], False

        if name == "search_fred":
            async with httpx.AsyncClient(timeout=15.0) as http:
                results = await FredAdapter(http).fetch(
                    " ".join(inputs.get("series_ids", [])), max_results=5
                )
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
            _apply_patch(session.simspec, patch)
            return {"ok": True, "spec_name": session.simspec.name}, False

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
            recs = self._theory_mapper.recommend_from_spec(session.simspec)
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
    if "actors" in patch:
        from core.spec import ActorSpec
        for actor_data in patch["actors"]:
            actor_id = actor_data.get("actor_id", "")
            if not any(a.actor_id == actor_id for a in simspec.actors):
                simspec.actors.append(ActorSpec(
                    actor_id=actor_id or f"actor_{len(simspec.actors)}",
                    name=actor_data.get("name", actor_id),
                    role=actor_data.get("role", "other"),
                    belief_state=actor_data.get("belief_state") or {},
                ))


def _ensure_metrics_consistent(simspec: SimSpec) -> None:
    """
    Remove any metrics whose env_key is not in initial_environment.
    Prevents ValidationError from stale metrics.
    """
    if not simspec.metrics:
        return
    env_keys = set(simspec.initial_environment.keys())
    valid_metrics = [m for m in simspec.metrics if m.env_key in env_keys]
    object.__setattr__(simspec, "metrics", valid_metrics)
