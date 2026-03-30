"""
api/routers/forge.py — Intake / Scoping Agent routes

POST /forge/intake                                   Create a new scoping session
GET  /forge/intake/{session_id}                      Poll session state + SimSpec progress
POST /forge/intake/{session_id}/message              Stream agent response (SSE)
DELETE /forge/intake/{session_id}                    Delete session
GET  /forge/intake/{session_id}/theories             Recommended ensemble + scores
PUT  /forge/intake/{session_id}/theories/accept      Accept recommended ensemble as-is
PUT  /forge/intake/{session_id}/theories/custom      Submit a custom ensemble
GET  /forge/theories/library                         All registered theories
GET  /forge/theories/pending                         Pending review queue
POST /forge/theories/pending/{id}/approve            Approve + hot-load
POST /forge/theories/pending/{id}/reject             Reject
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from forge.scoping_agent import ScopingAgent
from forge.session import ForgeSession, ForgeState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forge", tags=["forge"])


# ── Session store (Postgres on Railway, file fallback for local dev) ─────────

import pathlib, json as _json
from forge import session_store as _store

_sessions: dict[str, ForgeSession] = {}


def _save_session(session: ForgeSession) -> None:
    """Fire-and-forget async save — creates a task so we never block the request."""
    try:
        asyncio.get_event_loop().create_task(_store.save(session.to_dict()))
    except RuntimeError:
        # No running loop (e.g. during tests) — skip
        pass


async def _load_sessions() -> None:
    """Load all persisted sessions into memory on startup."""
    await _store.init()
    all_data = await _store.load_all()
    from forge.session import ForgeState, ResearchContext, SpecGap
    from core.spec import SimSpec
    for data in all_data:
        try:
            session = ForgeSession(intake_text=data.get("intake_text", ""))
            session.session_id           = data["session_id"]
            session.state                = ForgeState(data.get("state", "complete"))
            session.domain               = data.get("domain", "")
            session.turn_count           = data.get("turn_count", 0)
            session.created_at           = data.get("created_at", 0.0)
            session.completed_at         = data.get("completed_at")
            session.recommended_theories = data.get("recommended_theories", [])
            session.discovered_theories  = data.get("discovered_theories", [])
            session.custom_theories      = data.get("custom_theories")
            session.assessment_path      = data.get("assessment_path")
            session.assessment_md        = data.get("assessment_md")
            session.findings_path        = data.get("findings_path")
            session.findings_md          = data.get("findings_md")
            # If a job was "running" when the container died, mark it failed so
            # the frontend doesn't poll forever waiting for a task that's gone.
            raw_job_status = data.get("findings_job_status", "not_started")
            if raw_job_status == "running":
                raw_job_status = "error"
                session.findings_job_error = "Service restarted while findings were generating — please try again."
            else:
                session.findings_job_error = data.get("findings_job_error")
            session.findings_job_status = raw_job_status
            session.data_gaps            = data.get("data_gaps", [])
            session.proprietary_gaps     = data.get("proprietary_gaps", [])
            session.gap_research_running  = False  # never resume mid-run
            session.gap_research_complete = data.get("gap_research_complete", False)
            session.closed_gaps          = data.get("closed_gaps", [])
            session.remaining_gaps       = data.get("remaining_gaps", [])
            if data.get("simspec"):
                session.simspec = SimSpec.model_validate(data["simspec"])
            ctx = session.research_context
            research = data.get("research", {})
            ctx.parameter_estimates = research.get("parameter_estimates", {})
            ctx.library_additions   = research.get("library_additions", [])
            _sessions[session.session_id] = session
            logger.info("Restored session %s (%s)", session.session_id, session.state)
        except Exception as exc:
            logger.warning("Failed to restore session: %s", exc)


def _get_session(session_id: str) -> ForgeSession:
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    return session


# ── Shared agent instance (stateless — all state is in ForgeSession) ───────

_agent = ScopingAgent()


# ── Request / Response models ──────────────────────────────────────────────

class IntakeRequest(BaseModel):
    intake_text: str

class MessageRequest(BaseModel):
    message: str


# ── Routes ─────────────────────────────────────────────────────────────────

@router.post("/intake", status_code=201)
async def create_session(body: IntakeRequest) -> dict:
    """
    Start a new scoping session from a free-text scenario description.
    Returns session_id immediately — research and first question are generated
    asynchronously via POST /forge/intake/{session_id}/message.
    """
    session = ScopingAgent.create_session(body.intake_text)
    _sessions[session.session_id] = session
    _save_session(session)
    logger.info("Created session %s", session.session_id)
    return {
        "session_id": session.session_id,
        "state":      session.state.value,
        "message":    "Session created. Send a message to begin.",
    }


@router.get("/intake/{session_id}")
async def get_session(session_id: str) -> dict:
    """
    Poll session state and current SimSpec progress.
    Returns full session dict including partial SimSpec, gaps, and message history.
    """
    session = _get_session(session_id)
    return session.to_dict()


@router.post("/intake/{session_id}/message")
async def send_message(session_id: str, body: MessageRequest, request: Request):
    """
    Send a user message to the scoping agent and stream the response via SSE.

    SSE event format:
        data: {"type": "chunk",  "text": "..."}
        data: {"type": "done",   "state": "dynamic_interview", "simspec": {...}}
        data: {"type": "error",  "detail": "..."}
    """
    session = _get_session(session_id)

    if session.state == ForgeState.COMPLETE:
        # Already complete — return a simple JSON response, no streaming needed
        return {
            "state":   session.state.value,
            "message": f"Session already complete. SimSpec: '{session.simspec.name}'.",
            "simspec": session.simspec.model_dump() if session.simspec else None,
        }

    async def event_stream():
        try:
            # If this is the very first message and state is INTAKE, pass None
            # so the agent runs the full intake pipeline first.
            user_msg = body.message if session.state != ForgeState.INTAKE else None

            # Drain the generator into a queue from a background task so we
            # can send SSE heartbeats without cancelling long-running awaits
            # (asyncio.wait_for cancels the coroutine on timeout).
            chunk_queue: asyncio.Queue = asyncio.Queue()

            async def _drain():
                try:
                    async for chunk in _agent.turn_stream(session, user_message=user_msg):
                        await chunk_queue.put(("chunk", chunk))
                    await chunk_queue.put(("done", None))
                except Exception as exc:  # noqa: BLE001
                    await chunk_queue.put(("error", exc))

            drain_task = asyncio.create_task(_drain())

            full_reply = ""
            while True:
                try:
                    kind, value = await asyncio.wait_for(
                        chunk_queue.get(), timeout=15.0
                    )
                except asyncio.TimeoutError:
                    # Generator is still running — keep connection alive
                    yield ": heartbeat\n\n"
                    continue

                if kind == "done":
                    break
                if kind == "error":
                    raise value  # type: ignore[misc]

                # kind == "chunk"
                chunk: str = value  # type: ignore[assignment]
                full_reply += chunk
                payload = json.dumps({"type": "chunk", "text": chunk})
                yield f"data: {payload}\n\n"
                if await request.is_disconnected():
                    logger.info("Client disconnected during session %s", session_id)
                    drain_task.cancel()
                    return

            _save_session(session)
            done_payload = json.dumps({
                "type":    "done",
                "state":   session.state.value,
                "simspec": session.simspec.model_dump() if session.simspec else None,
                "gaps":    [g.to_dict() for g in session.open_gaps()],
            })
            yield f"data: {done_payload}\n\n"

        except Exception as exc:
            logger.exception("Error in session %s", session_id)
            error_payload = json.dumps({"type": "error", "detail": str(exc)})
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/generate-scenario")
async def generate_scenario() -> dict:
    """Generate an Accenture LLP-relevant scenario prompt."""
    import random
    from anthropic import Anthropic
    client = Anthropic()

    themes = [
        "financial services regulatory change",
        "pharmaceutical supply chain disruption",
        "central bank policy and credit markets",
        "energy transition and stranded assets",
        "sovereign debt and emerging market contagion",
        "technology platform antitrust action",
        "insurance market stress from climate events",
        "global trade route disruption",
        "workforce displacement from automation",
        "private equity portfolio stress",
    ]
    theme = random.choice(themes)

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=180,
        messages=[{"role": "user", "content": (
            f"Write a simulation scenario brief for an Accenture LLP consulting engagement. "
            f"Theme: {theme}. "
            f"Format: 2-3 sentences written as a consultant briefing a partner. "
            f"Describe the strategic situation and the client's concern — do not name specific countries, "
            f"companies, percentages, or dates. Keep it broad enough that the analyst will define those details. "
            f"End with a clear analytical question the simulation should answer. "
            f"Do not use bullet points. Plain prose only."
        )}],
    )
    return {"scenario": resp.content[0].text.strip()}


@router.delete("/intake/{session_id}", status_code=200)
async def delete_session(session_id: str) -> dict:
    """Delete a scoping session."""
    _get_session(session_id)  # 404 if not found
    del _sessions[session_id]
    await _store.delete(session_id)
    return {"deleted": True}


# ── Ensemble review routes ─────────────────────────────────────────────────────

@router.get("/intake/{session_id}/theories")
async def get_theories(session_id: str) -> dict:
    """
    Return the recommended and custom ensembles for a session.
    Available once the session reaches ensemble_review or complete state.
    """
    session = _get_session(session_id)
    if not session.recommended_theories:
        raise HTTPException(
            status_code=409,
            detail="Recommended ensemble not yet generated. Session must reach ensemble_review state.",
        )
    from core.theories import list_theories, get_theory
    library = set(list_theories())
    return {
        "session_id":           session_id,
        "state":                session.state.value,
        "recommended":          session.recommended_theories,
        "custom":               session.custom_theories,
        "active_ensemble":      "custom" if session.custom_theories is not None else "recommended",
        "library_size":         len(library),
        "library_additions":    session.research_context.library_additions,
    }


class CustomEnsembleRequest(BaseModel):
    theories: list[dict]  # list of {theory_id, priority?, parameters?}


@router.put("/intake/{session_id}/theories/accept", status_code=200)
async def accept_recommended(session_id: str) -> dict:
    """
    Accept the recommended ensemble as-is.
    Clears any custom ensemble and finalizes the session.
    """
    session = _get_session(session_id)
    if not session.recommended_theories:
        raise HTTPException(status_code=409, detail="No recommended ensemble yet")
    session.custom_theories = None  # clear any previous custom
    _save_session(session)
    return {
        "ensemble_type": "recommended",
        "theories": session.recommended_theories,
        "message": "Recommended ensemble accepted. Launch with POST /simulations.",
    }


@router.put("/intake/{session_id}/theories/custom", status_code=200)
async def set_custom_ensemble(session_id: str, body: CustomEnsembleRequest) -> dict:
    """
    Set a custom theory ensemble for this session.

    The consultant provides a list of {theory_id, priority?, parameters?}.
    All theory_ids must be registered in the library.
    Both the recommended and custom ensembles will run when POST /simulations is called.
    """
    session = _get_session(session_id)
    from core.theories import list_theories
    library = set(list_theories())

    unknown = [t["theory_id"] for t in body.theories if t["theory_id"] not in library]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown theory IDs: {unknown}. Available: {sorted(library)}",
        )

    session.custom_theories = [
        {
            "theory_id":          t["theory_id"],
            "suggested_priority": t.get("priority", i),
            "parameters":         t.get("parameters", {}),
            "source":             "custom",
        }
        for i, t in enumerate(body.theories)
    ]
    _save_session(session)
    return {
        "ensemble_type": "custom",
        "theories":      session.custom_theories,
        "message": (
            f"Custom ensemble set ({len(session.custom_theories)} theories). "
            "Both recommended and custom will run at POST /simulations."
        ),
    }


# ── Assessment generation ─────────────────────────────────────────────────────

@router.post("/intake/{session_id}/assessment", status_code=200)
async def generate_assessment(session_id: str) -> dict:
    """
    Generate assessment MD + PDF for a session.
    Session must have reached ensemble_review or complete state.
    Returns paths to generated files.
    """
    session = _get_session(session_id)
    if not session.recommended_theories:
        raise HTTPException(
            status_code=409,
            detail="Ensemble not yet generated. Session must reach ensemble_review state.",
        )
    try:
        from forge.assessment_generator import generate_assessment as _gen
        md_path, pdf_path = await asyncio.to_thread(_gen, session)
        session.assessment_path = str(md_path)
        try:
            session.assessment_md = md_path.read_text(encoding="utf-8")
        except Exception:
            pass
        _save_session(session)
        return {
            "session_id":   session_id,
            "md_path":      str(md_path),
            "pdf_path":     str(pdf_path),
            "md_exists":    md_path.exists(),
            "pdf_exists":   pdf_path.exists(),
        }
    except Exception as exc:
        logger.exception("Assessment generation failed for session %s", session_id)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/intake/{session_id}/assessment/download")
async def download_assessment(session_id: str, fmt: str = "pdf"):
    """Download the assessment PDF or MD for a session."""
    from fastapi.responses import FileResponse, Response
    session = _get_session(session_id)
    if not session.assessment_path and not session.assessment_md:
        raise HTTPException(status_code=404, detail="Assessment not yet generated")

    md_path = pathlib.Path(session.assessment_path) if session.assessment_path else None

    # Reconstruct MD from DB if filesystem was wiped (Railway ephemeral)
    if md_path and not md_path.exists() and session.assessment_md:
        try:
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(session.assessment_md, encoding="utf-8")
        except Exception:
            pass

    # If still no file, serve MD content directly from DB
    if not md_path or not md_path.exists():
        if session.assessment_md:
            if fmt == "md":
                name = f"{(session.simspec.name or session_id).replace(' ', '-')}-assessment.md"
                return Response(session.assessment_md, media_type="text/markdown",
                                headers={"Content-Disposition": f'attachment; filename="{name}"'})
            # Regenerate PDF from stored MD
            try:
                import tempfile
                from scripts.md_to_pdf import convert
                with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8") as f:
                    f.write(session.assessment_md)
                    tmp_md = pathlib.Path(f.name)
                pdf_path = await asyncio.to_thread(convert, tmp_md, True)
                name = f"{(session.simspec.name or session_id).replace(' ', '-')}-assessment.pdf"
                return FileResponse(pdf_path, media_type="application/pdf", filename=name)
            except Exception:
                name = f"{(session.simspec.name or session_id).replace(' ', '-')}-assessment.md"
                return Response(session.assessment_md, media_type="text/markdown",
                                headers={"Content-Disposition": f'attachment; filename="{name}"'})
        raise HTTPException(status_code=404, detail="Assessment file not found on server")

    pdf_path = md_path.with_suffix(".pdf")
    if fmt == "md":
        path = md_path
        media_type = "text/markdown"
    else:
        if not pdf_path.exists() and session.assessment_md:
            try:
                from scripts.md_to_pdf import convert
                pdf_path = await asyncio.to_thread(convert, md_path, True)
            except Exception:
                pass
        path = pdf_path if pdf_path.exists() else md_path
        media_type = "application/pdf" if path.suffix == ".pdf" else "text/markdown"

    filename = f"{(session.simspec.name or session_id).replace(' ', '-')}-assessment{path.suffix}"
    return FileResponse(path, media_type=media_type, filename=filename)


# ── Findings document ─────────────────────────────────────────────────────────

@router.post("/intake/{session_id}/findings", status_code=202)
async def generate_findings(session_id: str) -> dict:
    """
    Kick off findings generation as a background task and return immediately.
    Poll GET /intake/{session_id}/findings/status for progress.
    Status is stored in Postgres (session) so any Railway instance can answer polls.
    """
    session = _get_session(session_id)

    if not session.simspec:
        raise HTTPException(status_code=409, detail="SimSpec not built — complete the interview first")
    active = session.active_theories
    if not active:
        raise HTTPException(status_code=409, detail="No theories in ensemble — complete ensemble review first")

    # Mark as running in Postgres so any Railway instance reports the correct status
    session.findings_job_status = "running"
    session.findings_job_error  = None
    _save_session(session)

    # Capture everything needed for the closure now — no re-fetching inside the task
    active_snapshot = list(active)
    simspec_dict_snapshot = session.simspec.model_dump()
    simspec_dict_snapshot["theories"] = [
        {
            "theory_id": t["theory_id"],
            "priority":  int(t.get("suggested_priority") or i),
            "parameters": t.get("parameters") or {},
        }
        for i, t in enumerate(active_snapshot)
    ]

    async def _run_findings():
        """Background task — entire body is wrapped so any crash sets status=error."""
        import traceback as _tb
        try:
            from api.routers.simulations import SimulationRun, _execute_run, _runs

            logger.info("Findings task started for session %s", session_id)

            run = SimulationRun(
                sim_id=str(__import__("uuid").uuid4()),
                session_id=session_id,
                ensemble_type="recommended",
                theory_ids=[t["theory_id"] for t in active_snapshot],
                status="pending",
            )
            _runs[run.sim_id] = run

            await asyncio.wait_for(_execute_run(run, simspec_dict_snapshot), timeout=300.0)

            if run.status != "complete":
                raise RuntimeError(run.error or "Simulation did not complete")

            logger.info("Sim complete for session %s, generating findings doc", session_id)

            from forge.findings_generator import generate_findings as _gen
            md_path, pdf_path = await asyncio.to_thread(_gen, session, run.results)

            session.findings_path       = str(md_path)
            session.findings_job_status = "complete"
            session.findings_job_error  = None
            try:
                session.findings_md = md_path.read_text(encoding="utf-8")
            except Exception:
                pass
            _save_session(session)
            logger.info("Findings complete for session %s: %s", session_id, md_path)

        except Exception as exc:
            err = f"{exc}\n\n{_tb.format_exc()}"
            logger.exception("Findings task FAILED for session %s: %s", session_id, exc)
            try:
                session.findings_job_status = "error"
                session.findings_job_error  = err
                _save_session(session)
            except Exception as save_exc:
                logger.error("Could not save error status for session %s: %s", session_id, save_exc)

    asyncio.create_task(_run_findings())
    return {"session_id": session_id, "status": "running"}


@router.get("/intake/{session_id}/findings/status")
async def findings_status(session_id: str) -> dict:
    """
    Poll findings generation progress.
    Reads from session (Postgres) — works across multiple Railway instances.
    """
    session = _get_session(session_id)
    return {
        "status": session.findings_job_status,
        "error":  session.findings_job_error,
    }



@router.get("/intake/{session_id}/findings/download")
async def download_findings(session_id: str, fmt: str = "pdf"):
    """Download the findings PDF or MD for a session."""
    from fastapi.responses import FileResponse, Response
    session = _get_session(session_id)

    # No findings generated yet
    findings_md_content = getattr(session, "findings_md", None)
    if not getattr(session, "findings_path", None) and not findings_md_content:
        raise HTTPException(status_code=404, detail="Findings not yet generated")

    md_path  = pathlib.Path(session.findings_path) if session.findings_path else None
    pdf_path = md_path.with_suffix(".pdf") if md_path else None

    # If MD file is missing but we have the content stored in Postgres, recreate it
    if md_path and not md_path.exists() and findings_md_content:
        try:
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(findings_md_content, encoding="utf-8")
            logger.info("Restored findings MD from session store: %s", md_path)
        except Exception as exc:
            logger.warning("Could not restore findings MD to disk: %s", exc)

    # PDF: serve from disk (or regenerate from MD)
    if fmt != "md":
        if pdf_path and not pdf_path.exists() and md_path and md_path.exists():
            try:
                from scripts.md_to_pdf import convert
                pdf_path = await asyncio.to_thread(convert, md_path, quiet=True)
            except Exception as exc:
                logger.warning("PDF regeneration failed: %s — falling back to MD", exc)
                pdf_path = None

        if pdf_path and pdf_path.exists():
            stem = (session.simspec.name if session.simspec else None) or session_id
            filename = f"{stem}-findings.pdf".replace(" ", "-")
            return FileResponse(str(pdf_path), media_type="application/pdf", filename=filename)

    # MD fallback: serve from disk or directly from session store
    if md_path and md_path.exists():
        stem = (session.simspec.name if session.simspec else None) or session_id
        filename = f"{stem}-findings.md".replace(" ", "-")
        return FileResponse(str(md_path), media_type="text/markdown", filename=filename)

    if findings_md_content:
        stem = (session.simspec.name if session.simspec else None) or session_id
        filename = f"{stem}-findings.md".replace(" ", "-")
        return Response(
            content=findings_md_content.encode("utf-8"),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    raise HTTPException(status_code=404, detail="Findings file not found — please regenerate")


# ── Gap research endpoint ─────────────────────────────────────────────────────

@router.post("/intake/{session_id}/research-gaps")
async def research_gaps(session_id: str, request: Request):
    """
    Trigger a targeted gap research pass and stream the results via SSE.
    Requires the assessment to have been generated first (session.data_gaps populated).

    SSE event format:
        data: {"type": "chunk",  "text": "..."}
        data: {"type": "done",   "session": {...}}
        data: {"type": "error",  "detail": "..."}
    """
    session = _get_session(session_id)

    async def event_stream():
        try:
            chunk_queue: asyncio.Queue = asyncio.Queue()

            async def _drain():
                try:
                    async for chunk in _agent.run_gap_research(session):
                        await chunk_queue.put(("chunk", chunk))
                    await chunk_queue.put(("done", None))
                except Exception as exc:  # noqa: BLE001
                    await chunk_queue.put(("error", exc))

            drain_task = asyncio.create_task(_drain())

            while True:
                try:
                    kind, value = await asyncio.wait_for(
                        chunk_queue.get(), timeout=15.0
                    )
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue

                if kind == "done":
                    break
                if kind == "error":
                    raise value  # type: ignore[misc]

                chunk: str = value  # type: ignore[assignment]
                payload = json.dumps({"type": "chunk", "text": chunk})
                yield f"data: {payload}\n\n"
                if await request.is_disconnected():
                    logger.info("Client disconnected during gap research for session %s", session_id)
                    drain_task.cancel()
                    return

            _save_session(session)
            done_payload = json.dumps({
                "type":    "done",
                "session": session.to_dict(),
            })
            yield f"data: {done_payload}\n\n"

        except Exception as exc:
            logger.exception("Error in gap research for session %s", session_id)
            error_payload = json.dumps({"type": "error", "detail": str(exc)})
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Theory library / pending queue routes ──────────────────────────────────────

@router.get("/theories/library")
async def list_library() -> dict:
    """List all registered theories (built-in + approved discovered)."""
    from core.theories import list_theories, get_theory
    theories = []
    for tid in list_theories():
        cls = get_theory(tid)
        module = getattr(cls, "__module__", "")
        theories.append({
            "theory_id": tid,
            "domains": getattr(cls, "DOMAINS", []),
            "source": "discovered" if "discovered" in module else "builtin",
        })
    return {"count": len(theories), "theories": theories}


@router.get("/theories/pending")
async def list_pending_theories(status: str | None = None) -> dict:
    """
    List theories queued for review.
    Optional ?status=pending|approved|rejected filter.
    """
    from forge.theory_builder import list_pending
    entries = list_pending(status=status)
    return {"count": len(entries), "pending": entries}


@router.get("/theories/pending/{pending_id}")
async def get_pending_theory(pending_id: str) -> dict:
    """Get the full record for a pending theory including generated code."""
    from forge.theory_builder import load_pending
    pt = load_pending(pending_id)
    if pt is None:
        raise HTTPException(status_code=404, detail=f"Pending theory '{pending_id}' not found")
    return pt.to_dict()


@router.post("/theories/pending/{pending_id}/approve", status_code=200)
async def approve_pending_theory(pending_id: str) -> dict:
    """
    Approve a pending theory:
    Writes code to core/theories/discovered/, hot-loads into registry.
    """
    from forge.theory_builder import approve, load_pending
    pt = load_pending(pending_id)
    if pt is None:
        raise HTTPException(status_code=404, detail=f"Pending theory '{pending_id}' not found")
    if pt.status != "pending":
        raise HTTPException(
            status_code=409, detail=f"Theory '{pending_id}' is already {pt.status}"
        )
    try:
        file_path = approve(pending_id, reviewed_by="consultant")
        return {
            "theory_id": pt.theory_id,
            "status": "approved",
            "file_path": str(file_path),
            "message": f"'{pt.theory_id}' is now active in the theory library.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/theories/pending/{pending_id}/reject", status_code=200)
async def reject_pending_theory(pending_id: str) -> dict:
    """Mark a pending theory as rejected."""
    from forge.theory_builder import reject, load_pending
    pt = load_pending(pending_id)
    if pt is None:
        raise HTTPException(status_code=404, detail=f"Pending theory '{pending_id}' not found")
    if pt.status != "pending":
        raise HTTPException(
            status_code=409, detail=f"Theory '{pending_id}' is already {pt.status}"
        )
    from forge.theory_builder import reject
    reject(pending_id, reviewed_by="consultant")
    return {"theory_id": pt.theory_id, "status": "rejected"}
