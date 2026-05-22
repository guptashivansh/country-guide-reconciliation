import sqlite3
from datetime import datetime


class SourceSnapshotRepository:
    def __init__(self, db_path):
        self.db_path = db_path

    def connect(self):
        return sqlite3.connect(self.db_path)

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

    def update_extraction_status(self, snapshot_id, extraction_status):
        conn = self.connect()
        c = conn.cursor()
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
            SELECT id, source_url, raw_text, content_hash, captured_at, extraction_status
            FROM source_snapshots
            WHERE id=?
        """, (snapshot_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0],
            "source_url": row[1],
            "raw_text": row[2],
            "content_hash": row[3],
            "captured_at": row[4],
            "extraction_status": row[5],
        }
