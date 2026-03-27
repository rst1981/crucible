"""
forge/session.py — ForgeSession conversation state

One ForgeSession per intake conversation. Holds all state needed to drive
the scoping agent: message history, partial SimSpec, research cache, and
gap tracking. Serializable to JSON for API responses and future persistence.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.spec import SimSpec
from forge.researchers.base import ResearchResult


# ── State machine ──────────────────────────────────────────────────────────

class ForgeState(str, Enum):
    INTAKE            = "intake"            # parsing free text, no research yet
    PARALLEL_RESEARCH = "parallel_research" # background research fired, awaiting
    DYNAMIC_INTERVIEW = "dynamic_interview" # asking gap-filling questions
    THEORY_MAPPING    = "theory_mapping"    # TheoryMapper selecting modules
    VALIDATION        = "validation"        # final SimSpec validation pass
    COMPLETE          = "complete"          # SimSpec ready for SimRunner


# ── Message types ──────────────────────────────────────────────────────────

class MessageRole(str, Enum):
    USER      = "user"
    ASSISTANT = "assistant"
    TOOL      = "tool"      # tool result injected into context
    SYSTEM    = "system"    # internal transitions, not shown to user


@dataclass
class ForgeMessage:
    role:        MessageRole
    content:     str
    tool_name:   str | None     = None   # set when role == TOOL
    tool_use_id: str | None     = None   # Claude API tool_use_id for correlation
    timestamp:   float          = field(default_factory=time.time)
    metadata:    dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role":        self.role.value,
            "content":     self.content,
            "tool_name":   self.tool_name,
            "tool_use_id": self.tool_use_id,
            "timestamp":   self.timestamp,
        }


# ── Gap tracking ───────────────────────────────────────────────────────────

@dataclass
class SpecGap:
    """Missing or under-specified part of the SimSpec. Drives question ordering."""
    gap_id:          str   = field(default_factory=lambda: str(uuid.uuid4()))
    field_path:      str   = ""    # e.g. "actors", "initial_environment", "theories"
    description:     str   = ""    # human-readable: what's missing
    priority:        float = 0.5   # 0–1. 1.0 = must ask. 0.0 = nice to have.
    filled:          bool  = False
    filled_by:       str | None = None   # "research" | "user" | "inference"
    question_asked:  str | None = None
    answer_received: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "gap_id":        self.gap_id,
            "field_path":    self.field_path,
            "description":   self.description,
            "priority":      self.priority,
            "filled":        self.filled,
            "filled_by":     self.filled_by,
        }


# ── Research context ───────────────────────────────────────────────────────

@dataclass
class ResearchContext:
    """Aggregated outputs of the parallel research phase."""
    session_id:          str
    results:             list[ResearchResult] = field(default_factory=list)
    theory_candidates:   list[str]            = field(default_factory=list)
    # LLM-extracted parameter hints: env_key → normalized [0,1] estimate
    parameter_estimates: dict[str, float]     = field(default_factory=dict)
    # env keys that research has answered (so we don't ask the user)
    env_keys_calibrated: set[str]             = field(default_factory=set)
    research_complete:   bool                 = False
    # Library gap results: theories auto-added during this session
    library_additions:   list[str]            = field(default_factory=list)
    # Theories found in papers that failed smoke test → in pending queue
    library_gaps:        list[str]            = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "complete":            self.research_complete,
            "result_count":        len(self.results),
            "theory_candidates":   self.theory_candidates,
            "parameter_estimates": self.parameter_estimates,
            "env_keys_calibrated": list(self.env_keys_calibrated),
            "library_additions":   self.library_additions,
            "library_gaps":        self.library_gaps,
        }


# ── ForgeSession ───────────────────────────────────────────────────────────

@dataclass
class ForgeSession:
    session_id:           str              = field(default_factory=lambda: str(uuid.uuid4()))
    simspec:              SimSpec | None   = None
    research_context:     ResearchContext  = field(
        default_factory=lambda: ResearchContext(session_id="")
    )
    conversation_history: list[ForgeMessage] = field(default_factory=list)
    state:                ForgeState        = ForgeState.INTAKE
    gaps:                 list[SpecGap]     = field(default_factory=list)
    turn_count:           int               = 0
    created_at:           float             = field(default_factory=time.time)
    completed_at:         float | None      = None
    intake_text:          str               = ""
    domain:               str               = ""

    def open_gaps(self) -> list[SpecGap]:
        """Return unfilled gaps ordered by priority descending."""
        return sorted(
            [g for g in self.gaps if not g.filled],
            key=lambda g: g.priority,
            reverse=True,
        )

    def mark_complete(self) -> None:
        self.state = ForgeState.COMPLETE
        self.completed_at = time.time()

    def add_message(self, role: MessageRole, content: str, **kwargs: Any) -> ForgeMessage:
        msg = ForgeMessage(role=role, content=content, **kwargs)
        self.conversation_history.append(msg)
        return msg

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id":   self.session_id,
            "state":        self.state.value,
            "domain":       self.domain,
            "turn_count":   self.turn_count,
            "created_at":   self.created_at,
            "completed_at": self.completed_at,
            "intake_text":  self.intake_text,
            "simspec":      self.simspec.model_dump() if self.simspec else None,
            "gaps":         [g.to_dict() for g in self.gaps],
            "messages": [
                m.to_dict() for m in self.conversation_history
                if m.role in (MessageRole.USER, MessageRole.ASSISTANT)
            ],
            "research": self.research_context.to_dict(),
        }
