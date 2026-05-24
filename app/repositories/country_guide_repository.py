from datetime import date, datetime

from app.utils.db import Database


class CountryGuideRepository:
    def __init__(self, db):
        if isinstance(db, str):
            db = Database(db)
        self.db = db

    def connect(self):
        return self.db.connect()

    def _now(self):
        return datetime.now().isoformat()

    def _normalize_effective_date(self, effective_date, created_at=None):
        if isinstance(effective_date, datetime):
            return effective_date.date().isoformat()
        if isinstance(effective_date, date):
            return effective_date.isoformat()
        if effective_date:
            return str(effective_date).strip()[:10]
        timestamp = created_at or self._now()
        return str(timestamp)[:10]

    def _superseded_at_for_effective_date(self, effective_date):
        return f"{self._normalize_effective_date(effective_date)}T00:00:00"

    def _next_version_number(self, cursor, country, section):
        cursor.execute(
            "SELECT COALESCE(MAX(version_number), 0) FROM country_guide_versions WHERE country=? AND section=?",
            (country, section),
        )
        return int(cursor.fetchone()[0] or 0) + 1

    def _version_row(self, row):
        return {
            "id": row[0],
            "country": row[1],
            "section": row[2],
            "value": row[3],
            "source_url": row[4],
            "source_hash": row[5],
            "effective_date": row[6],
            "created_at": row[7],
            "superseded_at": row[8],
            "version_number": row[9],
            "approval_reference": row[10],
        }

    def _publish_rule_version(
        self,
        cursor,
        country,
        section,
        value,
        source_url,
        source_hash="",
        effective_date=None,
        created_at=None,
        approval_reference=None,
    ):
        created_at = created_at or self._now()
        effective_date = self._normalize_effective_date(effective_date, created_at)
        approval_reference = approval_reference or "direct_upsert"
        source_url = source_url or ""
        source_hash = source_hash or ""

        cursor.execute("""
            SELECT value, source_url, source_hash, version_number
            FROM country_guide
            WHERE country=? AND section=?
        """, (country, section))
        current = cursor.fetchone()

        if current and current[0] == value and (current[1] or "") == source_url and (current[2] or "") == source_hash:
            current_version = current[3] or 1
            cursor.execute("""
                UPDATE country_guide
                SET last_updated=?, effective_date=COALESCE(effective_date, ?),
                    created_at=COALESCE(created_at, ?), version_number=COALESCE(version_number, ?),
                    approval_reference=COALESCE(approval_reference, ?)
                WHERE country=? AND section=?
            """, (created_at, effective_date, created_at, current_version, approval_reference, country, section))
            return current_version

        version_number = self._next_version_number(cursor, country, section)
        if current:
            cursor.execute("""
                UPDATE country_guide_versions
                SET superseded_at=COALESCE(superseded_at, ?)
                WHERE country=? AND section=? AND superseded_at IS NULL
            """, (self._superseded_at_for_effective_date(effective_date), country, section))

        cursor.execute('''
            INSERT INTO country_guide_versions
            (country, section, value, source_url, source_hash, effective_date, created_at,
             superseded_at, version_number, approval_reference)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
        ''', (
            country,
            section,
            value,
            source_url,
            source_hash,
            effective_date,
            created_at,
            version_number,
            approval_reference,
        ))
        cursor.execute('''
            INSERT INTO country_guide
            (country, section, value, source_url, source_hash, last_updated,
             effective_date, created_at, version_number, approval_reference)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(country, section) DO UPDATE SET
                value=excluded.value,
                source_url=excluded.source_url,
                source_hash=excluded.source_hash,
                last_updated=excluded.last_updated,
                effective_date=excluded.effective_date,
                created_at=COALESCE(country_guide.created_at, excluded.created_at),
                version_number=excluded.version_number,
                approval_reference=excluded.approval_reference
        ''', (
            country,
            section,
            value,
            source_url,
            source_hash,
            created_at,
            effective_date,
            created_at,
            version_number,
            approval_reference,
        ))
        return version_number

    def initialize_schema(self):
        conn = self.connect()
        c = conn.cursor()

        c.execute('''
            CREATE TABLE IF NOT EXISTS country_guide (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country TEXT,
                section TEXT,
                value TEXT,
                source_url TEXT,
                source_hash TEXT,
                last_updated TEXT,
                UNIQUE(country, section)
            )
        ''')

        guide_columns = self.db.get_table_columns(conn, "country_guide")
        if "effective_date" not in guide_columns:
            c.execute("ALTER TABLE country_guide ADD COLUMN effective_date TEXT")
        if "created_at" not in guide_columns:
            c.execute("ALTER TABLE country_guide ADD COLUMN created_at TEXT")
        if "version_number" not in guide_columns:
            c.execute("ALTER TABLE country_guide ADD COLUMN version_number INTEGER")
        if "approval_reference" not in guide_columns:
            c.execute("ALTER TABLE country_guide ADD COLUMN approval_reference TEXT")

        c.execute('''
            CREATE TABLE IF NOT EXISTS country_guide_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country TEXT NOT NULL,
                section TEXT NOT NULL,
                value TEXT NOT NULL,
                source_url TEXT,
                source_hash TEXT,
                effective_date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                superseded_at TEXT,
                version_number INTEGER NOT NULL,
                approval_reference TEXT,
                metadata TEXT DEFAULT '{}',
                UNIQUE(country, section, version_number)
            )
        ''')
        c.execute('''
            CREATE INDEX IF NOT EXISTS idx_country_guide_versions_lookup
            ON country_guide_versions(country, section, effective_date, superseded_at)
        ''')
        c.execute('''
            CREATE INDEX IF NOT EXISTS idx_country_guide_versions_history
            ON country_guide_versions(country, section, version_number)
        ''')

        migration_timestamp = self._now()
        c.execute("""
            UPDATE country_guide
            SET created_at=COALESCE(created_at, last_updated, ?),
                effective_date=COALESCE(effective_date, substr(COALESCE(last_updated, ?), 1, 10)),
                version_number=COALESCE(version_number, 1),
                approval_reference=COALESCE(approval_reference, 'initial_migration')
        """, (migration_timestamp, migration_timestamp))
        c.execute("""
            INSERT OR IGNORE INTO country_guide_versions
            (country, section, value, source_url, source_hash, effective_date, created_at,
             superseded_at, version_number, approval_reference)
            SELECT country, section, value, source_url, source_hash,
                   COALESCE(effective_date, substr(COALESCE(last_updated, ?), 1, 10)),
                   COALESCE(created_at, last_updated, ?),
                   NULL,
                   COALESCE(version_number, 1),
                   COALESCE(approval_reference, 'initial_migration')
            FROM country_guide
        """, (migration_timestamp, migration_timestamp))

        c.execute('''
            CREATE TABLE IF NOT EXISTS review_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country TEXT,
                section TEXT,
                old_value TEXT,
                new_value TEXT,
                severity TEXT,
                confidence REAL,
                source_url TEXT,
                source_paragraph TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                reviewed_at TEXT,
                reviewer_comment TEXT
            )
        ''')

        review_columns = self.db.get_table_columns(conn, "review_queue")
        if "source_hash" not in review_columns:
            c.execute("ALTER TABLE review_queue ADD COLUMN source_hash TEXT")
        if "source_snapshot_id" not in review_columns:
            c.execute("ALTER TABLE review_queue ADD COLUMN source_snapshot_id INTEGER")
        if "reviewer_assignee" not in review_columns:
            c.execute("ALTER TABLE review_queue ADD COLUMN reviewer_assignee TEXT")
        if "reviewer_rationale" not in review_columns:
            c.execute("ALTER TABLE review_queue ADD COLUMN reviewer_rationale TEXT")
        if "effective_date" not in review_columns:
            c.execute("ALTER TABLE review_queue ADD COLUMN effective_date TEXT")
        if "materiality_level" not in review_columns:
            c.execute("ALTER TABLE review_queue ADD COLUMN materiality_level TEXT")
        if "change_type" not in review_columns:
            c.execute("ALTER TABLE review_queue ADD COLUMN change_type TEXT")

        c.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT,
                country TEXT,
                section TEXT,
                old_value TEXT,
                new_value TEXT,
                decision TEXT,
                reviewer_comment TEXT,
                timestamp TEXT
            )
        ''')

        audit_columns = self.db.get_table_columns(conn, "audit_log")
        if "reviewer_assignee" not in audit_columns:
            c.execute("ALTER TABLE audit_log ADD COLUMN reviewer_assignee TEXT")
        if "reviewer_rationale" not in audit_columns:
            c.execute("ALTER TABLE audit_log ADD COLUMN reviewer_rationale TEXT")

        conn.commit()
        conn.close()

    def seed_initial_country_guide(self):
        initial_data = [
            ("India", "annual_leave", "12 days per year", "https://labour.gov.in/", ""),
            ("India", "working_hours", "48 hours per week, 9 hours per day", "https://labour.gov.in/", ""),
            ("India", "public_holidays", "National holidays: 3 (Republic Day, Independence Day, Gandhi Jayanti)", "https://labour.gov.in/", ""),
            ("India", "overtime", "Twice the ordinary rate of wages", "https://labour.gov.in/", ""),
            ("India", "termination_notice", "30 days notice or pay in lieu", "https://labour.gov.in/", ""),
            ("India", "provident_fund", "12% of basic salary contributed by employer", "https://www.epfindia.gov.in/site_en/index.php", ""),
        ]

        conn = self.connect()
        c = conn.cursor()
        timestamp = self._now()
        for country, section, value, url, source_hash in initial_data:
            self._publish_rule_version(
                c,
                country,
                section,
                value,
                url,
                source_hash,
                effective_date=timestamp[:10],
                created_at=timestamp,
                approval_reference="initial_seed",
            )

        conn.commit()
        conn.close()

    def list_countries_summary(self):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT country, COUNT(*) as n, MAX(last_updated) as updated
            FROM country_guide
            GROUP BY country
            ORDER BY country
        """)
        rows = c.fetchall()
        conn.close()
        return [{"country": r[0], "rule_count": r[1], "last_updated": r[2]} for r in rows]

    def get_country_sections(self, country):
        conn = self.connect()
        c = conn.cursor()
        c.execute(
            "SELECT section, value, last_updated FROM country_guide WHERE country = ? ORDER BY section",
            (country,),
        )
        rows = c.fetchall()
        conn.close()
        return [{"section": r[0], "value": r[1], "last_updated": r[2]} for r in rows]

    def list_country_guide_entries(self):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT country, section, value, source_url, last_updated, effective_date,
                   created_at, version_number, approval_reference
            FROM country_guide
            ORDER BY country, section
        """)
        rows = c.fetchall()
        conn.close()
        return [{
            "country": r[0], "section": r[1], "value": r[2],
            "source_url": r[3], "last_updated": r[4],
            "effective_date": r[5], "created_at": r[6],
            "version_number": r[7], "approval_reference": r[8],
        } for r in rows]

    def list_pending_review_items(self):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT id, country, section, old_value, new_value, severity, confidence, source_url, source_paragraph,
                   created_at, source_snapshot_id, status, reviewed_at, reviewer_comment, reviewer_assignee,
                   reviewer_rationale, effective_date, materiality_level, change_type
            FROM review_queue WHERE status IN ('pending', 'escalated')
            ORDER BY
                CASE status WHEN 'escalated' THEN 0 ELSE 1 END,
                CASE severity WHEN 'critical' THEN 1 WHEN 'major' THEN 2 ELSE 3 END,
                confidence DESC
        """)
        rows = c.fetchall()
        conn.close()
        return [{
            "id": r[0], "country": r[1], "section": r[2],
            "old_value": r[3], "new_value": r[4], "severity": r[5],
            "confidence": r[6], "source_url": r[7],
            "source_paragraph": r[8], "created_at": r[9],
            "source_snapshot_id": r[10],
            "status": r[11], "reviewed_at": r[12],
            "reviewer_notes": r[13], "reviewer_assignee": r[14],
            "reviewer_rationale": r[15],
            "effective_date": r[16],
            "materiality_level": r[17],
            "change_type": r[18],
        } for r in rows]

    def list_audit_entries(self, limit=50):
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return [{
            "id": r[0], "action": r[1], "country": r[2], "section": r[3],
            "old_value": r[4], "new_value": r[5], "decision": r[6],
            "reviewer_comment": r[7], "timestamp": r[8],
            "reviewer_assignee": r[9] if len(r) > 9 else None,
            "reviewer_rationale": r[10] if len(r) > 10 else None,
        } for r in rows]

    def upsert_guide_entry(self, country, section, value, source_url, source_hash="", effective_date=None, approval_reference=None):
        conn = self.connect()
        c = conn.cursor()
        self._publish_rule_version(
            c,
            country,
            section,
            value,
            source_url,
            source_hash,
            effective_date=effective_date,
            approval_reference=approval_reference,
        )
        conn.commit()
        conn.close()

    def get_current_value(self, country, section):
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT value FROM country_guide WHERE country=? AND section=?", (country, section))
        row = c.fetchone()
        conn.close()
        return row[0] if row else "Not previously recorded"

    def get_current_rule(self, country, section):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT country, section, value, source_url, source_hash, effective_date, created_at,
                   NULL as superseded_at, version_number, approval_reference
            FROM country_guide
            WHERE country=? AND section=?
        """, (country, section))
        row = c.fetchone()
        conn.close()
        return self._version_row((None,) + row) if row else None

    def list_rule_versions(self, country, section):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT id, country, section, value, source_url, source_hash, effective_date,
                   created_at, superseded_at, version_number, approval_reference
            FROM country_guide_versions
            WHERE country=? AND section=?
            ORDER BY version_number ASC
        """, (country, section))
        rows = c.fetchall()
        conn.close()
        return [self._version_row(row) for row in rows]

    def get_rule_at_date(self, country, section, as_of_date):
        query_date = self._normalize_effective_date(as_of_date)
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT id, country, section, value, source_url, source_hash, effective_date,
                   created_at, superseded_at, version_number, approval_reference
            FROM country_guide_versions
            WHERE country=? AND section=?
              AND date(effective_date) <= date(?)
              AND (superseded_at IS NULL OR date(superseded_at) > date(?))
            ORDER BY date(effective_date) DESC, version_number DESC
            LIMIT 1
        """, (country, section, query_date, query_date))
        row = c.fetchone()
        conn.close()
        return self._version_row(row) if row else None

    def pending_review_exists(self, country, section):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT id FROM review_queue
            WHERE country=? AND section=? AND status IN ('pending', 'escalated')
        """, (country, section))
        exists = c.fetchone() is not None
        conn.close()
        return exists

    def enqueue_review_item(self, country, section, old_value, new_value, severity, confidence, source_url, source_paragraph, source_hash, source_snapshot_id, effective_date=None, materiality_level=None, change_type=None):
        conn = self.connect()
        c = conn.cursor()
        c.execute('''
            INSERT INTO review_queue
            (country, section, old_value, new_value, severity, confidence, source_url, source_paragraph,
             status, created_at, source_hash, source_snapshot_id, effective_date, materiality_level, change_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)
        ''', (
            country,
            section,
            old_value,
            new_value,
            severity,
            confidence,
            source_url,
            source_paragraph,
            self._now(),
            source_hash,
            source_snapshot_id,
            self._normalize_effective_date(effective_date) if effective_date else None,
            materiality_level,
            change_type,
        ))
        conn.commit()
        conn.close()

    def approve_pending_review_item(self, item_id, comment, assignee="", rationale="", effective_date=None):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT country, section, old_value, new_value, source_url, source_hash,
                   source_paragraph, confidence, source_snapshot_id, created_at, effective_date
            FROM review_queue
            WHERE id=? AND status IN ('pending', 'escalated')
        """, (item_id,))
        item = c.fetchone()
        if not item:
            conn.close()
            return None

        country, section, old_value, new_value, source_url, source_hash, \
            source_paragraph, confidence, source_snapshot_id, created_at, queued_effective_date = item
        timestamp = self._now()
        resolved_effective_date = self._normalize_effective_date(effective_date or queued_effective_date, timestamp)
        approval_reference = f"review_queue:{item_id}"
        version_number = self._publish_rule_version(
            c,
            country,
            section,
            new_value,
            source_url,
            source_hash,
            effective_date=resolved_effective_date,
            created_at=timestamp,
            approval_reference=approval_reference,
        )
        c.execute("""
            UPDATE review_queue
            SET status='approved', reviewed_at=?, reviewer_comment=?, reviewer_assignee=?,
                reviewer_rationale=?, effective_date=?
            WHERE id=?
        """, (timestamp, comment, assignee, rationale, resolved_effective_date, item_id))
        c.execute('''
            INSERT INTO audit_log
            (action, country, section, old_value, new_value, decision, reviewer_comment, timestamp, reviewer_assignee, reviewer_rationale)
            VALUES ('REVIEW', ?, ?, ?, ?, 'approved', ?, ?, ?, ?)
        ''', (country, section, old_value, new_value, comment, timestamp, assignee, rationale))

        conn.commit()
        conn.close()
        return {
            "country": country, "section": section, "status": "approved", "reviewed_at": timestamp,
            "item_id": item_id, "new_value": new_value, "source_url": source_url,
            "source_hash": source_hash, "source_paragraph": source_paragraph,
            "confidence": confidence, "source_snapshot_id": source_snapshot_id,
            "reviewer_assignee": assignee, "reviewer_rationale": rationale, "reviewer_comment": comment,
            "effective_date": resolved_effective_date, "version_number": version_number,
            "approval_reference": approval_reference,
        }

    def reject_pending_review_item(self, item_id, comment, assignee="", rationale=""):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT country, section, old_value, new_value
            FROM review_queue
            WHERE id=? AND status IN ('pending', 'escalated')
        """, (item_id,))
        item = c.fetchone()
        if not item:
            conn.close()
            return None

        country, section, old_value, new_value = item
        timestamp = self._now()
        c.execute("""
            UPDATE review_queue
            SET status='rejected', reviewed_at=?, reviewer_comment=?, reviewer_assignee=?, reviewer_rationale=?
            WHERE id=?
        """, (timestamp, comment, assignee, rationale, item_id))
        c.execute('''
            INSERT INTO audit_log
            (action, country, section, old_value, new_value, decision, reviewer_comment, timestamp, reviewer_assignee, reviewer_rationale)
            VALUES ('REVIEW', ?, ?, ?, ?, 'rejected', ?, ?, ?, ?)
        ''', (country, section, old_value, new_value, comment, timestamp, assignee, rationale))

        conn.commit()
        conn.close()
        return {"country": country, "section": section, "status": "rejected", "reviewed_at": timestamp}

    def update_review_assignment(self, item_id, comment, assignee=""):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT country, section, status
            FROM review_queue
            WHERE id=? AND status IN ('pending', 'escalated')
        """, (item_id,))
        item = c.fetchone()
        if not item:
            conn.close()
            return None

        country, section, status = item
        timestamp = self._now()
        c.execute("""
            UPDATE review_queue
            SET reviewed_at=?, reviewer_comment=?, reviewer_assignee=?
            WHERE id=?
        """, (timestamp, comment, assignee, item_id))

        conn.commit()
        conn.close()
        return {"country": country, "section": section, "status": status, "reviewed_at": timestamp}

    def bulk_approve_non_critical(self, country, comment="", rationale="", effective_date=None):
        """Approve all pending/escalated non-critical items for a country in one transaction."""
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT id, country, section, old_value, new_value, source_url, source_hash,
                   source_paragraph, confidence, source_snapshot_id, effective_date
            FROM review_queue
            WHERE country = ? AND status IN ('pending', 'escalated')
              AND (severity IS NULL OR LOWER(severity) != 'critical')
            ORDER BY section
        """, (country,))
        rows = c.fetchall()

        if not rows:
            conn.close()
            return {"approved": 0}

        timestamp = self._now()
        approved_items = []
        for row in rows:
            item_id, country_val, section, old_value, new_value, source_url, source_hash, \
                source_paragraph, confidence, source_snapshot_id, queued_effective_date = row
            resolved_effective_date = self._normalize_effective_date(effective_date or queued_effective_date, timestamp)
            approval_reference = f"review_queue:{item_id}"
            version_number = self._publish_rule_version(
                c,
                country_val,
                section,
                new_value,
                source_url,
                source_hash,
                effective_date=resolved_effective_date,
                created_at=timestamp,
                approval_reference=approval_reference,
            )
            c.execute("""
                UPDATE review_queue
                SET status='approved', reviewed_at=?, reviewer_comment=?, reviewer_rationale=?, effective_date=?
                WHERE id=?
            """, (timestamp, comment, rationale, resolved_effective_date, item_id))
            c.execute('''
                INSERT INTO audit_log
                (action, country, section, old_value, new_value, decision, reviewer_comment, timestamp, reviewer_rationale)
                VALUES ('REVIEW', ?, ?, ?, ?, 'approved', ?, ?, ?)
            ''', (country_val, section, old_value, new_value, comment, timestamp, rationale))
            approved_items.append({
                "item_id": item_id, "country": country_val, "section": section,
                "new_value": new_value, "source_url": source_url, "source_hash": source_hash,
                "source_paragraph": source_paragraph, "confidence": confidence,
                "source_snapshot_id": source_snapshot_id,
                "reviewer_assignee": "", "reviewer_rationale": rationale, "reviewer_comment": comment,
                "reviewed_at": timestamp, "effective_date": resolved_effective_date,
                "version_number": version_number, "approval_reference": approval_reference,
            })

        conn.commit()
        conn.close()
        return {"approved": len(rows), "items": approved_items}

    def escalate_review_item(self, item_id, comment, assignee="", rationale=""):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT country, section, old_value, new_value
            FROM review_queue
            WHERE id=? AND status IN ('pending', 'escalated')
        """, (item_id,))
        item = c.fetchone()
        if not item:
            conn.close()
            return None

        country, section, old_value, new_value = item
        timestamp = self._now()
        c.execute("""
            UPDATE review_queue
            SET status='escalated', reviewed_at=?, reviewer_comment=?, reviewer_assignee=?, reviewer_rationale=?
            WHERE id=?
        """, (timestamp, comment, assignee, rationale, item_id))
        c.execute('''
            INSERT INTO audit_log
            (action, country, section, old_value, new_value, decision, reviewer_comment, timestamp, reviewer_assignee, reviewer_rationale)
            VALUES ('REVIEW', ?, ?, ?, ?, 'escalated', ?, ?, ?, ?)
        ''', (country, section, old_value, new_value, comment, timestamp, assignee, rationale))

        conn.commit()
        conn.close()
        return {"country": country, "section": section, "status": "escalated", "reviewed_at": timestamp}
