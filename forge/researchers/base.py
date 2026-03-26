"""
forge/researchers/base.py — Research adapter base classes

ResearchResult is the common output of every adapter. BaseAdapter defines
the interface all adapters must satisfy. Adapters are stateless — each
call to fetch() is independent, results are cached by ForgeSession.

Design notes:
  - All adapters are async (httpx). Use asyncio.gather() for parallel calls.
  - Adapters do NOT write to disk — callers own persistence.
  - source_type matches ResearchSourceSpec.source_type in core/spec.py.
  - calibrates is the env key this result informs (if known at fetch time).
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ResearchResult:
    """
    Uniform output from every research adapter.

    The `data` field is adapter-specific — callers should use source_type
    to know which keys to expect. The Scoping Agent reads `summary` for
    plain-language context and `data` for parameter calibration hints.
    """
    source_type: str                     # "arxiv" | "ssrn" | "fred" | "world_bank" | "news"
    query: str                           # the search term / series ID / URL that produced this
    title: str                           # human-readable title for this result
    summary: str                         # 1-3 sentence plain-language summary
    url: str                             # canonical URL or empty string
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    calibrates: str | None = None        # env key this informs, e.g. "global__trade_volume"
    data: dict[str, Any] = field(default_factory=dict)  # adapter-specific payload
    raw: str = ""                        # raw text / JSON for LLM re-reading if needed
    error: str | None = None            # non-None means partial/failed fetch

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_context_snippet(self) -> str:
        """
        Compact text suitable for inclusion in a Scoping Agent prompt.
        Keeps token cost low while preserving key facts.
        """
        lines = [f"[{self.source_type.upper()}] {self.title}"]
        if self.url:
            lines.append(f"URL: {self.url}")
        lines.append(self.summary)
        if self.calibrates:
            lines.append(f"Informs: {self.calibrates}")
        return "\n".join(lines)


class BaseAdapter(ABC):
    """
    Abstract base for research adapters.

    Each adapter wraps one external data source. Implement fetch() to
    return a list of ResearchResult for a given query string.

    Subclasses should:
      - Define SOURCE_TYPE as a class attribute
      - Accept httpx.AsyncClient as a constructor argument (injected by caller)
      - Handle rate-limit / network errors gracefully — return a result with
        error set rather than raising, so parallel gather() calls don't abort
    """

    SOURCE_TYPE: str = "unknown"

    @abstractmethod
    async def fetch(
        self,
        query: str,
        max_results: int = 5,
        calibrates: str | None = None,
    ) -> list[ResearchResult]:
        """
        Fetch research results for the given query.

        Args:
            query:        Search term, series ID, or topic description.
            max_results:  Maximum number of results to return.
            calibrates:   Hint for which env key these results inform.

        Returns:
            List of ResearchResult. May be empty. Never raises — errors
            are encoded as ResearchResult(error=...).
        """
        ...

    def _error_result(
        self,
        query: str,
        error_msg: str,
        calibrates: str | None = None,
    ) -> ResearchResult:
        """Return a single failed result for error handling in subclasses."""
        logger.warning("%s adapter error for query=%r: %s", self.SOURCE_TYPE, query, error_msg)
        return ResearchResult(
            source_type=self.SOURCE_TYPE,
            query=query,
            title=f"{self.SOURCE_TYPE} fetch failed",
            summary=f"Error: {error_msg}",
            url="",
            calibrates=calibrates,
            error=error_msg,
        )
