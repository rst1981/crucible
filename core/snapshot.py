"""
core/snapshot.py — Named snapshot persistence for simulation state.

SimRunner already takes in-memory snapshots (SimSnapshot dataclass). This module
adds disk persistence: save snapshots to JSON, load them back, and schedule
periodic auto-saves via APScheduler.

Usage:
    from core.snapshot import SnapshotStore

    store = SnapshotStore("scenarios/hormuz/snapshots/")
    store.save(runner.snapshots[-1])               # save one snapshot
    store.save_all(runner.snapshots)               # save all at end of run

    snap = store.load("threshold_fearon__conflict_probability")
    store.list()                                   # → [{"label": ..., "tick": ..., "path": ...}]

APScheduler integration (optional):
    scheduler = store.start_auto_save(runner, interval_minutes=60)
    # ...
    scheduler.shutdown()
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.sim_runner import SimRunner, SimSnapshot

logger = logging.getLogger(__name__)


# ── SnapshotStore ─────────────────────────────────────────────────────────────

class SnapshotStore:
    """
    Persists SimSnapshot objects as JSON files in a directory.

    File naming: ``{tick:04d}_{slug}.json`` where slug is the snapshot label
    with non-alphanumeric characters replaced by underscores.

    Index file: ``index.json`` in the same directory — a summary list for fast
    listing without loading every snapshot file.
    """

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    # ── Save ──────────────────────────────────────────────────────────────────

    def save(self, snapshot: "SimSnapshot") -> Path:
        """
        Persist a single SimSnapshot to disk.

        Returns the path of the written file.
        """
        slug = re.sub(r"[^\w]+", "_", snapshot.label).strip("_")
        filename = f"{snapshot.tick:04d}_{slug}.json"
        path = self.directory / filename

        data = {
            "tick":          snapshot.tick,
            "label":         snapshot.label,
            "timestamp":     snapshot.timestamp,
            "env":           snapshot.env,
            "agent_states":  snapshot.agent_states,
            "theory_states": snapshot.theory_states,
        }
        path.write_text(json.dumps(data, indent=2))
        self._update_index(snapshot, path)
        logger.debug("Snapshot saved: %s", path)
        return path

    def save_all(self, snapshots: "list[SimSnapshot]") -> list[Path]:
        """Save a list of snapshots. Returns list of written paths."""
        return [self.save(s) for s in snapshots]

    # ── Load ──────────────────────────────────────────────────────────────────

    def load(self, label: str) -> dict[str, Any] | None:
        """
        Load a snapshot by label.

        Returns the raw dict (env, agent_states, theory_states) or None if not found.
        """
        index = self._read_index()
        entry = next((e for e in index if e["label"] == label), None)
        if entry is None:
            logger.warning("Snapshot '%s' not found in index", label)
            return None
        path = Path(entry["path"])
        if not path.exists():
            logger.warning("Snapshot file missing: %s", path)
            return None
        return json.loads(path.read_text())

    def load_at_tick(self, tick: int) -> list[dict[str, Any]]:
        """Return all snapshots at a given tick."""
        index = self._read_index()
        results = []
        for entry in index:
            if entry["tick"] == tick:
                data = self.load(entry["label"])
                if data:
                    results.append(data)
        return results

    # ── List ──────────────────────────────────────────────────────────────────

    def list(self) -> list[dict[str, Any]]:
        """
        Return a summary list of all saved snapshots.

        Each entry: {"label": str, "tick": int, "timestamp": float, "path": str}
        """
        return self._read_index()

    def latest(self) -> dict[str, Any] | None:
        """Return the most recent snapshot (by tick), or None if empty."""
        index = self._read_index()
        if not index:
            return None
        latest_entry = max(index, key=lambda e: (e["tick"], e.get("timestamp", 0)))
        return self.load(latest_entry["label"])

    # ── APScheduler integration ───────────────────────────────────────────────

    def start_auto_save(
        self,
        runner: "SimRunner",
        interval_minutes: float = 60.0,
    ) -> Any:
        """
        Schedule periodic auto-saves of the runner's latest snapshot.

        Requires APScheduler (already in requirements.txt). The scheduler
        runs in a background thread — call scheduler.shutdown() when done.

        Args:
            runner:           The SimRunner to pull snapshots from.
            interval_minutes: How often to auto-save (default 60 min).

        Returns:
            The BackgroundScheduler instance (caller owns shutdown).
        """
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
        except ImportError as exc:
            raise ImportError(
                "APScheduler is required for auto-save. "
                "Install it with: pip install apscheduler"
            ) from exc

        def _auto_save_job() -> None:
            if runner.snapshots:
                path = self.save(runner.snapshots[-1])
                logger.info("Auto-save: %s", path)
            else:
                logger.debug("Auto-save: no snapshots yet")

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            _auto_save_job,
            trigger="interval",
            minutes=interval_minutes,
            id="snapshot_auto_save",
        )
        scheduler.start()
        logger.info(
            "Snapshot auto-save started (every %.0f min → %s)",
            interval_minutes, self.directory,
        )
        return scheduler

    # ── Index helpers ─────────────────────────────────────────────────────────

    def _index_path(self) -> Path:
        return self.directory / "index.json"

    def _read_index(self) -> list[dict[str, Any]]:
        path = self._index_path()
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def _update_index(self, snapshot: "SimSnapshot", file_path: Path) -> None:
        index = self._read_index()
        entry = {
            "label":     snapshot.label,
            "tick":      snapshot.tick,
            "timestamp": snapshot.timestamp,
            "path":      str(file_path),
        }
        # Replace existing entry with same label or append
        index = [e for e in index if e["label"] != snapshot.label]
        index.append(entry)
        index.sort(key=lambda e: (e["tick"], e.get("timestamp", 0)))
        self._index_path().write_text(json.dumps(index, indent=2))
