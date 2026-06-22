import time
import pytest
from app.repositories.config_repository import ConfigRepository
from app.services.config_service import ConfigService
from app.utils.db import Database


@pytest.fixture
def svc(tmp_path):
    db_path = str(tmp_path / "test_config_svc.db")
    db = Database(db_path)
    repo = ConfigRepository(db)
    repo.initialize_schema()
    return ConfigService(repo, cache_ttl_seconds=1)


class TestCaching:
    def test_cache_returns_same_object(self, svc):
        a = svc.get_section_groups()
        b = svc.get_section_groups()
        assert a is b

    def test_cache_expires(self, svc):
        a = svc.get_section_groups()
        time.sleep(1.1)
        b = svc.get_section_groups()
        assert a is not b
        assert a == b

    def test_write_invalidates_cache(self, svc):
        a = svc.get_section_groups()
        svc.create_section("test_sec", "Test", "leave", changed_by="test")
        b = svc.get_section_groups()
        assert a is not b
        leave_b = next(g for g in b if g["id"] == "leave")
        assert "test_sec" in leave_b["sections"]


class TestSectionTaxonomy:
    def test_get_section_groups(self, svc):
        groups = svc.get_section_groups()
        assert len(groups) == 8

    def test_get_all_section_ids(self, svc):
        ids = svc.get_all_section_ids()
        assert "annual_leave" in ids
        assert len(ids) >= 40

    def test_get_sections_for_view(self, svc):
        emp = svc.get_sections_for_view("employee")
        assert "leave" in emp
        assert "safety" not in emp

    def test_create_and_update_section(self, svc):
        svc.create_section("custom_s", "Custom Section", "hours", changed_by="test")
        groups = svc.get_section_groups()
        hours = next(g for g in groups if g["id"] == "hours")
        assert "custom_s" in hours["sections"]

        svc.update_section("custom_s", changed_by="test", display_name="Updated")

    def test_create_and_update_section_group(self, svc):
        svc.create_section_group("newgrp", "New Group", changed_by="test")
        groups = svc.get_section_groups()
        assert any(g["id"] == "newgrp" for g in groups)

        svc.update_section_group("newgrp", changed_by="test", label="Renamed")
        groups = svc.get_section_groups()
        grp = next(g for g in groups if g["id"] == "newgrp")
        assert grp["label"] == "Renamed"

    def test_set_view_role_sections(self, svc):
        svc.set_view_role_sections("test_view", ["leave", "compensation"], changed_by="test")
        result = svc.get_sections_for_view("test_view")
        assert result == {"leave", "compensation"}


class TestRubrics:
    def test_global_rubric(self, svc):
        rubric = svc.get_classification_rubric()
        assert "CRITICAL" in rubric

    def test_country_rubric_fallback(self, svc):
        rubric = svc.get_classification_rubric(country="Japan")
        assert "CRITICAL" in rubric

    def test_country_rubric_override(self, svc):
        svc.set_classification_rubric("Japan rules", country="Japan", changed_by="test")
        assert svc.get_classification_rubric(country="Japan") == "Japan rules"
        assert "CRITICAL" in svc.get_classification_rubric()

    def test_delete_rubric_reverts_to_global(self, svc):
        svc.set_classification_rubric("temp", country="UK", changed_by="test")
        svc.delete_classification_rubric("UK", changed_by="test")
        rubric = svc.get_classification_rubric(country="UK")
        assert "CRITICAL" in rubric

    def test_list_rubrics(self, svc):
        rubrics = svc.list_classification_rubrics()
        assert isinstance(rubrics, list)
        assert len(rubrics) >= 1

    def test_rubric_cache_invalidated_on_write(self, svc):
        r1 = svc.get_classification_rubric(country="Brazil")
        svc.set_classification_rubric("Brazil special", country="Brazil", changed_by="test")
        r2 = svc.get_classification_rubric(country="Brazil")
        assert r1 != r2
        assert r2 == "Brazil special"


class TestDriftThresholds:
    def test_get_drift_thresholds(self, svc):
        t = svc.get_drift_thresholds()
        assert t["pending_days_critical"] == 14
        assert t["stale_days_critical"] == 90

    def test_set_drift_threshold_invalidates(self, svc):
        svc.get_drift_thresholds()
        svc.set_config("drift", "pending_days_critical", 21, changed_by="test")
        t = svc.get_drift_thresholds()
        assert t["pending_days_critical"] == 21


class TestGenericConfig:
    def test_get_set_config(self, svc):
        svc.set_config("app", "feature_flag", True, changed_by="test")
        assert svc.get_config("app", "feature_flag") is True

    def test_get_namespace(self, svc):
        svc.set_config("ns", "a", 1, changed_by="test")
        svc.set_config("ns", "b", "two", changed_by="test")
        ns = svc.get_namespace("ns")
        assert ns["a"]["value"] == 1
        assert ns["b"]["value"] == "two"


class TestAuditLog:
    def test_audit_log(self, svc):
        svc.set_config("test", "k", "v1", changed_by="user1")
        svc.set_config("test", "k", "v2", changed_by="user2", reason="updating")
        log = svc.get_config_audit_log("test", "k", limit=10)
        assert len(log) >= 1
        assert log[0]["changed_by"] == "user2"
