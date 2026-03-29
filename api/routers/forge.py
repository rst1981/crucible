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


# ── Session store with disk persistence ────────────────────────────────────

import pathlib, json as _json

_SESSION_DIR = pathlib.Path(__file__).parent.parent.parent / "data" / "sessions"
_SESSION_DIR.mkdir(parents=True, exist_ok=True)

_sessions: dict[str, ForgeSession] = {}


def _session_path(session_id: str) -> pathlib.Path:
    return _SESSION_DIR / f"{session_id}.json"


def _save_session(session: ForgeSession) -> None:
    try:
        _session_path(session.session_id).write_text(
            _json.dumps(session.to_dict(), default=str), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning("Session save failed: %s", exc)


def _load_sessions() -> None:
    """Load all saved sessions from disk on startup."""
    from forge.session import ForgeState, ResearchContext, SpecGap
    from core.spec import SimSpec
    for path in _SESSION_DIR.glob("*.json"):
        try:
            data = _json.loads(path.read_text(encoding="utf-8"))
            session = ForgeSession(intake_text=data.get("intake_text", ""))
            session.session_id          = data["session_id"]
            session.state               = ForgeState(data.get("state", "complete"))
            session.domain              = data.get("domain", "")
            session.turn_count          = data.get("turn_count", 0)
            session.created_at          = data.get("created_at", 0.0)
            session.completed_at        = data.get("completed_at")
            session.recommended_theories = data.get("recommended_theories", [])
            session.discovered_theories  = data.get("discovered_theories", [])
            session.custom_theories      = data.get("custom_theories")
            session.assessment_path      = data.get("assessment_path")
            session.data_gaps            = data.get("data_gaps", [])
            session.proprietary_gaps     = data.get("proprietary_gaps", [])
            session.gap_research_running  = False  # never resume mid-run
            session.gap_research_complete = data.get("gap_research_complete", False)
            session.closed_gaps          = data.get("closed_gaps", [])
            session.remaining_gaps       = data.get("remaining_gaps", [])
            if data.get("simspec"):
                session.simspec = SimSpec.model_validate(data["simspec"])
            # Restore research context minimally (results not needed post-session)
            ctx = session.research_context
            research = data.get("research", {})
            ctx.parameter_estimates = research.get("parameter_estimates", {})
            ctx.library_additions   = research.get("library_additions", [])
            _sessions[session.session_id] = session
            logger.info("Restored session %s (%s)", session.session_id, session.state)
        except Exception as exc:
            logger.warning("Failed to restore session %s: %s", path.name, exc)


# Load persisted sessions on startup
_load_sessions()


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
    path = _session_path(session_id)
    if path.exists():
        path.unlink()
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
