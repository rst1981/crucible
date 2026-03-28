"""
tests/test_assessment_generator.py

Unit tests for forge/assessment_generator.py.
All LLM calls and file I/O are mocked — no live API calls, no disk writes.
"""
from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock, patch, mock_open

import pytest

from core.spec import SimSpec, ActorSpec, TimeframeSpec, TheoryRef
from forge.session import ForgeSession, ResearchContext, ForgeState
from forge.researchers.base import ResearchResult


# ── Fixtures ────────────────────────────────────────────────────────────────

def _make_simspec(
    name="Test Scenario",
    domain="market",
    actors=None,
    env=None,
) -> SimSpec:
    if actors is None:
        actors = [
            ActorSpec(actor_id="actor_a", name="Actor A", metadata={"role": "state"}),
            ActorSpec(actor_id="actor_b", name="Actor B", metadata={"role": "market"}),
        ]
    return SimSpec(
        name=name,
        description="A test scenario",
        domain=domain,
        actors=actors,
        timeframe=TimeframeSpec(total_ticks=12, tick_unit="month", start_date="2025-01-01"),
        initial_environment=env if env is not None else {"global__stress": 0.6, "global__competition": 0.4},
        metadata={"outcome_focus": "Identify platforms with highest churn risk"},
    )


def _make_session(simspec=None) -> ForgeSession:
    session = ForgeSession()
    session.simspec = simspec or _make_simspec()
    session.state = ForgeState.ENSEMBLE_REVIEW
    session.recommended_theories = [
        {
            "theory_id": "cournot_oligopoly",
            "display_name": "Cournot Oligopoly",
            "score": 0.85,
            "rationale": "Models quantity competition between firms",
            "application_note": "Captures competitive dynamics between streaming platforms",
            "source": "builtin",
            "domains": ["market"],
            "suggested_priority": 0,
            "parameters": {},
        },
        {
            "theory_id": "porter_five_forces",
            "display_name": "Porter Five Forces",
            "score": 0.72,
            "rationale": "Structural competitive analysis",
            "application_note": "Maps the five forces for streaming industry",
            "source": "builtin",
            "domains": ["market", "corporate"],
            "suggested_priority": 1,
            "parameters": {},
        },
    ]
    ctx = ResearchContext(session_id=session.session_id)
    ctx.theory_candidates = ["cournot_oligopoly", "porter_five_forces"]
    ctx.parameter_estimates = {"global__competition": 0.7, "global__churn": 0.4}
    ctx.research_complete = True
    rr = ResearchResult(
        source_type="arxiv",
        query="streaming platform competition",
        title="Streaming Platform Competition",
        url="https://arxiv.org/abs/1234",
        summary="A study of streaming competition",
        raw={},
    )
    ctx.results = [rr]
    session.research_context = ctx
    return session


# ── Slugify ──────────────────────────────────────────────────────────────────

class TestSlugify:
    def test_basic(self):
        from forge.assessment_generator import _slugify
        assert _slugify("Hello World") == "hello-world"

    def test_special_chars_stripped(self):
        from forge.assessment_generator import _slugify
        result = _slugify("Walla Walla: Wine & Simulation!")
        assert ":" not in result
        assert "&" not in result

    def test_long_name_truncated(self):
        from forge.assessment_generator import _slugify
        result = _slugify("a" * 100)
        assert len(result) <= 60

    def test_spaces_become_dashes(self):
        from forge.assessment_generator import _slugify
        assert _slugify("foo bar baz") == "foo-bar-baz"

    def test_multiple_spaces_single_dash(self):
        from forge.assessment_generator import _slugify
        assert _slugify("foo   bar") == "foo-bar"


# ── Table builders ────────────────────────────────────────────────────────────

class TestActorsTable:
    def test_returns_table_with_actors(self):
        from forge.assessment_generator import _actors_table
        spec = _make_simspec()
        result = _actors_table(spec)
        assert "Actor A" in result
        assert "Actor B" in result
        assert "| Actor |" in result

    def test_no_actors_returns_placeholder(self):
        from forge.assessment_generator import _actors_table
        spec = _make_simspec(actors=[])
        result = _actors_table(spec)
        assert "No actors" in result

    def test_none_spec_returns_placeholder(self):
        from forge.assessment_generator import _actors_table
        result = _actors_table(None)
        assert "No actors" in result

    def test_belief_state_shown(self):
        from forge.assessment_generator import _actors_table
        actor = ActorSpec(
            actor_id="a", name="A",
            metadata={"role": "state", "belief_state": {"resolve": 0.7}}
        )
        spec = _make_simspec(actors=[actor])
        result = _actors_table(spec)
        assert "resolve" in result


class TestEnvTable:
    def test_returns_table(self):
        from forge.assessment_generator import _env_table
        spec = _make_simspec()
        result = _env_table(spec)
        assert "| Parameter |" in result
        assert "stress" in result  # global__ prefix stripped

    def test_empty_env_returns_placeholder(self):
        from forge.assessment_generator import _env_table
        spec = _make_simspec(env={})
        result = _env_table(spec)
        assert "No initial conditions" in result

    def test_strips_global_prefix(self):
        from forge.assessment_generator import _env_table
        spec = _make_simspec(env={"global__foo": 0.5})
        result = _env_table(spec)
        assert "global__foo" not in result
        assert "foo" in result


class TestTheoriesTable:
    def test_renders_theories(self):
        from forge.assessment_generator import _theories_table
        recs = [
            {"display_name": "Cournot", "score": 0.85, "rationale": "qty comp",
             "application_note": "applies here", "source": "builtin", "theory_id": "cournot"},
        ]
        result = _theories_table(recs)
        assert "Cournot" in result
        assert "0.85" in result
        assert "applies here" in result

    def test_new_badge_for_discovered(self):
        from forge.assessment_generator import _theories_table
        recs = [
            {"display_name": "New Theory", "score": 0.6, "rationale": "r",
             "application_note": "a", "source": "discovered", "theory_id": "new_t"},
        ]
        result = _theories_table(recs)
        assert "*(new)*" in result

    def test_empty_returns_placeholder(self):
        from forge.assessment_generator import _theories_table
        result = _theories_table([])
        assert "No theories" in result

    def test_long_note_truncated(self):
        from forge.assessment_generator import _theories_table
        recs = [
            {"display_name": "T", "score": 0.5, "rationale": "r",
             "application_note": "x" * 200, "source": "builtin", "theory_id": "t"},
        ]
        result = _theories_table(recs)
        assert "…" in result


class TestCalibrationTable:
    def test_renders_estimates(self):
        from forge.assessment_generator import _calibration_table
        ctx = MagicMock()
        ctx.parameter_estimates = {"global__competition": 0.7}
        result = _calibration_table(ctx)
        assert "competition" in result
        assert "0.700" in result

    def test_empty_estimates_returns_placeholder(self):
        from forge.assessment_generator import _calibration_table
        ctx = MagicMock()
        ctx.parameter_estimates = {}
        result = _calibration_table(ctx)
        assert "No calibration data" in result

    def test_none_ctx_returns_placeholder(self):
        from forge.assessment_generator import _calibration_table
        result = _calibration_table(None)
        assert "No calibration data" in result


class TestSourcesSection:
    def test_renders_titles(self):
        from forge.assessment_generator import _sources_section
        ctx = MagicMock()
        rr = MagicMock()
        rr.title = "My Paper"
        rr.url = "https://example.com"
        ctx.results = [rr]
        result = _sources_section(ctx)
        assert "My Paper" in result

    def test_empty_results_returns_placeholder(self):
        from forge.assessment_generator import _sources_section
        ctx = MagicMock()
        ctx.results = []
        result = _sources_section(ctx)
        assert "No sources" in result


# ── Prose generation ─────────────────────────────────────────────────────────

class TestGenerateProse:
    def test_returns_tuple_of_strings(self):
        from forge.assessment_generator import _generate_prose
        session = _make_session()

        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(
            text=json.dumps({
                "exec_summary": "This is the executive summary.",
                "data_gaps": "- Gap 1\n- Gap 2",
            })
        )]

        with patch("forge.assessment_generator.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_resp
            exec_s, gaps = _generate_prose(session)

        assert "executive summary" in exec_s
        assert "Gap 1" in gaps

    def test_fallback_on_api_failure(self):
        from forge.assessment_generator import _generate_prose
        session = _make_session()

        with patch("forge.assessment_generator.Anthropic") as MockClient:
            MockClient.return_value.messages.create.side_effect = Exception("API down")
            exec_s, gaps = _generate_prose(session)

        assert isinstance(exec_s, str)
        assert isinstance(gaps, str)
        assert len(exec_s) > 0

    def test_handles_json_in_fences(self):
        from forge.assessment_generator import _generate_prose
        session = _make_session()

        fenced = "```json\n" + json.dumps({
            "exec_summary": "Summary text.",
            "data_gaps": "- A gap",
        }) + "\n```"

        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=fenced)]

        with patch("forge.assessment_generator.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_resp
            exec_s, gaps = _generate_prose(session)

        assert "Summary text" in exec_s


# ── Chart generation ──────────────────────────────────────────────────────────

class TestGenerateCharts:
    def test_returns_list(self, tmp_path):
        from forge.assessment_generator import _generate_charts
        session = _make_session()

        with patch("forge.assessment_generator._apply_rcparams") as mock_plt:
            fig_mock = MagicMock()
            ax_mock = MagicMock()
            bar_mock = MagicMock()
            bar_mock.get_y.return_value = 0.0
            bar_mock.get_height.return_value = 0.4
            ax_mock.barh.return_value = [bar_mock, bar_mock]
            ax_mock.pie.return_value = ([], [], [])
            fig_mock.add_subplot.return_value = ax_mock
            mock_plt.return_value.subplots.return_value = (fig_mock, ax_mock)
            mock_plt.return_value.close = MagicMock()

            result = _generate_charts(session, tmp_path)

        assert isinstance(result, list)

    def test_no_crash_on_empty_env(self, tmp_path):
        from forge.assessment_generator import _generate_charts
        session = _make_session()
        object.__setattr__(session.simspec, "initial_environment", {})

        with patch("forge.assessment_generator._apply_rcparams") as mock_plt:
            mock_plt.return_value.subplots.return_value = (MagicMock(), MagicMock())
            mock_plt.return_value.close = MagicMock()
            result = _generate_charts(session, tmp_path)

        assert isinstance(result, list)

    def test_no_crash_on_exception(self, tmp_path):
        from forge.assessment_generator import _generate_charts
        session = _make_session()

        with patch("forge.assessment_generator._apply_rcparams", side_effect=ImportError("no matplotlib")):
            result = _generate_charts(session, tmp_path)

        assert result == []


# ── Markdown builder ──────────────────────────────────────────────────────────

class TestBuildMarkdown:
    def test_contains_scenario_name(self):
        from forge.assessment_generator import _build_markdown
        session = _make_session()
        md = _build_markdown(session, "test-scenario", [])
        assert "Test Scenario" in md

    def test_contains_all_sections(self):
        from forge.assessment_generator import _build_markdown
        session = _make_session()
        md = _build_markdown(session, "test-scenario", [])
        for section in ["Executive Summary", "## Scenario", "Recommended Theory Stack",
                         "Calibration Anchors", "Data Gaps & Monte Carlo Guidance"]:
            assert section in md, f"Missing section: {section}"

    def test_contains_outcome_focus(self):
        from forge.assessment_generator import _build_markdown
        session = _make_session()
        md = _build_markdown(session, "test-scenario", [])
        assert "churn risk" in md

    def test_embeds_chart_paths(self, tmp_path):
        from forge.assessment_generator import _build_markdown
        session = _make_session()
        chart = tmp_path / "fig1_theory_scores.png"
        chart.write_bytes(b"fake")
        md = _build_markdown(session, "test-scenario", [chart])
        assert "fig1_theory_scores.png" in md

    def test_custom_note_when_custom_set(self):
        from forge.assessment_generator import _build_markdown
        session = _make_session()
        session.custom_theories = [{"theory_id": "x", "display_name": "X", "score": 0.5}]
        md = _build_markdown(session, "test-scenario", [])
        assert "Custom ensemble" in md

    def test_monte_carlo_guidance_by_domain(self):
        from forge.assessment_generator import _build_markdown
        session = _make_session(_make_simspec(domain="geopolitics"))
        md = _build_markdown(session, "test-scenario", [])
        assert "escalation_prob" in md


# ── Full generate_assessment (integration-level, mocked I/O) ─────────────────

class TestGenerateAssessment:
    def test_calls_pdf_convert(self, tmp_path):
        from forge.assessment_generator import generate_assessment
        session = _make_session()

        prose_resp = MagicMock()
        prose_resp.content = [MagicMock(text=json.dumps({
            "exec_summary": "Summary.",
            "data_gaps": "- Gap",
        }))]

        with patch("forge.assessment_generator._RESEARCH_DIR", tmp_path), \
             patch("forge.assessment_generator.Anthropic") as MockClient, \
             patch("forge.assessment_generator._generate_charts", return_value=[]), \
             patch("scripts.md_to_pdf.convert") as mock_convert:

            MockClient.return_value.messages.create.return_value = prose_resp
            mock_convert.return_value = tmp_path / "out.pdf"

            md_path, pdf_path = generate_assessment(session)

        assert md_path.suffix == ".md"
        assert md_path.exists()

    def test_pdf_failure_does_not_raise(self, tmp_path):
        from forge.assessment_generator import generate_assessment
        session = _make_session()

        prose_resp = MagicMock()
        prose_resp.content = [MagicMock(text=json.dumps({
            "exec_summary": "Summary.",
            "data_gaps": "- Gap",
        }))]

        with patch("forge.assessment_generator._RESEARCH_DIR", tmp_path), \
             patch("forge.assessment_generator.Anthropic") as MockClient, \
             patch("forge.assessment_generator._generate_charts", return_value=[]), \
             patch("scripts.md_to_pdf.convert", side_effect=RuntimeError("pandoc missing")):

            MockClient.return_value.messages.create.return_value = prose_resp
            md_path, pdf_path = generate_assessment(session)

        # Should not raise, md should still exist
        assert md_path.exists()

    def test_slug_derived_from_name(self, tmp_path):
        from forge.assessment_generator import generate_assessment
        session = _make_session(_make_simspec(name="My Custom Scenario"))

        prose_resp = MagicMock()
        prose_resp.content = [MagicMock(text=json.dumps({
            "exec_summary": "S.", "data_gaps": "- G",
        }))]

        with patch("forge.assessment_generator._RESEARCH_DIR", tmp_path), \
             patch("forge.assessment_generator.Anthropic") as MockClient, \
             patch("forge.assessment_generator._generate_charts", return_value=[]), \
             patch("scripts.md_to_pdf.convert") as mock_convert:

            MockClient.return_value.messages.create.return_value = prose_resp
            mock_convert.return_value = tmp_path / "out.pdf"
            md_path, _ = generate_assessment(session)

        assert "my-custom-scenario" in md_path.name


# ── Session field: assessment_path ───────────────────────────────────────────

class TestSessionAssessmentPath:
    def test_default_is_none(self):
        session = ForgeSession()
        assert session.assessment_path is None

    def test_can_be_set(self):
        session = ForgeSession()
        session.assessment_path = "/some/path/assessment.md"
        assert session.assessment_path == "/some/path/assessment.md"

    def test_included_in_to_dict(self):
        session = ForgeSession()
        session.assessment_path = "/path/to/doc.md"
        d = session.to_dict()
        assert d["assessment_path"] == "/path/to/doc.md"

    def test_null_included_in_to_dict(self):
        session = ForgeSession()
        d = session.to_dict()
        assert "assessment_path" in d
        assert d["assessment_path"] is None


# ── Session field: deep_dive_complete ────────────────────────────────────────

class TestSessionDeepDive:
    def test_default_is_false(self):
        session = ForgeSession()
        assert session.deep_dive_complete is False

    def test_can_be_set(self):
        session = ForgeSession()
        session.deep_dive_complete = True
        assert session.deep_dive_complete is True
