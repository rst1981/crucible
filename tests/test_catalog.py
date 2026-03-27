"""
Tests for api/catalog.py — TheoryCatalogEntry introspection and build_catalog().
"""
from __future__ import annotations

import pytest

from api.catalog import (
    DOMAIN_MAP,
    TheoryCatalogEntry,
    build_catalog,
    get_entry,
    invalidate_cache,
    _extract_description,
    _extract_reference,
    _extract_parameters,
    _class_to_name,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fresh_catalog() -> list[TheoryCatalogEntry]:
    invalidate_cache()
    return build_catalog()


# ── _extract_description ───────────────────────────────────────────────────────

class TestExtractDescription:
    def test_returns_first_paragraph(self):
        doc = "First paragraph line one.\nFirst paragraph line two.\n\nSecond paragraph."
        result = _extract_description(doc)
        assert "First paragraph" in result
        assert "Second paragraph" not in result

    def test_empty_docstring(self):
        assert _extract_description(None) == ""
        assert _extract_description("") == ""

    def test_single_line(self):
        result = _extract_description("Just one line.")
        assert result == "Just one line."


# ── _extract_reference ─────────────────────────────────────────────────────────

class TestExtractReference:
    def test_extracts_reference_line(self):
        doc = "Description.\n\nReference: Richardson, L.F. (1960). Arms and Insecurity."
        result = _extract_reference(doc)
        assert "Richardson" in result
        assert result.startswith("Richardson")

    def test_case_insensitive(self):
        doc = "REFERENCE: Some Author (2000). Some Book."
        result = _extract_reference(doc)
        assert "Some Author" in result

    def test_no_reference_returns_empty(self):
        doc = "Just a description with no reference."
        assert _extract_reference(doc) == ""

    def test_none_returns_empty(self):
        assert _extract_reference(None) == ""


# ── _class_to_name ─────────────────────────────────────────────────────────────

class TestClassToName:
    def test_camel_case_split(self):
        from pydantic import BaseModel
        from core.theories.base import TheoryBase

        class RichardsonArmsRace(TheoryBase):
            pass

        result = _class_to_name(RichardsonArmsRace)
        assert result == "Richardson Arms Race"

    def test_single_word(self):
        from core.theories.base import TheoryBase

        class Simple(TheoryBase):
            pass

        assert _class_to_name(Simple) == "Simple"


# ── build_catalog ──────────────────────────────────────────────────────────────

class TestBuildCatalog:
    def test_returns_list_of_entries(self):
        catalog = _fresh_catalog()
        assert isinstance(catalog, list)
        assert len(catalog) > 0

    def test_all_entries_are_catalog_entries(self):
        for entry in _fresh_catalog():
            assert isinstance(entry, TheoryCatalogEntry)

    def test_richardson_in_catalog(self):
        ids = [e.theory_id for e in _fresh_catalog()]
        assert "richardson_arms_race" in ids

    def test_entries_have_required_fields(self):
        for entry in _fresh_catalog():
            assert entry.theory_id
            assert entry.name
            assert isinstance(entry.domains, list)
            assert isinstance(entry.parameters, list)

    def test_cache_returns_same_object(self):
        invalidate_cache()
        first = build_catalog()
        second = build_catalog()
        assert first is second

    def test_invalidate_cache_forces_rebuild(self):
        first = build_catalog()
        invalidate_cache()
        second = build_catalog()
        assert first is not second

    def test_source_field_is_builtin_or_discovered(self):
        for entry in _fresh_catalog():
            assert entry.source in ("builtin", "discovered")

    def test_parameter_count_matches_parameters_list(self):
        for entry in _fresh_catalog():
            assert entry.parameter_count == len(entry.parameters)


# ── get_entry ──────────────────────────────────────────────────────────────────

class TestGetEntry:
    def test_returns_entry_for_known_id(self):
        invalidate_cache()
        entry = get_entry("richardson_arms_race")
        assert entry is not None
        assert entry.theory_id == "richardson_arms_race"

    def test_returns_none_for_unknown_id(self):
        invalidate_cache()
        assert get_entry("this_does_not_exist") is None


# ── TheoryCatalogEntry.to_dict / to_summary_dict ──────────────────────────────

class TestCatalogEntrySerialisation:
    def setup_method(self):
        invalidate_cache()
        self.entry = get_entry("richardson_arms_race")
        assert self.entry is not None

    def test_to_dict_has_all_keys(self):
        d = self.entry.to_dict()
        for key in ("theory_id", "name", "domains", "description", "reference",
                    "parameters", "parameter_count", "reads", "writes",
                    "initializes", "source"):
            assert key in d, f"Missing key: {key}"

    def test_to_summary_dict_omits_reads_writes(self):
        d = self.entry.to_summary_dict()
        assert "reads" not in d
        assert "writes" not in d
        assert "initializes" not in d

    def test_to_summary_dict_truncates_description(self):
        d = self.entry.to_summary_dict()
        assert len(d["description"]) <= 201  # 200 chars + possible "…"

    def test_parameters_serialized_as_list_of_dicts(self):
        d = self.entry.to_dict()
        assert isinstance(d["parameters"], list)
        for p in d["parameters"]:
            assert "name" in p
            assert "type" in p
            assert "description" in p

    def test_reference_is_string(self):
        d = self.entry.to_dict()
        assert isinstance(d["reference"], str)


# ── DOMAIN_MAP ─────────────────────────────────────────────────────────────────

class TestDomainMap:
    def test_all_standard_domains_present(self):
        for domain in ("geopolitics", "market", "corporate", "macro", "social", "technology"):
            assert domain in DOMAIN_MAP, f"Missing domain: {domain}"

    def test_all_values_are_lists(self):
        for domain, theory_ids in DOMAIN_MAP.items():
            assert isinstance(theory_ids, list)
            assert len(theory_ids) > 0

    def test_no_duplicates_within_domain(self):
        for domain, theory_ids in DOMAIN_MAP.items():
            assert len(theory_ids) == len(set(theory_ids)), f"Duplicate in {domain}"
