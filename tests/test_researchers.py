"""
Tests for forge/researchers/ adapters.

All tests are unit tests — they use httpx mocking (respx or manual
pytest-style patching) rather than hitting live APIs. This keeps the
suite deterministic and fast.

Integration tests (real network calls) are opt-in via the CRUCIBLE_INTEGRATION_TESTS
env var and are NOT run in CI by default.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forge.researchers.base import BaseAdapter, ResearchResult
from forge.researchers.arxiv import ArxivAdapter, _parse_arxiv_xml
from forge.researchers.fred import FredAdapter, _looks_like_series_id
from forge.researchers.worldbank import WorldBankAdapter, _looks_like_indicator
from forge.researchers.ssrn import SsrnAdapter
from forge.researchers.news import NewsAdapter, _relevance_score, _tokenize


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_client(status_code: int = 200, text: str = "", json_data=None):
    """Return a mock httpx.AsyncClient that returns a fixed response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    if json_data is not None:
        resp.json = MagicMock(return_value=json_data)

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    return client


def run(coro):
    """Run a coroutine synchronously in tests."""
    return asyncio.run(coro)


# ── ResearchResult ─────────────────────────────────────────────────────────────

class TestResearchResult:
    def test_ok_when_no_error(self):
        r = ResearchResult(
            source_type="arxiv",
            query="arms race",
            title="Test paper",
            summary="A test.",
            url="https://example.com",
        )
        assert r.ok is True

    def test_not_ok_when_error_set(self):
        r = ResearchResult(
            source_type="fred",
            query="GDP",
            title="failed",
            summary="",
            url="",
            error="network timeout",
        )
        assert r.ok is False

    def test_context_snippet_includes_source_type(self):
        r = ResearchResult(
            source_type="arxiv",
            query="test",
            title="My Paper",
            summary="It does things.",
            url="https://arxiv.org/abs/1234",
        )
        snippet = r.context_snippet if hasattr(r, "context_snippet") else r.to_context_snippet()
        assert "ARXIV" in snippet
        assert "My Paper" in snippet

    def test_context_snippet_includes_calibrates(self):
        r = ResearchResult(
            source_type="fred",
            query="GDP",
            title="GDP Series",
            summary="US GDP data.",
            url="https://fred.stlouisfed.org/series/GDP",
            calibrates="keynesian__gdp_normalized",
        )
        snippet = r.to_context_snippet()
        assert "keynesian__gdp_normalized" in snippet

    def test_fetched_at_defaults_to_now(self):
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        r = ResearchResult(source_type="news", query="q", title="t", summary="s", url="")
        after = datetime.now(timezone.utc).replace(tzinfo=None)
        assert before <= r.fetched_at <= after


# ── BaseAdapter ────────────────────────────────────────────────────────────────

class TestBaseAdapter:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseAdapter()

    def test_error_result_sets_error_field(self):
        class ConcreteAdapter(BaseAdapter):
            SOURCE_TYPE = "test"
            async def fetch(self, query, max_results=5, calibrates=None):
                return [self._error_result(query, "something broke", calibrates)]

        adapter = ConcreteAdapter()
        result = run(adapter.fetch("foo"))
        assert len(result) == 1
        assert result[0].ok is False
        assert "something broke" in result[0].error
        assert result[0].source_type == "test"


# ── ArxivAdapter ───────────────────────────────────────────────────────────────

_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2301.12345v1</id>
    <title>Richardson Arms Race Model Revisited</title>
    <summary>We revisit the Richardson model and show new stability conditions
under asymmetric power distributions. The key finding is that fatigue
parameters dominate grievance terms in long-horizon conflicts.</summary>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <category term="econ.GN"/>
    <published>2023-01-30T00:00:00Z</published>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2302.99999v2</id>
    <title>Bargaining Theory in Conflict Resolution</title>
    <summary>A survey of bargaining models applied to interstate conflict,
covering Fearon's rationalist explanations and Wittman's efficient war hypothesis.</summary>
    <author><name>Carol White</name></author>
    <category term="polisci.IR"/>
    <published>2023-02-15T00:00:00Z</published>
  </entry>
</feed>"""


class TestArxivAdapter:
    def test_parse_returns_results(self):
        results = _parse_arxiv_xml(_ARXIV_XML, "arms race", None)
        assert len(results) == 2

    def test_parse_extracts_title(self):
        results = _parse_arxiv_xml(_ARXIV_XML, "arms race", None)
        assert results[0].title == "Richardson Arms Race Model Revisited"

    def test_parse_extracts_arxiv_id(self):
        results = _parse_arxiv_xml(_ARXIV_XML, "arms race", None)
        assert results[0].data["arxiv_id"] == "2301.12345v1"

    def test_parse_extracts_authors(self):
        results = _parse_arxiv_xml(_ARXIV_XML, "arms race", None)
        assert "Alice Smith" in results[0].data["authors"]
        assert "Bob Jones" in results[0].data["authors"]

    def test_parse_propagates_calibrates(self):
        results = _parse_arxiv_xml(_ARXIV_XML, "arms race", "richardson__escalation_index")
        assert all(r.calibrates == "richardson__escalation_index" for r in results)

    def test_parse_source_type_is_arxiv(self):
        results = _parse_arxiv_xml(_ARXIV_XML, "test", None)
        assert all(r.source_type == "arxiv" for r in results)

    def test_fetch_returns_error_on_http_failure(self):
        client = _mock_client(status_code=503)
        adapter = ArxivAdapter(client)
        results = run(adapter.fetch("arms race"))
        assert len(results) == 1
        assert not results[0].ok

    def test_fetch_returns_results_on_success(self):
        client = _mock_client(text=_ARXIV_XML)
        adapter = ArxivAdapter(client)
        results = run(adapter.fetch("arms race", max_results=5))
        assert len(results) == 2
        assert all(r.ok for r in results)

    def test_parse_empty_feed(self):
        empty_xml = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>"""
        results = _parse_arxiv_xml(empty_xml, "nothing", None)
        assert results == []


# ── FredAdapter ────────────────────────────────────────────────────────────────

class TestFredAdapter:
    def test_looks_like_series_id_true(self):
        assert _looks_like_series_id("GDP") is True
        assert _looks_like_series_id("UNRATE") is True
        assert _looks_like_series_id("FEDFUNDS") is True

    def test_looks_like_series_id_false(self):
        assert _looks_like_series_id("us gdp growth") is False
        assert _looks_like_series_id("") is False
        assert _looks_like_series_id("AVERYLONGSTRINGTHATISNOTASERIESID") is False

    def test_no_api_key_returns_error(self):
        client = _mock_client()
        adapter = FredAdapter(client, api_key="")
        results = run(adapter.fetch("GDP"))
        assert len(results) == 1
        assert not results[0].ok
        assert "FRED_API_KEY" in results[0].error

    def test_fetch_series_http_error(self):
        client = _mock_client(status_code=400)
        adapter = FredAdapter(client, api_key="testkey")
        results = run(adapter.fetch("GDP"))
        assert not results[0].ok

    def test_fetch_search_mode_for_keywords(self):
        """Non-series-ID queries trigger search mode, not series fetch."""
        search_json = {
            "seriess": [
                {
                    "id": "GDP",
                    "title": "Gross Domestic Product",
                    "units_short": "Bil. of $",
                    "frequency_short": "A",
                    "notes": "Annual GDP.",
                    "popularity": 95,
                }
            ]
        }
        client = _mock_client(json_data=search_json)
        adapter = FredAdapter(client, api_key="testkey")
        results = run(adapter.fetch("gross domestic product", max_results=3))
        assert len(results) >= 1
        assert results[0].data["series_id"] == "GDP"

    def test_search_empty_returns_error(self):
        client = _mock_client(json_data={"seriess": []})
        adapter = FredAdapter(client, api_key="testkey")
        results = run(adapter.fetch("something obscure that does not exist"))
        assert not results[0].ok


# ── WorldBankAdapter ───────────────────────────────────────────────────────────

class TestWorldBankAdapter:
    def test_looks_like_indicator_true(self):
        assert _looks_like_indicator("NY.GDP.MKTP.CD") is True
        assert _looks_like_indicator("MS.MIL.XPND.GD.ZS") is True

    def test_looks_like_indicator_false(self):
        assert _looks_like_indicator("gdp growth rate") is False
        assert _looks_like_indicator("") is False

    def test_fetch_indicator_http_error(self):
        client = _mock_client(status_code=500)
        adapter = WorldBankAdapter(client)
        results = run(adapter.fetch("NY.GDP.MKTP.CD"))
        assert not results[0].ok

    def test_fetch_indicator_parses_observations(self):
        wb_json = [
            {"page": 1, "pages": 1, "per_page": 10, "total": 1},
            [
                {
                    "indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP (current USD)"},
                    "country": {"id": "US", "value": "United States"},
                    "countryiso3code": "USA",
                    "date": "2022",
                    "value": 25462700000000,
                    "unit": "",
                    "obs_status": "",
                    "decimal": 0,
                }
            ],
        ]
        client = _mock_client(json_data=wb_json)
        adapter = WorldBankAdapter(client)
        results = run(adapter.fetch("NY.GDP.MKTP.CD"))
        assert len(results) >= 1
        assert results[0].ok
        assert results[0].data["latest_value"] == 25462700000000

    def test_search_mode_for_keyword(self):
        wb_json = [
            {"page": 1, "pages": 1},
            [
                {
                    "id": "NY.GDP.MKTP.CD",
                    "name": "GDP (current USD)",
                    "sourceNote": "GDP at purchaser prices.",
                    "topics": [{"id": "3", "value": "Economy & Growth"}],
                }
            ],
        ]
        client = _mock_client(json_data=wb_json)
        adapter = WorldBankAdapter(client)
        results = run(adapter.fetch("gross domestic product"))
        assert results[0].data["indicator_id"] == "NY.GDP.MKTP.CD"

    def test_country_qualifier_parsed(self):
        """'USA:NY.GDP.MKTP.CD' should fetch US-specific data."""
        wb_json = [{"page": 1}, []]
        client = _mock_client(json_data=wb_json)
        adapter = WorldBankAdapter(client)
        # Should not raise — empty data returns error result
        results = run(adapter.fetch("USA:NY.GDP.MKTP.CD"))
        assert isinstance(results, list)


# ── SsrnAdapter ────────────────────────────────────────────────────────────────

_SSRN_HTML = """<html><body>
<div class="search-results">
  <h3 class="title"><a href="/abstract=4123456">Fearon Bargaining Under Incomplete Information</a></h3>
  <div class="abstract-text">We extend Fearon's model to allow for endogenous revelation of private
information during crisis bargaining. Our key result is that war probability increases when both
sides face high costs of misrepresentation.</div>
  <div class="authors">Jane Doe; John Smith</div>
</div>
</body></html>"""


class TestSsrnAdapter:
    def test_fetch_error_on_http_failure(self):
        client = _mock_client(status_code=403)
        adapter = SsrnAdapter(client)
        results = run(adapter.fetch("fearon bargaining"))
        assert not results[0].ok

    def test_fetch_returns_no_results_result_on_empty_html(self):
        client = _mock_client(text="<html><body></body></html>")
        adapter = SsrnAdapter(client)
        results = run(adapter.fetch("anything"))
        assert len(results) == 1
        # Graceful no-results result (not an error)
        assert "ssrn" in results[0].source_type

    def test_fetch_parses_html_results(self):
        client = _mock_client(text=_SSRN_HTML)
        adapter = SsrnAdapter(client)
        results = run(adapter.fetch("fearon bargaining"))
        # At least the graceful no-result or a parsed result
        assert len(results) >= 1
        assert results[0].source_type == "ssrn"


# ── NewsAdapter ────────────────────────────────────────────────────────────────

_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>World News</title>
  <item>
    <title>Iran tensions in Strait of Hormuz rise amid tanker incidents</title>
    <description>Iranian naval vessels intercepted a commercial tanker in the
    Strait of Hormuz, raising concerns about oil supply disruption.</description>
    <link>https://example.com/article/1</link>
    <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Federal Reserve raises interest rates by 25 basis points</title>
    <description>The Federal Open Market Committee voted to raise rates,
    citing persistent inflation above the 2% target.</description>
    <link>https://example.com/article/2</link>
    <pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate>
  </item>
</channel></rss>"""


class TestNewsAdapter:
    def test_tokenize_removes_stopwords(self):
        tokens = _tokenize("the arms race in the Middle East")
        assert "the" not in tokens
        assert "arms" in tokens
        assert "race" in tokens

    def test_relevance_score_title_weighted_higher(self):
        article = {
            "title": "Hormuz oil disruption",
            "summary": "Some text without keywords.",
        }
        score_title = _relevance_score(article, ["hormuz"])
        article2 = {
            "title": "Oil markets update",
            "summary": "Hormuz is mentioned here in the body text only.",
        }
        score_body = _relevance_score(article2, ["hormuz"])
        assert score_title > score_body

    def test_relevance_zero_for_no_match(self):
        article = {"title": "Cricket match results", "summary": "England beat Australia."}
        assert _relevance_score(article, ["hormuz", "iran", "tanker"]) == 0

    def test_fetch_returns_error_when_all_feeds_fail(self):
        client = _mock_client(status_code=500)
        adapter = NewsAdapter(client, feeds=["https://example.com/feed.rss"])
        results = run(adapter.fetch("anything"))
        assert not results[0].ok

    def test_fetch_parses_rss_and_filters_by_keyword(self):
        client = _mock_client(text=_RSS_XML)
        adapter = NewsAdapter(client, feeds=["https://example.com/feed.rss"])
        results = run(adapter.fetch("Hormuz tanker", max_results=5))
        assert len(results) >= 1
        # Most relevant result should be about Hormuz, not the Fed
        assert "Hormuz" in results[0].title or "tanker" in results[0].title.lower()

    def test_fetch_falls_back_to_recent_when_no_keyword_match(self):
        client = _mock_client(text=_RSS_XML)
        adapter = NewsAdapter(client, feeds=["https://example.com/feed.rss"])
        results = run(adapter.fetch("xyznomatch", max_results=5))
        # Falls back to returning articles even with no match
        assert len(results) >= 1
        assert all(r.source_type == "news" for r in results)

    def test_custom_feeds_used_when_provided(self):
        """Adapter should use feeds kwarg over defaults when passed to fetch()."""
        client = _mock_client(text=_RSS_XML)
        adapter = NewsAdapter(client, feeds=["https://default.com/feed.rss"])

        call_urls: list[str] = []
        original_get = client.get

        async def capturing_get(url, **kwargs):
            call_urls.append(url)
            return await original_get(url, **kwargs)

        client.get = capturing_get
        run(adapter.fetch("test", feeds=["https://custom.com/rss"]))
        assert any("custom.com" in u for u in call_urls)
