"""
forge/session_store.py — Persistent session storage for ForgeSession objects.

Storage backend is selected at startup:
  - DATABASE_URL set → PostgreSQL (survives Railway deploys)
  - DATABASE_URL not set → local file storage under data/sessions/ (dev)

Public API (called from api/routers/forge.py):
    await session_store.init()
    await session_store.save(session)
    await session_store.load_all() -> list[dict]   # raw dicts, forge.py deserializes
    await session_store.delete(session_id)
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import Any

logger = logging.getLogger(__name__)

_SESSION_DIR = pathlib.Path(__file__).parent.parent / "data" / "sessions"
_SESSION_DIR.mkdir(parents=True, exist_ok=True)

# ── Backend selection ─────────────────────────────────────────────────────────

_pool = None          # asyncpg connection pool (None = file mode)
_db_url: str | None = os.environ.get("DATABASE_URL")


async def init() -> None:
    """Initialise the storage backend. Call once at app startup."""
    global _pool
    if not _db_url:
        logger.info("[session_store] No DATABASE_URL — using file storage")
        return

    try:
        import asyncpg
        # Railway provides postgres:// but asyncpg needs postgresql://
        url = _db_url.replace("postgres://", "postgresql://", 1)
        _pool = await asyncpg.create_pool(url, min_size=1, max_size=5)
        async with _pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS forge_sessions (
                    session_id  TEXT PRIMARY KEY,
                    data        JSONB NOT NULL,
                    updated_at  TIMESTAMPTZ DEFAULT NOW()
                )
            """)
        logger.info("[session_store] PostgreSQL backend ready")
    except Exception as exc:
        logger.warning("[session_store] Postgres init failed (%s) — falling back to files", exc)
        _pool = None


async def save(session_dict: dict) -> None:
    """Persist a session (pass session.to_dict())."""
    sid = session_dict["session_id"]
    if _pool:
        try:
            async with _pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO forge_sessions (session_id, data, updated_at)
                    VALUES ($1, $2::jsonb, NOW())
                    ON CONFLICT (session_id)
                    DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
                """, sid, json.dumps(session_dict, default=str))
            return
        except Exception as exc:
            logger.warning("[session_store] Postgres save failed (%s) — writing to file", exc)

    # File fallback
    try:
        path = _SESSION_DIR / f"{sid}.json"
        path.write_text(json.dumps(session_dict, default=str), encoding="utf-8")
    except Exception as exc:
        logger.warning("[session_store] File save failed: %s", exc)


async def load_all() -> list[dict[str, Any]]:
    """Return all persisted sessions as raw dicts."""
    if _pool:
        try:
            async with _pool.acquire() as conn:
                rows = await conn.fetch("SELECT data FROM forge_sessions")
            return [json.loads(r["data"]) for r in rows]
        except Exception as exc:
            logger.warning("[session_store] Postgres load_all failed (%s) — reading files", exc)

    # File fallback
    results = []
    for path in _SESSION_DIR.glob("*.json"):
        try:
            results.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.warning("[session_store] Could not read %s: %s", path.name, exc)
    return results


async def delete(session_id: str) -> None:
    """Delete a session from the store."""
    if _pool:
        try:
            async with _pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM forge_sessions WHERE session_id = $1", session_id
                )
            return
        except Exception as exc:
            logger.warning("[session_store] Postgres delete failed: %s", exc)

    path = _SESSION_DIR / f"{session_id}.json"
    if path.exists():
        path.unlink()
