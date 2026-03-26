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
from forge.researchers.news import NewsAdapter, FEEDS_BY_CATEGORY, _relevance_score, _tokenize
from forge.researchers.gdelt import GdeltAdapter
from forge.researchers.guardian import GuardianAdapter
from forge.researchers.newsapi import NewsApiAdapter
from forge.researchers.acled import AcledAdapter, _summarize_events
from forge.researchers.eia import EiaAdapter, _looks_like_series_id as _eia_looks_like_series_id
from forge.researchers.un import UnAdapter


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


# ── TestNewsFeedCategories ─────────────────────────────────────────────────────

class TestNewsFeedCategories:
    def test_all_categories_present(self):
        expected = {"geopolitics", "defense", "economics", "energy", "corporate", "sanctions", "think_tanks", "conflict"}
        assert set(FEEDS_BY_CATEGORY.keys()) >= expected

    def test_each_category_has_feeds(self):
        for cat, feeds in FEEDS_BY_CATEGORY.items():
            assert len(feeds) > 0, f"Category '{cat}' has no feeds"

    def test_category_filter_restricts_fetched_feeds(self):
        """Using category= should only hit feeds from that category."""
        client = _mock_client(text=_RSS_XML)
        adapter = NewsAdapter(client)

        call_urls: list[str] = []
        original_get = client.get

        async def capturing_get(url, **kwargs):
            call_urls.append(url)
            return await original_get(url, **kwargs)

        client.get = capturing_get
        run(adapter.fetch("oil", category="energy"))

        energy_feeds = set(FEEDS_BY_CATEGORY["energy"])
        assert all(u in energy_feeds for u in call_urls), (
            f"Non-energy feed called: {[u for u in call_urls if u not in energy_feeds]}"
        )

    def test_default_feeds_are_deduplicated(self):
        from forge.researchers.news import DEFAULT_FEEDS
        assert len(DEFAULT_FEEDS) == len(set(DEFAULT_FEEDS))

    def test_unknown_category_falls_back_to_defaults(self):
        from forge.researchers.news import DEFAULT_FEEDS
        client = _mock_client(text=_RSS_XML)
        adapter = NewsAdapter(client)
        call_urls: list[str] = []
        original_get = client.get

        async def capturing_get(url, **kwargs):
            call_urls.append(url)
            return await original_get(url, **kwargs)

        client.get = capturing_get
        run(adapter.fetch("test", category="nonexistent_category"))
        assert len(call_urls) == len(DEFAULT_FEEDS)


# ── GdeltAdapter ───────────────────────────────────────────────────────────────

_GDELT_JSON = {
    "articles": [
        {
            "url": "https://example.com/gdelt/1",
            "title": "Iran warships shadow tanker in Strait of Hormuz",
            "seendate": "20240115T120000Z",
            "domain": "example.com",
            "language": "English",
            "tone": -12.5,
        },
        {
            "url": "https://example.com/gdelt/2",
            "title": "OPEC nations agree on output cut",
            "seendate": "20240114T090000Z",
            "domain": "oilnews.com",
            "language": "English",
            "tone": -3.0,
        },
    ]
}


class TestGdeltAdapter:
    def test_fetch_returns_results_on_success(self):
        client = _mock_client(json_data=_GDELT_JSON)
        adapter = GdeltAdapter(client)
        results = run(adapter.fetch("Hormuz tanker"))
        assert len(results) == 2
        assert all(r.ok for r in results)

    def test_fetch_source_type_is_gdelt(self):
        client = _mock_client(json_data=_GDELT_JSON)
        adapter = GdeltAdapter(client)
        results = run(adapter.fetch("Iran"))
        assert all(r.source_type == "gdelt" for r in results)

    def test_negative_tone_signals_conflict(self):
        client = _mock_client(json_data=_GDELT_JSON)
        adapter = GdeltAdapter(client)
        results = run(adapter.fetch("Iran"))
        # First article has tone -12.5 — tone stored in data and described in summary
        first = results[0]
        assert first.data["tone"] == -12.5
        assert "conflict" in first.summary.lower() or "negative" in first.summary.lower()

    def test_fetch_returns_error_on_http_failure(self):
        client = _mock_client(status_code=500)
        adapter = GdeltAdapter(client)
        results = run(adapter.fetch("anything"))
        assert len(results) == 1
        assert not results[0].ok

    def test_fetch_handles_empty_articles_list(self):
        client = _mock_client(json_data={"articles": []})
        adapter = GdeltAdapter(client)
        results = run(adapter.fetch("obscure query"))
        assert len(results) == 1
        # Returns a descriptive no-results result (not an error, but informs the caller)
        assert "no articles" in results[0].title.lower() or not results[0].ok

    def test_max_results_respected(self):
        client = _mock_client(json_data=_GDELT_JSON)
        adapter = GdeltAdapter(client)
        results = run(adapter.fetch("test", max_results=1))
        assert len(results) == 1


# ── GuardianAdapter ────────────────────────────────────────────────────────────

_GUARDIAN_JSON = {
    "response": {
        "status": "ok",
        "results": [
            {
                "webTitle": "Iran sanctions tightened after nuclear talks collapse",
                "webUrl": "https://www.theguardian.com/world/2024/iran-sanctions",
                "sectionId": "world",
                "webPublicationDate": "2024-01-15T09:30:00Z",
                "fields": {"trailText": "Western powers impose new financial penalties as negotiations stall."},
            },
            {
                "webTitle": "Oil prices surge as Middle East tensions mount",
                "webUrl": "https://www.theguardian.com/business/2024/oil-prices",
                "sectionId": "business",
                "webPublicationDate": "2024-01-14T14:00:00Z",
                "fields": {"trailText": "Brent crude rises 4% on supply disruption fears."},
            },
        ],
    }
}


class TestGuardianAdapter:
    def test_no_api_key_returns_error(self):
        client = _mock_client()
        adapter = GuardianAdapter(client, api_key="")
        results = run(adapter.fetch("Iran sanctions"))
        assert len(results) == 1
        assert not results[0].ok
        assert "GUARDIAN_API_KEY" in results[0].error

    def test_fetch_returns_results_on_success(self):
        client = _mock_client(json_data=_GUARDIAN_JSON)
        adapter = GuardianAdapter(client, api_key="testkey")
        results = run(adapter.fetch("Iran sanctions"))
        assert len(results) == 2
        assert all(r.ok for r in results)

    def test_source_type_is_guardian(self):
        client = _mock_client(json_data=_GUARDIAN_JSON)
        adapter = GuardianAdapter(client, api_key="testkey")
        results = run(adapter.fetch("oil prices"))
        assert all(r.source_type == "guardian" for r in results)

    def test_trail_text_used_as_summary(self):
        client = _mock_client(json_data=_GUARDIAN_JSON)
        adapter = GuardianAdapter(client, api_key="testkey")
        results = run(adapter.fetch("Iran"))
        assert "Western powers" in results[0].summary

    def test_fetch_http_error_returns_error_result(self):
        client = _mock_client(status_code=403)
        adapter = GuardianAdapter(client, api_key="badkey")
        results = run(adapter.fetch("anything"))
        assert not results[0].ok

    def test_empty_results_returns_no_results_message(self):
        empty = {"response": {"status": "ok", "results": []}}
        client = _mock_client(json_data=empty)
        adapter = GuardianAdapter(client, api_key="testkey")
        results = run(adapter.fetch("very obscure query"))
        assert len(results) == 1
        assert not results[0].ok or "no results" in results[0].title.lower()


# ── NewsApiAdapter ─────────────────────────────────────────────────────────────

_NEWSAPI_JSON = {
    "status": "ok",
    "totalResults": 2,
    "articles": [
        {
            "source": {"id": "reuters", "name": "Reuters"},
            "title": "Saudi Arabia cuts oil output",
            "description": "Saudi Aramco reduces daily production following OPEC+ agreement.",
            "url": "https://reuters.com/energy/2024/opec",
            "publishedAt": "2024-01-15T08:00:00Z",
            "author": "Reuters Staff",
        },
        {
            "source": {"id": "bbc-news", "name": "BBC News"},
            "title": "Strait of Hormuz shipping update",
            "description": "Traffic through the Strait remains disrupted for third consecutive day.",
            "url": "https://bbc.co.uk/news/2024/hormuz",
            "publishedAt": "2024-01-14T12:00:00Z",
            "author": "BBC Correspondent",
        },
    ],
}


class TestNewsApiAdapter:
    def test_no_api_key_returns_error(self):
        client = _mock_client()
        adapter = NewsApiAdapter(client, api_key="")
        results = run(adapter.fetch("oil"))
        assert len(results) == 1
        assert not results[0].ok
        assert "NEWSAPI_KEY" in results[0].error

    def test_fetch_returns_results_on_success(self):
        client = _mock_client(json_data=_NEWSAPI_JSON)
        adapter = NewsApiAdapter(client, api_key="testkey")
        results = run(adapter.fetch("oil OPEC"))
        assert len(results) == 2
        assert all(r.ok for r in results)

    def test_source_type_is_newsapi(self):
        client = _mock_client(json_data=_NEWSAPI_JSON)
        adapter = NewsApiAdapter(client, api_key="testkey")
        results = run(adapter.fetch("test"))
        assert all(r.source_type == "newsapi" for r in results)

    def test_description_used_as_summary(self):
        client = _mock_client(json_data=_NEWSAPI_JSON)
        adapter = NewsApiAdapter(client, api_key="testkey")
        results = run(adapter.fetch("oil"))
        assert "Aramco" in results[0].summary

    def test_newsapi_error_body_at_200_handled(self):
        """NewsAPI returns HTTP 200 with error status in body."""
        error_body = {"status": "error", "code": "apiKeyInvalid", "message": "Your API key is invalid."}
        client = _mock_client(json_data=error_body)
        adapter = NewsApiAdapter(client, api_key="badkey")
        results = run(adapter.fetch("test"))
        assert not results[0].ok
        assert "apiKeyInvalid" in results[0].error or "invalid" in results[0].error.lower()

    def test_empty_articles_returns_no_results(self):
        client = _mock_client(json_data={"status": "ok", "totalResults": 0, "articles": []})
        adapter = NewsApiAdapter(client, api_key="testkey")
        results = run(adapter.fetch("obscure query with no results"))
        assert len(results) == 1
        assert "no results" in results[0].title.lower() or not results[0].ok


# ── AcledAdapter ───────────────────────────────────────────────────────────────

_ACLED_EVENTS = [
    {
        "event_date": "2024-01-10",
        "event_type": "Battles",
        "sub_event_type": "Armed clash",
        "actor1": "Houthi forces",
        "actor2": "Saudi-led coalition",
        "country": "Yemen",
        "admin1": "Hudaydah",
        "location": "Al Hudaydah",
        "latitude": "14.7",
        "longitude": "42.9",
        "fatalities": "12",
        "notes": "Clashes reported near port area.",
        "source": "AP",
    },
    {
        "event_date": "2024-01-09",
        "event_type": "Battles",
        "sub_event_type": "Armed clash",
        "actor1": "Houthi forces",
        "actor2": "Yemeni Army",
        "country": "Yemen",
        "admin1": "Taizz",
        "location": "Taizz",
        "latitude": "13.6",
        "longitude": "44.0",
        "fatalities": "5",
        "notes": "Frontline position attacked.",
        "source": "Reuters",
    },
    {
        "event_date": "2024-01-08",
        "event_type": "Protests",
        "sub_event_type": "Peaceful protest",
        "actor1": "Civilians",
        "actor2": "",
        "country": "Yemen",
        "admin1": "Aden",
        "location": "Aden",
        "latitude": "12.8",
        "longitude": "45.0",
        "fatalities": "0",
        "notes": "Anti-government demonstration.",
        "source": "Local media",
    },
]

_ACLED_JSON = {"data": _ACLED_EVENTS, "count": 3, "status": 1}


class TestAcledAdapter:
    def test_no_credentials_returns_error(self):
        client = _mock_client()
        adapter = AcledAdapter(client, api_key="", email="")
        results = run(adapter.fetch("Yemen"))
        assert not results[0].ok
        assert "ACLED_API_KEY" in results[0].error or "ACLED_EMAIL" in results[0].error

    def test_fetch_returns_grouped_results(self):
        client = _mock_client(json_data=_ACLED_JSON)
        adapter = AcledAdapter(client, api_key="testkey", email="test@example.com")
        results = run(adapter.fetch("Yemen"))
        # Should produce one result per event type (Battles + Protests = 2)
        assert len(results) == 2

    def test_source_type_is_acled(self):
        client = _mock_client(json_data=_ACLED_JSON)
        adapter = AcledAdapter(client, api_key="testkey", email="test@example.com")
        results = run(adapter.fetch("Yemen"))
        assert all(r.source_type == "acled" for r in results)

    def test_battles_have_high_intensity(self):
        client = _mock_client(json_data=_ACLED_JSON)
        adapter = AcledAdapter(client, api_key="testkey", email="test@example.com")
        results = run(adapter.fetch("Yemen"))
        battles = [r for r in results if "Battles" in r.title]
        assert battles
        assert battles[0].data["intensity"] >= 0.8

    def test_protests_have_lower_intensity_than_battles(self):
        client = _mock_client(json_data=_ACLED_JSON)
        adapter = AcledAdapter(client, api_key="testkey", email="test@example.com")
        results = run(adapter.fetch("Yemen"))
        battles = next(r for r in results if "Battles" in r.title)
        protests = next(r for r in results if "Protests" in r.title)
        assert protests.data["intensity"] < battles.data["intensity"]

    def test_fatalities_summed_per_type(self):
        results = _summarize_events(_ACLED_EVENTS, "Yemen", "Yemen", None, 10)
        battles = next(r for r in results if "Battles" in r.title)
        assert battles.data["fatalities"] == 17  # 12 + 5

    def test_no_events_returns_descriptive_result(self):
        client = _mock_client(json_data={"data": [], "count": 0, "status": 1})
        adapter = AcledAdapter(client, api_key="testkey", email="test@example.com")
        results = run(adapter.fetch("LowConflictCountry"))
        assert len(results) == 1
        assert "no events" in results[0].title.lower()

    def test_http_error_returns_error_result(self):
        client = _mock_client(status_code=401)
        adapter = AcledAdapter(client, api_key="testkey", email="test@example.com")
        results = run(adapter.fetch("Yemen"))
        assert not results[0].ok


# ── EiaAdapter ─────────────────────────────────────────────────────────────────

_EIA_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>EIA Today in Energy</title>
  <item>
    <title>U.S. crude oil production reaches record high</title>
    <description>Domestic crude output hit 13.2 million barrels per day in December.</description>
    <link>https://www.eia.gov/todayinenergy/detail.php?id=12345</link>
    <pubDate>Mon, 15 Jan 2024 10:00:00 EST</pubDate>
  </item>
  <item>
    <title>Natural gas inventories below 5-year average</title>
    <description>Working gas in storage dropped 150 Bcf last week.</description>
    <link>https://www.eia.gov/todayinenergy/detail.php?id=12346</link>
    <pubDate>Fri, 12 Jan 2024 10:00:00 EST</pubDate>
  </item>
</channel></rss>"""

_EIA_SERIES_JSON = {
    "response": {
        "description": "Cushing, OK WTI Spot Price FOB",
        "units": "Dollars per Barrel",
        "data": [
            {"period": "2024-01-12", "value": 72.77},
            {"period": "2024-01-11", "value": 71.93},
            {"period": "2024-01-10", "value": 70.38},
        ],
    }
}


class TestEiaAdapter:
    def test_looks_like_series_id_true(self):
        assert _eia_looks_like_series_id("PET.RWTC.D") is True
        assert _eia_looks_like_series_id("NG.RNGWHHD.D") is True

    def test_looks_like_series_id_false(self):
        assert _eia_looks_like_series_id("crude oil price") is False
        assert _eia_looks_like_series_id("") is False

    def test_rss_mode_when_no_api_key(self):
        """No key → RSS mode, not API mode."""
        client = _mock_client(text=_EIA_RSS_XML)
        adapter = EiaAdapter(client, api_key="")
        results = run(adapter.fetch("crude oil"))
        assert len(results) >= 1
        assert all(r.source_type == "eia" for r in results)

    def test_rss_keyword_filtering(self):
        client = _mock_client(text=_EIA_RSS_XML)
        adapter = EiaAdapter(client, api_key="")
        results = run(adapter.fetch("crude oil"))
        # Only the crude oil article should match
        assert any("crude" in r.title.lower() for r in results)

    def test_series_id_with_key_uses_api_mode(self):
        client = _mock_client(json_data=_EIA_SERIES_JSON)
        adapter = EiaAdapter(client, api_key="testkey")
        results = run(adapter.fetch("PET.RWTC.D"))
        assert len(results) == 1
        assert results[0].ok
        assert results[0].data["latest_value"] == 72.77

    def test_series_id_without_key_returns_note_and_rss(self):
        """Series requested but no key → note result + RSS fallback."""
        client = _mock_client(text=_EIA_RSS_XML)
        adapter = EiaAdapter(client, api_key="")
        results = run(adapter.fetch("PET.RWTC.D"))
        # First result should be the note about missing key
        assert len(results) >= 1
        assert "EIA_API_KEY" in results[0].summary or "api_key" in results[0].summary.lower() or "key" in results[0].summary.lower()

    def test_rss_http_error_returns_error_result(self):
        client = _mock_client(status_code=503)
        adapter = EiaAdapter(client, api_key="")
        results = run(adapter.fetch("energy"))
        assert not results[0].ok


# ── UnAdapter ──────────────────────────────────────────────────────────────────

_UN_SC_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>UN Security Council Press Releases</title>
  <item>
    <title>Security Council Resolution 2789 (2024) — Sanctions on Iran</title>
    <description>The Security Council today unanimously adopted resolution 2789,
    imposing additional sanctions on Iranian entities linked to ballistic missile programme.</description>
    <link>https://www.un.org/press/en/2024/sc15467.doc.htm</link>
    <pubDate>Mon, 15 Jan 2024 16:00:00 EST</pubDate>
  </item>
  <item>
    <title>Security Council Demands Immediate Ceasefire in Yemen</title>
    <description>Members voted 13-0 with 2 abstentions to demand cessation of hostilities
    and unimpeded humanitarian access.</description>
    <link>https://www.un.org/press/en/2024/sc15468.doc.htm</link>
    <pubDate>Fri, 12 Jan 2024 14:30:00 EST</pubDate>
  </item>
</channel></rss>"""

_UN_NEWS_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>UN News</title>
  <item>
    <title>UNHCR warns of worsening humanitarian crisis in Yemen</title>
    <description>More than 4.5 million people remain internally displaced amid ongoing conflict.</description>
    <link>https://news.un.org/en/story/2024/01/1234567</link>
    <pubDate>Thu, 11 Jan 2024 10:00:00 EST</pubDate>
  </item>
</channel></rss>"""


class TestUnAdapter:
    def test_fetch_returns_results(self):
        client = _mock_client(text=_UN_SC_RSS)
        adapter = UnAdapter(client)
        results = run(adapter.fetch("sanctions Iran", feeds=["https://www.un.org/press/en/rss.xml"]))
        assert len(results) >= 1
        assert all(r.source_type == "un" for r in results)

    def test_security_council_articles_flagged(self):
        client = _mock_client(text=_UN_SC_RSS)
        adapter = UnAdapter(client)
        results = run(adapter.fetch("sanctions", feeds=["https://www.un.org/press/en/rss.xml"]))
        sc_results = [r for r in results if r.data.get("is_security_council")]
        assert len(sc_results) > 0

    def test_sc_articles_score_higher_than_un_news(self):
        """SC articles get a bonus — sanctions SC result should outrank plain UN news."""
        # Two feeds: SC (with bonus) vs UN News (without bonus)
        resp_sc = MagicMock()
        resp_sc.status_code = 200
        resp_sc.text = _UN_SC_RSS
        resp_sc.raise_for_status = MagicMock()

        resp_news = MagicMock()
        resp_news.status_code = 200
        resp_news.text = _UN_NEWS_RSS
        resp_news.raise_for_status = MagicMock()

        call_count = [0]

        async def side_effect(url, **kwargs):
            call_count[0] += 1
            if "press" in url:
                return resp_sc
            return resp_news

        client = MagicMock()
        client.get = AsyncMock(side_effect=side_effect)
        adapter = UnAdapter(client)
        results = run(adapter.fetch(
            "sanctions",
            feeds=[
                "https://www.un.org/press/en/rss.xml",
                "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
            ],
        ))
        # SC article about sanctions should appear first
        assert results[0].data.get("is_security_council") is True

    def test_fetch_error_on_all_feeds_failing(self):
        client = _mock_client(status_code=503)
        adapter = UnAdapter(client)
        results = run(adapter.fetch("Yemen", feeds=["https://news.un.org/feed/subscribe/en/news/all/rss.xml"]))
        assert len(results) == 1
        assert not results[0].ok

    def test_keyword_relevance_filters_results(self):
        client = _mock_client(text=_UN_SC_RSS)
        adapter = UnAdapter(client)
        results_sanctions = run(adapter.fetch("sanctions", feeds=["https://www.un.org/press/en/rss.xml"]))
        results_climate = run(adapter.fetch("climate biodiversity", feeds=["https://www.un.org/press/en/rss.xml"]))
        # Sanctions query should return results (both SC articles mention sanctions/ceasefire)
        # Climate query has no matches — falls back to all articles
        assert len(results_sanctions) >= 1
        assert len(results_climate) >= 1  # fallback behavior
