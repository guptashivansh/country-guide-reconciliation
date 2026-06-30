from datetime import datetime

from app.utils.db import Database


class SourceSnapshotRepository:
    def __init__(self, db):
        if isinstance(db, str):
            db = Database(db)
        self.db = db

    def connect(self):
        return self.db.connect()

    def initialize_schema(self):
        conn = self.connect()
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS source_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_url TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                extraction_status TEXT NOT NULL
            )
        ''')
        columns = self.db.get_table_columns(conn, "source_snapshots")
        if "extracted_rules_json" not in columns:
            c.execute("ALTER TABLE source_snapshots ADD COLUMN extracted_rules_json TEXT")
        conn.commit()
        conn.close()

    def create_snapshot(self, source_url, raw_text, content_hash, extraction_status="pending"):
        conn = self.connect()
        c = conn.cursor()
        c.execute('''
            INSERT INTO source_snapshots
            (source_url, raw_text, content_hash, captured_at, extraction_status)
            VALUES (?, ?, ?, ?, ?)
        ''', (source_url, raw_text, content_hash, datetime.now().isoformat(), extraction_status))
        snapshot_id = c.lastrowid
        conn.commit()
        conn.close()
        return snapshot_id

    def update_extraction_status(self, snapshot_id, extraction_status, extracted_rules_json=None):
        conn = self.connect()
        c = conn.cursor()
        if extracted_rules_json is not None:
            c.execute(
                "UPDATE source_snapshots SET extraction_status=?, extracted_rules_json=? WHERE id=?",
                (extraction_status, extracted_rules_json, snapshot_id),
            )
        else:
            c.execute(
                "UPDATE source_snapshots SET extraction_status=? WHERE id=?",
                (extraction_status, snapshot_id),
            )
        conn.commit()
        conn.close()

    def get_snapshot(self, snapshot_id):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT id, source_url, raw_text, content_hash, captured_at, extraction_status, extracted_rules_json
            FROM source_snapshots
            WHERE id=?
        """, (snapshot_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_dict(row)

    def get_latest_by_source_url(self, source_url):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT id, source_url, raw_text, content_hash, captured_at, extraction_status, extracted_rules_json
            FROM source_snapshots
            WHERE source_url=?
            ORDER BY id DESC
            LIMIT 1
        """, (source_url,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_dict(row)

    @staticmethod
    def _row_to_dict(row):
        return {
            "id": row[0],
            "source_url": row[1],
            "raw_text": row[2],
            "content_hash": row[3],
            "captured_at": row[4],
            "extraction_status": row[5],
            "extracted_rules_json": row[6] if len(row) > 6 else None,
        }
