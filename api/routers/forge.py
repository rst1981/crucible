"""
api/routers/forge.py — Intake / Scoping Agent routes

POST /forge/intake                          Create a new scoping session
GET  /forge/intake/{session_id}             Poll session state + SimSpec progress
POST /forge/intake/{session_id}/message     Send user message, stream agent response (SSE)
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


# ── Session store (in-memory for Week 4; Week 5 moves to Redis) ────────────

_sessions: dict[str, ForgeSession] = {}

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

            full_reply = ""
            async for chunk in _agent.turn_stream(session, user_message=user_msg):
                full_reply += chunk
                payload = json.dumps({"type": "chunk", "text": chunk})
                yield f"data: {payload}\n\n"
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info("Client disconnected during session %s", session_id)
                    return

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


@router.delete("/intake/{session_id}", status_code=204)
async def delete_session(session_id: str):
    """Delete a scoping session."""
    _get_session(session_id)  # 404 if not found
    del _sessions[session_id]


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
