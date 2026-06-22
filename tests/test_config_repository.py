import json
import os
import tempfile
import pytest
from app.repositories.config_repository import ConfigRepository
from app.utils.db import Database


@pytest.fixture
def repo(tmp_path):
    db_path = str(tmp_path / "test_config.db")
    db = Database(db_path)
    r = ConfigRepository(db)
    r.initialize_schema()
    return r


class TestSchema:
    def test_tables_created(self, repo):
        conn = repo.db.connect()
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        for t in ("config_entries", "config_audit_log", "section_groups", "sections", "view_role_sections", "classification_rubrics"):
            assert t in tables

    def test_seed_defaults(self, repo):
        groups = repo.list_section_groups()
        assert len(groups) == 8
        assert groups[0]["id"] == "leave"
        ids = repo.get_all_section_ids()
        assert "annual_leave" in ids
        assert "working_hours" in ids

    def test_idempotent_schema(self, repo):
        repo.initialize_schema()
        assert len(repo.list_section_groups()) == 8


class TestGenericConfig:
    def test_get_missing_returns_default(self, repo):
        assert repo.get_config("test", "missing") is None
        assert repo.get_config("test", "missing", "fallback") == "fallback"

    def test_set_and_get(self, repo):
        repo.set_config("test", "key1", 42, "tester", reason="init")
        assert repo.get_config("test", "key1") == 42

    def test_set_overwrites(self, repo):
        repo.set_config("test", "k", "v1", "a")
        repo.set_config("test", "k", "v2", "b", reason="update")
        assert repo.get_config("test", "k") == "v2"

    def test_audit_log_written(self, repo):
        repo.set_config("ns", "k", "old", "user1")
        repo.set_config("ns", "k", "new", "user2", reason="changed it")
        log = repo.get_config_audit_log("ns", "k", limit=10)
        assert len(log) >= 1
        entry = log[0]
        assert entry["changed_by"] == "user2"
        assert entry["change_reason"] == "changed it"

    def test_get_namespace(self, repo):
        repo.set_config("ns", "a", 1, "u")
        repo.set_config("ns", "b", "two", "u")
        ns = repo.get_namespace("ns")
        assert ns["a"]["value"] == 1
        assert ns["b"]["value"] == "two"


class TestDriftThresholdSeeds:
    def test_drift_thresholds_seeded_lowercase(self, repo):
        ns = repo.get_namespace("drift")
        assert "pending_days_critical" in ns
        assert ns["pending_days_critical"]["value"] == 14
        assert ns["stale_days_warning"]["value"] == 30
        assert ns["missing_confidence_critical"]["value"] == 0.8


class TestSections:
    def test_list_section_groups_structure(self, repo):
        groups = repo.list_section_groups()
        leave = next(g for g in groups if g["id"] == "leave")
        assert "annual_leave" in leave["sections"]
        assert leave["label"] == "Leave & Time Off"

    def test_create_section(self, repo):
        repo.create_section("new_sec", "New Section", "leave", sort_order=99, changed_by="test")
        groups = repo.list_section_groups()
        leave = next(g for g in groups if g["id"] == "leave")
        assert "new_sec" in leave["sections"]

    def test_update_section(self, repo):
        result = repo.update_section("annual_leave", display_name="Annual Holiday", changed_by="test")
        assert result is True
        result = repo.update_section("nonexistent", display_name="X", changed_by="test")
        assert result is False

    def test_create_section_group(self, repo):
        repo.create_section_group("custom", "Custom Group", sort_order=99, changed_by="test")
        groups = repo.list_section_groups()
        custom = next((g for g in groups if g["id"] == "custom"), None)
        assert custom is not None
        assert custom["label"] == "Custom Group"

    def test_update_section_group(self, repo):
        result = repo.update_section_group("leave", label="Leave & PTO", changed_by="test")
        assert result is True
        groups = repo.list_section_groups()
        leave = next(g for g in groups if g["id"] == "leave")
        assert leave["label"] == "Leave & PTO"

    def test_get_all_section_ids(self, repo):
        ids = repo.get_all_section_ids()
        assert isinstance(ids, set)
        assert len(ids) >= 40


class TestViewRoles:
    def test_default_view_roles(self, repo):
        emp = repo.get_sections_for_view("employee")
        assert "leave" in emp
        assert "immigration" not in emp
        ops = repo.get_sections_for_view("ops")
        assert "safety" in ops

    def test_set_view_role_sections(self, repo):
        repo.set_view_role_sections("custom_view", ["leave", "hours"], changed_by="test")
        result = repo.get_sections_for_view("custom_view")
        assert result == {"leave", "hours"}

    def test_unknown_view_returns_empty(self, repo):
        assert repo.get_sections_for_view("nonexistent") == set()


class TestRubrics:
    def test_default_global_rubric(self, repo):
        rubric = repo.get_classification_rubric()
        assert "CRITICAL" in rubric
        assert "INFORMATIONAL" in rubric

    def test_country_fallback_to_global(self, repo):
        rubric = repo.get_classification_rubric(country="India")
        assert "CRITICAL" in rubric

    def test_set_country_rubric(self, repo):
        repo.set_classification_rubric("India-specific guidance", country="India", changed_by="test")
        assert repo.get_classification_rubric(country="India") == "India-specific guidance"
        assert "CRITICAL" in repo.get_classification_rubric()

    def test_delete_country_rubric(self, repo):
        repo.set_classification_rubric("temp", country="Germany", changed_by="test")
        assert repo.get_classification_rubric(country="Germany") == "temp"
        repo.delete_classification_rubric("Germany", changed_by="test")
        rubric = repo.get_classification_rubric(country="Germany")
        assert "CRITICAL" in rubric

    def test_list_rubrics(self, repo):
        rubrics = repo.list_classification_rubrics()
        assert len(rubrics) >= 1
        assert any(r["country"] == "global" for r in rubrics)
