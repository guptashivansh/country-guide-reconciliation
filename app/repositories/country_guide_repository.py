import sqlite3
from datetime import datetime


class CountryGuideRepository:
    def __init__(self, db_path):
        self.db_path = db_path

    def connect(self):
        return sqlite3.connect(self.db_path)

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

        c.execute("PRAGMA table_info(review_queue)")
        review_columns = {row[1] for row in c.fetchall()}
        if "source_hash" not in review_columns:
            c.execute("ALTER TABLE review_queue ADD COLUMN source_hash TEXT")
        if "source_snapshot_id" not in review_columns:
            c.execute("ALTER TABLE review_queue ADD COLUMN source_snapshot_id INTEGER")

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
        for country, section, value, url, source_hash in initial_data:
            c.execute('''
                INSERT OR IGNORE INTO country_guide (country, section, value, source_url, source_hash, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (country, section, value, url, source_hash, datetime.now().isoformat()))

        conn.commit()
        conn.close()

    def list_country_guide_entries(self):
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT country, section, value, source_url, last_updated FROM country_guide ORDER BY country, section")
        rows = c.fetchall()
        conn.close()
        return [{
            "country": r[0], "section": r[1], "value": r[2],
            "source_url": r[3], "last_updated": r[4]
        } for r in rows]

    def list_pending_review_items(self):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT id, country, section, old_value, new_value, severity, confidence, source_url, source_paragraph, created_at, source_snapshot_id
            FROM review_queue WHERE status='pending'
            ORDER BY
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
            "reviewer_comment": r[7], "timestamp": r[8]
        } for r in rows]

    def get_current_value(self, country, section):
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT value FROM country_guide WHERE country=? AND section=?", (country, section))
        row = c.fetchone()
        conn.close()
        return row[0] if row else "Not previously recorded"

    def pending_review_exists(self, country, section):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT id FROM review_queue
            WHERE country=? AND section=? AND status='pending'
        """, (country, section))
        exists = c.fetchone() is not None
        conn.close()
        return exists

    def enqueue_review_item(self, country, section, old_value, new_value, severity, confidence, source_url, source_paragraph, source_hash, source_snapshot_id):
        conn = self.connect()
        c = conn.cursor()
        c.execute('''
            INSERT INTO review_queue
            (country, section, old_value, new_value, severity, confidence, source_url, source_paragraph, status, created_at, source_hash, source_snapshot_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
        ''', (country, section, old_value, new_value, severity, confidence, source_url, source_paragraph, datetime.now().isoformat(), source_hash, source_snapshot_id))
        conn.commit()
        conn.close()

    def approve_pending_review_item(self, item_id, comment):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT country, section, old_value, new_value, source_url, source_hash
            FROM review_queue
            WHERE id=? AND status='pending'
        """, (item_id,))
        item = c.fetchone()
        if not item:
            conn.close()
            return None

        country, section, old_value, new_value, source_url, source_hash = item
        timestamp = datetime.now().isoformat()
        c.execute('''
            INSERT INTO country_guide (country, section, value, source_url, source_hash, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(country, section) DO UPDATE SET
                value=excluded.value,
                source_url=excluded.source_url,
                source_hash=excluded.source_hash,
                last_updated=excluded.last_updated
        ''', (country, section, new_value, source_url, source_hash, timestamp))
        c.execute("UPDATE review_queue SET status='approved', reviewed_at=?, reviewer_comment=? WHERE id=?",
                  (timestamp, comment, item_id))
        c.execute('''
            INSERT INTO audit_log (action, country, section, old_value, new_value, decision, reviewer_comment, timestamp)
            VALUES ('REVIEW', ?, ?, ?, ?, 'approved', ?, ?)
        ''', (country, section, old_value, new_value, comment, timestamp))

        conn.commit()
        conn.close()
        return {"country": country, "section": section}

    def reject_pending_review_item(self, item_id, comment):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT country, section, old_value, new_value
            FROM review_queue
            WHERE id=? AND status='pending'
        """, (item_id,))
        item = c.fetchone()
        if not item:
            conn.close()
            return None

        country, section, old_value, new_value = item
        timestamp = datetime.now().isoformat()
        c.execute("UPDATE review_queue SET status='rejected', reviewed_at=?, reviewer_comment=? WHERE id=?",
                  (timestamp, comment, item_id))
        c.execute('''
            INSERT INTO audit_log (action, country, section, old_value, new_value, decision, reviewer_comment, timestamp)
            VALUES ('REVIEW', ?, ?, ?, ?, 'rejected', ?, ?)
        ''', (country, section, old_value, new_value, comment, timestamp))

        conn.commit()
        conn.close()
        return {"country": country, "section": section}
