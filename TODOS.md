# Crucible — Deferred Items

> Captured from architecture reviews and design deliberations.
> Items here are real, reasoned deferrals — not forgotten work.
> Each entry includes context so someone picking it up in 3 months knows where to start.

---

## P1 — Must resolve before first client deployment

### T-01: Test suite for SimOrchestrator
**What:** Integration tests covering the full single-run and ensemble-run lifecycle through SimOrchestrator — wiring, metric flushing, narrative callbacks, state transitions, error handling.
**Why:** SimOrchestrator is the most critical new component added in the engineering review. It is the only path between the API and the engine. An untested orchestrator means untested simulation runs in production.
**Where to start:** `tests/integration/test_orchestrator.py`. Mock SimRunner (use a fast deterministic stub that runs 10 ticks), real DB (SQLite in-memory), real NarrativeAgent with mocked Anthropic client.
**Depends on:** SimOrchestrator implementation, SimRepository with engine injection pattern.

### T-02: Transaction rollback test on multi-step failure
**What:** Test that if `update_sim_state(COMPLETED)` fails after `save_snapshot` and `save_narrative_entry` have already been called, all three operations roll back atomically.
**Why:** The engineering review removed `commit()` from individual repository methods and moved transaction control to the caller. This is only safe if the `async with engine.begin()` rollback actually works end-to-end. Without a test, a failed completion could leave the DB in a state where the sim has a "complete" narrative entry but is still marked RUNNING.
**Where to start:** `tests/integration/test_repository.py`. Use a mock that raises on the third operation. Verify DB state after exception.
**Depends on:** SimRepository engine injection pattern.

### T-03: ForgeSession serialization roundtrip
**What:** Tests that `ForgeSession.to_dict()` / `ForgeSession.from_dict()` roundtrips correctly for every `ForgeState` enum value, with nested `SimSpec` (all field types), `conversation_history` containing Claude tool-use blocks, and empty/partial sessions.
**Why:** The serialization was a stub (`...`) in the original design and was fully specified in the engineering review. Without tests, the Redis session store will fail silently on the first real Forge session that hits a non-trivial state.
**Where to start:** `tests/unit/test_forge_session.py`. Build one ForgeSession per state, with the full Claude tool-use block structure, round-trip through `to_dict/from_dict`, assert field equality.
**Depends on:** ForgeSession.to_dict/from_dict implementation.

### T-04: RNG threading through SimRunner
**What:** Tests that `SimRunner(spec, rng=random.Random(seed))` produces identical output on two runs with the same seed, and that two `EnsembleRunner` runs with the same `base_seed` produce identical distributions.
**Why:** The engineering review fixed the thread-unsafe `random.seed()` call. Without a reproducibility test, the fix could be silently bypassed if any BDIAgent or theory module slips back to calling the global `random` module.
**Where to start:** `tests/unit/test_reproducibility.py`. Run SimRunner twice with the same rng seed, assert `metric_history` is identical. Run EnsembleRunner twice with `n_runs=10, base_seed=42`, assert distribution means are within floating point tolerance.
**Depends on:** rng parameter threaded through BDIAgent and all theory modules.

---

## P2 — Must resolve before public Portal launch

### T-05: Auth and multi-tenancy integration tests
**What:** Tests covering the full ADMIN / CONSULTANT / CLIENT role hierarchy — that a CLIENT cannot access simulations they were not granted access to, a CONSULTANT cannot access another org's simulations, and role escalation is not possible via API manipulation.
**Why:** ARCHITECTURE-PORTAL.md specifies the auth model (JWT, org → project → simulation hierarchy). The API endpoints are currently stubs with no auth guards. Before Portal goes live, every endpoint needs a role check and a test that the role check works.
**Where to start:** `tests/integration/test_auth.py`. Use three test users (admin, consultant, client). Test each endpoint for all three roles. Verify 403s are returned correctly.
**Depends on:** Auth middleware implementation, ARCHITECTURE-PORTAL.md auth model.

### T-06: EnsembleRunner memory eviction integration test
**What:** Test that calling `ensemble_runner.evict(ensemble_id)` after result retrieval clears `_run_metric_histories` and `_run_final_envs`, that `get_result()` still returns the cached result, and that the 30-minute cleanup task removes stale jobs.
**Why:** The engineering review added the eviction mechanism to prevent unbounded memory growth (~36MB per ensemble job). Without a test, the eviction could be silently skipped or broken in a refactor, and the memory leak would return without any visible signal.
**Where to start:** `tests/unit/test_ensemble_eviction.py`. Create an EnsembleJob with mock data, call evict(), assert history cleared and result intact. Manually trigger cleanup_stale_jobs(), assert job removed.
**Depends on:** EnsembleRunner evict() implementation.

---

## P2 — Architecture work deferred from this session

### T-07: Deployment architecture document
**What:** A `DEPLOYMENT.md` specifying the Railway (backend) + Vercel (frontend) deployment pattern for Crucible, analogous to the Hormuz pattern. Covers: environment variable management, DB migration strategy (Alembic), Redis provisioning, APScheduler behavior in Railway's container environment, Vercel preview deployments for Portal.
**Why:** The Hormuz sim established the deployment pattern but several Crucible-specific concerns are unresolved: SQLite → Postgres migration path, Redis TTL behavior across Railway restarts, how the DataFeedAgent scheduler survives container restarts.
**Where to start:** Reference `d:/dev/hormuz-sim-dashboard` deployment configuration. Hormuz operational notes in CONTEXT.md. Key constraint: never use `vercel deploy` CLI — git push only.
**Depends on:** Nothing blocking. Can be written independently.

### T-08: Security threat model
**What:** A formal threat model for the API layer: injection vectors (prompt injection into ScopingAgent, SQL injection via API params), data classification (client scenario contents are confidential), secrets management, rate limiting for Claude API calls, and audit logging for calibration approvals.
**Why:** ARCHITECTURE-API.md has `allow_origins=settings.CORS_ORIGINS` (fixed) and `changed_by` fields on version records, but no formal security review. For a platform handling sensitive geopolitical scenario analysis for enterprise clients, a threat model is a standard requirement before deployment.
**Where to start:** OWASP API Security Top 10. Focus on: the ScopingAgent (user input goes directly into LLM context — prompt injection surface), the CalibrationProposal approval endpoint (authorization check: only the simulation's owning consultant should approve), the report download endpoint (ensure clients cannot download other clients' reports by ID manipulation).
**Depends on:** Auth model implementation (T-05).

### T-09: Alembic migration strategy
**What:** Initialize Alembic for database schema migrations. Define the migration baseline from `api/db/schema.py`. Document the migration workflow for the team.
**Why:** ARCHITECTURE-API.md uses `metadata.create_all()` for dev (table creation). In production, schema changes need migrations. Without Alembic, the first production schema change requires manual SQL or a destructive recreate.
**Where to start:** `alembic init alembic`. Point `env.py` at `api.db.schema.metadata`. Create initial migration from current schema. Document in DEPLOYMENT.md.
**Depends on:** T-07 (deployment doc).

---

## P3 — Future vision items

### T-10: Hormuz scenario port as reference implementation #1
**What:** Port the existing Hormuz simulation (`d:/dev/hormuz-sim-dashboard`) into the Crucible framework as `scenarios/hormuz/`. This validates that Crucible's generalization preserves the behavior of the system it was built from.
**Why:** Hormuz has 18 BDI agents, Richardson escalation, Wittman-Zartman termination branches, and a live deployment. Porting it proves the engine is general enough to reproduce a working sim without modification.
**Where to start:** `scenarios/hormuz/spec.py` — define the Hormuz SimSpec (18 actors, Richardson + Wittman-Zartman theories, Strait of Hormuz environment variables). Compare outputs to the live Hormuz sim at `hormuz-sim.vercel.app`.
**Depends on:** Core engine complete (Weeks 1-2), Theory library complete (Week 2).

### T-11: "Crucible" trademark check
**What:** Verify "Crucible" is available as a trademark for a B2B SaaS platform in the simulation/analytics category.
**Why:** This was flagged as an open question in CONTEXT.md and never resolved. Should be checked before any external client-facing materials use the name.
**Where to start:** USPTO TESS database search. Check for existing registrations in Nice Classification 42 (software as a service).
**Depends on:** Nothing technical.

### T-12: Custom Claude Code skills for scenario development
**What:** Three gstack-style skills stubbed in CONTEXT.md — `/research-theory`, `/research-data`, `/scaffold-sim` — that use Claude Code to assist with scenario development. Currently documented as planned but not implemented.
**Why:** These would accelerate the consultant workflow: `/research-theory` fires an arXiv/SSRN search and returns a theory brief + suggested SimSpec updates; `/research-data` queries FRED/World Bank and returns parameter estimates; `/scaffold-sim` takes a SimSpec and generates the full scenario directory scaffold.
**Where to start:** `.claude/skills/` directory. Follow the gstack skill markdown pattern. `/scaffold-sim` is highest value — a consultant with a finished SimSpec should be able to generate the scenario directory structure in one command.
**Depends on:** Core engine and Forge layer complete.

### T-13: SSRN researcher implementation
**What:** The ScopingAgent's research pipeline includes an `SsrnResearcher` in the list of tools, but SSRN does not have a public API. The implementation will need to use their search endpoint with careful rate limiting, or find an alternative social science preprint source.
**Why:** SSRN is the primary repository for economics, finance, and political science working papers — highly relevant to the scenarios Crucible targets. Leaving it unimplemented reduces the research quality of the scoping agent for economic and policy scenarios.
**Where to start:** Test SSRN's public search endpoint (`https://papers.ssrn.com/sol3/results.cfm`). Alternatively, consider REPEC (Research Papers in Economics) which has a documented API. Document the decision.
**Depends on:** Forge layer research pipeline implementation (Week 5).

---

## Resolved / Not pursuing

| Item | Decision | Reason |
|------|----------|--------|
| ProcessPoolExecutor for ensemble | Not pursuing | Pickling complexity, startup overhead. ThreadPoolExecutor with GIL is sufficient for CPU-bound Python sim. |
| Celery distributed queue | Not pursuing | Overkill for consulting firm scale. EnsembleRunner in-process is sufficient. |
| ORM (SQLAlchemy ORM) | Not pursuing | metric_records is high-volume append-only. ORM overhead not justified. SQLAlchemy Core only. |
| Automatic recalibration | Not pursuing | Human-in-the-loop is a product requirement. Automatic updates would produce confident wrong answers without consultant judgment. |
| Per-method DB commits | Resolved | Removed in engineering review. Caller controls transactions via `async with engine.begin()`. |
