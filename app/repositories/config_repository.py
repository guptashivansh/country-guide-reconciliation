from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.utils.db import Database

logger = logging.getLogger(__name__)


_DEFAULT_SECTION_GROUPS = [
    {"id": "leave",        "label": "Leave & Time Off",          "sort_order": 0, "sections": [
        "annual_leave", "sick_leave", "maternity_leave", "paternity_leave",
        "parental_leave", "adoption_leave", "childcare_leave",
        "compassionate_leave", "bereavement_leave", "public_holidays",
        "casual_leave", "personal_leave", "study_leave", "care_leave",
        "other_leaves", "leave_carry_forward",
    ]},
    {"id": "hours",        "label": "Working Hours",             "sort_order": 1, "sections": [
        "working_hours", "overtime", "probation",
        "notice_period_probation", "training_hours",
    ]},
    {"id": "compensation", "label": "Compensation",              "sort_order": 2, "sections": [
        "minimum_wage", "payout_currency", "income_tax",
        "employer_cost", "additional_employer_costs",
        "annual_bonus", "thirteenth_month_pay", "festival_bonus",
        "holiday_bonus", "holiday_pay", "holiday_pay_allowance", "vacation_premium",
        "overtime_pay", "end_of_service_benefit", "severance_accrual",
        "seniority_bonus", "profit_sharing", "long_service_pay",
        "payroll_tax", "withholding_tax", "vat",
    ]},
    {"id": "benefits",     "label": "Benefits & Social Security", "sort_order": 3, "sections": [
        "health_insurance", "public_health_insurance", "private_health_insurance",
        "social_security", "pension", "mandatory_pension",
        "life_insurance", "severance_fund", "employee_benefits",
    ]},
    {"id": "employment",   "label": "Employment Terms",          "sort_order": 4, "sections": [
        "termination_notice", "termination_scenarios", "severance_payable",
        "redundancy_allowance", "employer_obligations", "industrial_relations",
        "contract_durations",
    ]},
    {"id": "onboarding",   "label": "Onboarding & Dates",        "sort_order": 5, "sections": [
        "onboarding_time", "onboarding_health_insurance", "device_shipment",
        "additional_onboarding_requirement", "pay_date", "expenses_cutoff", "onboarding_cutoff",
    ]},
    {"id": "immigration",  "label": "Immigration",               "sort_order": 6, "sections": [
        "work_permit", "work_visa", "expatriate_employment",
    ]},
    {"id": "safety",       "label": "Workplace Safety",          "sort_order": 7, "sections": [
        "workplace_safety", "osh_obligations", "health_and_safety",
    ]},
]

_DEFAULT_VIEW_ROLES = {
    "employee": {"leave", "hours", "compensation", "benefits", "onboarding"},
    "client":   {"leave", "hours", "compensation", "benefits", "employment", "immigration", "onboarding"},
    "ops":      {"leave", "hours", "compensation", "benefits", "employment", "immigration", "safety", "onboarding"},
}

_DEFAULT_CLASSIFICATION_RUBRIC = """\
- CRITICAL: the change affects visa, work permit, or immigration eligibility; or a mandatory \
requirement was removed
- HIGH: the change affects minimum wage, tax, social security, pension, termination, dismissal, \
or overtime; or a numeric threshold moved by 25% or more; or the population of workers covered \
by the rule changed
- MODERATE: a numeric threshold, deadline, or timeline changed, but the rule is not in a \
high-impact domain
- LOW: the wording changed and a requirement was added, but no numeric, eligibility, or timeline \
signal was found
- INFORMATIONAL: no material compliance change — punctuation, capitalization, spacing, or \
non-substantive rewording only"""

_DEFAULT_DRIFT_THRESHOLDS = {
    "pending_days_critical": 14,
    "pending_days_warning": 7,
    "escalated_days_critical": 7,
    "stale_days_critical": 90,
    "stale_days_warning": 30,
    "stale_days_info": 14,
    "missing_confidence_critical": 0.8,
    "missing_confidence_warning": 0.65,
}


class ConfigRepository:

    def __init__(self, db):
        if isinstance(db, str):
            db = Database(db)
        self.db = db

    # ── schema ─────────────────────────────────────────────────────────────────

    def initialize_schema(self):
        conn = self.db.connect()
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS config_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                value_type TEXT NOT NULL DEFAULT 'string',
                description TEXT,
                updated_by TEXT,
                updated_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                UNIQUE(namespace, key)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS config_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace TEXT NOT NULL,
                key TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                changed_by TEXT NOT NULL,
                change_reason TEXT,
                changed_at TEXT NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_config_audit_ns_key ON config_audit_log(namespace, key)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS section_groups (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS sections (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                group_id TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_sections_group ON sections(group_id)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS view_role_sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                view_name TEXT NOT NULL,
                group_id TEXT NOT NULL,
                UNIQUE(view_name, group_id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS classification_rubrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country TEXT,
                rubric_text TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                updated_by TEXT,
                updated_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(country)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_rubrics_country ON classification_rubrics(country)")

        for table, col, default in [
            ("config_entries", "is_active", "1"),
            ("section_groups", "is_active", "1"),
            ("sections", "is_active", "1"),
            ("classification_rubrics", "is_active", "1"),
        ]:
            if col not in self.db.get_table_columns(conn, table):
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} INTEGER NOT NULL DEFAULT {default}")

        conn.commit()

        self._migrate_drift_keys(conn)

        row = c.execute("SELECT COUNT(*) FROM section_groups").fetchone()
        if row[0] == 0:
            self._seed_defaults(conn)

    def _migrate_drift_keys(self, conn):
        c = conn.cursor()
        rows = c.execute(
            "SELECT key FROM config_entries WHERE namespace = ? AND key != lower(key)",
            ("drift",),
        ).fetchall()
        if not rows:
            return
        for (key,) in rows:
            c.execute(
                "UPDATE config_entries SET key = ? WHERE namespace = ? AND key = ?",
                (key.lower(), "drift", key),
            )
        conn.commit()
        logger.info("Migrated %d drift threshold keys to lowercase", len(rows))

    # ── seed ───────────────────────────────────────────────────────────────────

    def _seed_defaults(self, conn):
        now = _now_iso()
        c = conn.cursor()

        for group in _DEFAULT_SECTION_GROUPS:
            c.execute(
                "INSERT OR IGNORE INTO section_groups (id, label, sort_order, is_active, created_at, updated_at) VALUES (?, ?, ?, 1, ?, ?)",
                (group["id"], group["label"], group["sort_order"], now, now),
            )
            for i, section_id in enumerate(group["sections"]):
                display = section_id.replace("_", " ").title()
                c.execute(
                    "INSERT OR IGNORE INTO sections (id, display_name, group_id, sort_order, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
                    (section_id, display, group["id"], i, now, now),
                )

        for view_name, group_ids in _DEFAULT_VIEW_ROLES.items():
            for gid in group_ids:
                c.execute(
                    "INSERT OR IGNORE INTO view_role_sections (view_name, group_id) VALUES (?, ?)",
                    (view_name, gid),
                )

        c.execute(
            "INSERT OR IGNORE INTO classification_rubrics (country, rubric_text, is_active, updated_by, updated_at, created_at) VALUES (NULL, ?, 1, 'system', ?, ?)",
            (_DEFAULT_CLASSIFICATION_RUBRIC, now, now),
        )

        for key, val in _DEFAULT_DRIFT_THRESHOLDS.items():
            vtype = "float" if isinstance(val, float) else "int"
            c.execute(
                "INSERT OR IGNORE INTO config_entries (namespace, key, value, value_type, description, updated_by, updated_at, created_at) VALUES (?, ?, ?, ?, ?, 'system', ?, ?)",
                ("drift", key, json.dumps(val), vtype, f"Drift threshold: {key}", now, now),
            )

        conn.commit()
        logger.info("Seeded default configuration (sections, rubrics, drift thresholds)")

    # ── generic config CRUD ────────────────────────────────────────────────────

    def get_config(self, namespace, key, default=None):
        conn = self.db.connect()
        row = conn.execute(
            "SELECT value, value_type FROM config_entries WHERE namespace = ? AND key = ? AND is_active = 1",
            (namespace, key),
        ).fetchone()
        if row is None:
            return default
        return _deserialize(row[0], row[1])

    def get_namespace(self, namespace):
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT key, value, value_type, description FROM config_entries WHERE namespace = ? AND is_active = 1 ORDER BY key",
            (namespace,),
        ).fetchall()
        return {r[0]: {"value": _deserialize(r[1], r[2]), "type": r[2], "description": r[3]} for r in rows}

    def set_config(self, namespace, key, value, changed_by, reason=None):
        conn = self.db.connect()
        now = _now_iso()
        vtype = _infer_type(value)
        serialized = json.dumps(value)

        old = self.get_config(namespace, key)

        existing = conn.execute(
            "SELECT id FROM config_entries WHERE namespace = ? AND key = ?",
            (namespace, key),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE config_entries SET value = ?, value_type = ?, updated_by = ?, updated_at = ?, is_active = 1 WHERE namespace = ? AND key = ?",
                (serialized, vtype, changed_by, now, namespace, key),
            )
        else:
            conn.execute(
                "INSERT INTO config_entries (namespace, key, value, value_type, updated_by, updated_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (namespace, key, serialized, vtype, changed_by, now, now),
            )

        conn.execute(
            "INSERT INTO config_audit_log (namespace, key, old_value, new_value, changed_by, change_reason, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (namespace, key, json.dumps(old) if old is not None else None, serialized, changed_by, reason, now),
        )
        conn.commit()

    # ── section taxonomy ───────────────────────────────────────────────────────

    def list_section_groups(self):
        conn = self.db.connect()
        groups = conn.execute(
            "SELECT id, label, sort_order FROM section_groups WHERE is_active = 1 ORDER BY sort_order",
        ).fetchall()
        result = []
        for g in groups:
            sections = conn.execute(
                "SELECT id FROM sections WHERE group_id = ? AND is_active = 1 ORDER BY sort_order",
                (g[0],),
            ).fetchall()
            result.append({"id": g[0], "label": g[1], "sections": [s[0] for s in sections]})
        return result

    def get_all_section_ids(self):
        conn = self.db.connect()
        rows = conn.execute("SELECT id FROM sections WHERE is_active = 1").fetchall()
        return {r[0] for r in rows}

    def get_sections_for_view(self, view_name):
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT group_id FROM view_role_sections WHERE view_name = ?",
            (view_name,),
        ).fetchall()
        return {r[0] for r in rows}

    def create_section(self, section_id, display_name, group_id, sort_order=0, changed_by="system"):
        conn = self.db.connect()
        now = _now_iso()
        conn.execute(
            "INSERT INTO sections (id, display_name, group_id, sort_order, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
            (section_id, display_name, group_id, sort_order, now, now),
        )
        conn.execute(
            "INSERT INTO config_audit_log (namespace, key, old_value, new_value, changed_by, change_reason, changed_at) VALUES (?, ?, NULL, ?, ?, ?, ?)",
            ("sections", section_id, json.dumps({"display_name": display_name, "group_id": group_id}), changed_by, "section created", now),
        )
        conn.commit()

    def update_section(self, section_id, display_name=None, group_id=None, sort_order=None, is_active=None, changed_by="system"):
        conn = self.db.connect()
        now = _now_iso()
        old = conn.execute("SELECT display_name, group_id, sort_order, is_active FROM sections WHERE id = ?", (section_id,)).fetchone()
        if not old:
            return False

        sets, vals = [], []
        if display_name is not None:
            sets.append("display_name = ?"); vals.append(display_name)
        if group_id is not None:
            sets.append("group_id = ?"); vals.append(group_id)
        if sort_order is not None:
            sets.append("sort_order = ?"); vals.append(sort_order)
        if is_active is not None:
            sets.append("is_active = ?"); vals.append(int(is_active))
        if not sets:
            return True
        sets.append("updated_at = ?"); vals.append(now)
        vals.append(section_id)

        conn.execute(f"UPDATE sections SET {', '.join(sets)} WHERE id = ?", vals)
        conn.execute(
            "INSERT INTO config_audit_log (namespace, key, old_value, new_value, changed_by, change_reason, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("sections", section_id, json.dumps({"display_name": old[0], "group_id": old[1]}),
             json.dumps({"display_name": display_name or old[0], "group_id": group_id or old[1]}), changed_by, "section updated", now),
        )
        conn.commit()
        return True

    def create_section_group(self, group_id, label, sort_order=0, changed_by="system"):
        conn = self.db.connect()
        now = _now_iso()
        conn.execute(
            "INSERT INTO section_groups (id, label, sort_order, is_active, created_at, updated_at) VALUES (?, ?, ?, 1, ?, ?)",
            (group_id, label, sort_order, now, now),
        )
        conn.execute(
            "INSERT INTO config_audit_log (namespace, key, old_value, new_value, changed_by, change_reason, changed_at) VALUES (?, ?, NULL, ?, ?, ?, ?)",
            ("section_groups", group_id, json.dumps({"label": label}), changed_by, "section group created", now),
        )
        conn.commit()

    def update_section_group(self, group_id, label=None, sort_order=None, is_active=None, changed_by="system"):
        conn = self.db.connect()
        now = _now_iso()
        old = conn.execute("SELECT label, sort_order, is_active FROM section_groups WHERE id = ?", (group_id,)).fetchone()
        if not old:
            return False

        sets, vals = [], []
        if label is not None:
            sets.append("label = ?"); vals.append(label)
        if sort_order is not None:
            sets.append("sort_order = ?"); vals.append(sort_order)
        if is_active is not None:
            sets.append("is_active = ?"); vals.append(int(is_active))
        if not sets:
            return True
        sets.append("updated_at = ?"); vals.append(now)
        vals.append(group_id)

        conn.execute(f"UPDATE section_groups SET {', '.join(sets)} WHERE id = ?", vals)
        conn.execute(
            "INSERT INTO config_audit_log (namespace, key, old_value, new_value, changed_by, change_reason, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("section_groups", group_id, json.dumps({"label": old[0]}),
             json.dumps({"label": label or old[0]}), changed_by, "section group updated", now),
        )
        conn.commit()
        return True

    def set_view_role_sections(self, view_name, group_ids, changed_by="system"):
        conn = self.db.connect()
        now = _now_iso()

        old_rows = conn.execute("SELECT group_id FROM view_role_sections WHERE view_name = ?", (view_name,)).fetchall()
        old_groups = {r[0] for r in old_rows}

        conn.execute("DELETE FROM view_role_sections WHERE view_name = ?", (view_name,))
        for gid in group_ids:
            conn.execute("INSERT INTO view_role_sections (view_name, group_id) VALUES (?, ?)", (view_name, gid))

        conn.execute(
            "INSERT INTO config_audit_log (namespace, key, old_value, new_value, changed_by, change_reason, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("view_roles", view_name, json.dumps(sorted(old_groups)), json.dumps(sorted(group_ids)), changed_by, "view roles updated", now),
        )
        conn.commit()

    # ── classification rubrics ─────────────────────────────────────────────────

    def get_classification_rubric(self, country=None):
        conn = self.db.connect()
        if country:
            row = conn.execute(
                "SELECT rubric_text FROM classification_rubrics WHERE country = ? AND is_active = 1",
                (country,),
            ).fetchone()
            if row:
                return row[0]
        row = conn.execute(
            "SELECT rubric_text FROM classification_rubrics WHERE country IS NULL AND is_active = 1",
        ).fetchone()
        return row[0] if row else _DEFAULT_CLASSIFICATION_RUBRIC

    def list_classification_rubrics(self):
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT id, country, rubric_text, updated_by, updated_at FROM classification_rubrics WHERE is_active = 1 ORDER BY country",
        ).fetchall()
        return [{"id": r[0], "country": r[1] or "global", "rubric_text": r[2], "updated_by": r[3], "updated_at": r[4]} for r in rows]

    def set_classification_rubric(self, rubric_text, country=None, changed_by="system"):
        conn = self.db.connect()
        now = _now_iso()
        old = self.get_classification_rubric(country)

        if country is None:
            existing = conn.execute(
                "SELECT id FROM classification_rubrics WHERE country IS NULL",
            ).fetchone()
        else:
            existing = conn.execute(
                "SELECT id FROM classification_rubrics WHERE country = ?",
                (country,),
            ).fetchone()

        if existing:
            conn.execute(
                "UPDATE classification_rubrics SET rubric_text = ?, is_active = 1, updated_by = ?, updated_at = ? WHERE id = ?",
                (rubric_text, changed_by, now, existing[0]),
            )
        else:
            conn.execute(
                "INSERT INTO classification_rubrics (country, rubric_text, is_active, updated_by, updated_at, created_at) VALUES (?, ?, 1, ?, ?, ?)",
                (country, rubric_text, changed_by, now, now),
            )

        conn.execute(
            "INSERT INTO config_audit_log (namespace, key, old_value, new_value, changed_by, change_reason, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("rubrics", country or "global", json.dumps(old) if old else None, json.dumps(rubric_text), changed_by, "rubric updated", now),
        )
        conn.commit()

    def delete_classification_rubric(self, country, changed_by="system"):
        if not country:
            return False
        conn = self.db.connect()
        now = _now_iso()
        old = self.get_classification_rubric(country)
        conn.execute("UPDATE classification_rubrics SET is_active = 0, updated_at = ? WHERE country = ?", (now, country))
        conn.execute(
            "INSERT INTO config_audit_log (namespace, key, old_value, new_value, changed_by, change_reason, changed_at) VALUES (?, ?, ?, NULL, ?, ?, ?)",
            ("rubrics", country, json.dumps(old) if old else None, changed_by, "rubric deleted", now),
        )
        conn.commit()
        return True

    # ── audit log ──────────────────────────────────────────────────────────────

    def get_config_audit_log(self, namespace=None, key=None, limit=50):
        conn = self.db.connect()
        sql = "SELECT namespace, key, old_value, new_value, changed_by, change_reason, changed_at FROM config_audit_log"
        params = []
        clauses = []
        if namespace:
            clauses.append("namespace = ?"); params.append(namespace)
        if key:
            clauses.append("key = ?"); params.append(key)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY changed_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [{"namespace": r[0], "key": r[1], "old_value": r[2], "new_value": r[3],
                 "changed_by": r[4], "change_reason": r[5], "changed_at": r[6]} for r in rows]


# ── helpers ────────────────────────────────────────────────────────────────────

def _now_iso():
    return datetime.now(tz=timezone.utc).isoformat()


def _deserialize(value_str, value_type):
    raw = json.loads(value_str)
    if value_type == "int":
        return int(raw)
    if value_type == "float":
        return float(raw)
    if value_type == "bool":
        return bool(raw)
    return raw


def _infer_type(value):
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, (dict, list)):
        return "json"
    return "string"
