import time
from typing import Any, Optional


class ConfigService:

    def __init__(self, config_repository, cache_ttl_seconds=300):
        self._repo = config_repository
        self._ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[Any, float]] = {}
        self._version = 0
        self._version_checked_at = 0.0
        self._VERSION_CHECK_INTERVAL = 30

    # ── section taxonomy ───────────────────────────────────────────────────────

    def get_section_groups(self) -> list[dict]:
        return self._cached("section_groups", self._repo.list_section_groups)

    def get_all_section_ids(self) -> set[str]:
        return self._cached("all_section_ids", self._repo.get_all_section_ids)

    def get_sections_for_view(self, view_name: str) -> set[str]:
        return self._cached(f"view:{view_name}", lambda: self._repo.get_sections_for_view(view_name))

    # ── classification rubrics ─────────────────────────────────────────────────

    def get_classification_rubric(self, country: Optional[str] = None) -> str:
        key = f"rubric:{country or 'global'}"
        return self._cached(key, lambda: self._repo.get_classification_rubric(country))

    def list_classification_rubrics(self) -> list[dict]:
        return self._cached("rubrics_list", self._repo.list_classification_rubrics)

    def set_classification_rubric(self, rubric_text: str, country: Optional[str] = None, changed_by: str = "system"):
        self._repo.set_classification_rubric(rubric_text, country, changed_by)
        self._bump_version()
        self._invalidate("rubric:")
        self._invalidate("rubrics_list")

    def delete_classification_rubric(self, country: str, changed_by: str = "system") -> bool:
        result = self._repo.delete_classification_rubric(country, changed_by)
        self._bump_version()
        self._invalidate("rubric:")
        self._invalidate("rubrics_list")
        return result

    # ── core sections (coverage) ─────────────────────────────────────────────

    def get_core_sections(self) -> list[str]:
        return self._cached("core_sections", self._repo.get_core_sections)

    def set_core_sections(self, section_ids: list[str], changed_by: str = "system"):
        self._repo.set_core_sections(section_ids, changed_by)
        self._bump_version()
        self._invalidate("core_sections")

    # ── drift thresholds ───────────────────────────────────────────────────────

    def get_drift_thresholds(self) -> dict:
        def _fetch():
            raw = self._repo.get_namespace("drift")
            return {k: v["value"] for k, v in raw.items()}
        return self._cached("drift_thresholds", _fetch)

    # ── generic config ─────────────────────────────────────────────────────────

    def get_config(self, namespace: str, key: str, default=None):
        cache_key = f"config:{namespace}:{key}"
        return self._cached(cache_key, lambda: self._repo.get_config(namespace, key, default))

    def get_namespace(self, namespace: str) -> dict:
        return self._cached(f"ns:{namespace}", lambda: self._repo.get_namespace(namespace))

    def set_config(self, namespace: str, key: str, value, changed_by: str, reason: Optional[str] = None):
        self._repo.set_config(namespace, key, value, changed_by, reason)
        self._bump_version()
        self._invalidate(f"config:{namespace}:{key}")
        self._invalidate(f"ns:{namespace}")
        if namespace == "drift":
            self._invalidate("drift_thresholds")

    # ── section/group mutations (delegate + invalidate) ────────────────────────

    def create_section(self, section_id, display_name, group_id, sort_order=0, changed_by="system"):
        self._repo.create_section(section_id, display_name, group_id, sort_order, changed_by)
        self._bump_version()
        self._invalidate_taxonomy()

    def update_section(self, section_id, changed_by="system", **kwargs):
        result = self._repo.update_section(section_id, changed_by=changed_by, **kwargs)
        self._bump_version()
        self._invalidate_taxonomy()
        return result

    def create_section_group(self, group_id, label, sort_order=0, changed_by="system"):
        self._repo.create_section_group(group_id, label, sort_order, changed_by)
        self._bump_version()
        self._invalidate_taxonomy()

    def update_section_group(self, group_id, changed_by="system", **kwargs):
        result = self._repo.update_section_group(group_id, changed_by=changed_by, **kwargs)
        self._bump_version()
        self._invalidate_taxonomy()
        return result

    def set_view_role_sections(self, view_name, group_ids, changed_by="system"):
        self._repo.set_view_role_sections(view_name, group_ids, changed_by)
        self._bump_version()
        self._invalidate(f"view:{view_name}")

    # ── audit ──────────────────────────────────────────────────────────────────

    def get_config_audit_log(self, namespace=None, key=None, limit=50):
        return self._repo.get_config_audit_log(namespace, key, limit)

    # ── country flags (delegates to source_countries via repo.db) ──────────────

    def get_country_iso_codes(self) -> dict[str, str]:
        def _fetch():
            conn = self._repo.db.connect()
            rows = conn.execute("SELECT name, iso_code FROM source_countries WHERE is_active = 1").fetchall()
            return {r[0]: r[1] for r in rows}
        return self._cached("country_iso_codes", _fetch)

    # ── cache internals ────────────────────────────────────────────────────────

    def _cached(self, key: str, fetcher):
        now = time.monotonic()
        if now - self._version_checked_at > self._VERSION_CHECK_INTERVAL:
            db_version = self._repo.get_cache_version()
            self._version_checked_at = now
            if db_version != self._version:
                self._version = db_version
                self._cache.clear()
        entry = self._cache.get(key)
        if entry and entry[1] > now:
            return entry[0]
        value = fetcher()
        self._cache[key] = (value, now + self._ttl)
        return value

    def _bump_version(self):
        self._version = self._repo.bump_cache_version()
        self._version_checked_at = time.monotonic()

    def _invalidate(self, prefix: str):
        to_remove = [k for k in self._cache if k == prefix or k.startswith(prefix)]
        for k in to_remove:
            del self._cache[k]

    def _invalidate_taxonomy(self):
        self._invalidate("section_groups")
        self._invalidate("all_section_ids")
        self._invalidate("view:")

    def invalidate_all(self):
        self._cache.clear()
