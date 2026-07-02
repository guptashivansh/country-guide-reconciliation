from datetime import datetime

from app.utils.db import Database


class IngestionJobRepository:
    VALID_STATES = {"queued", "fetched", "normalized", "extracted", "reconciled", "failed"}

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
            CREATE TABLE IF NOT EXISTS ingestion_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_url TEXT NOT NULL,
                state TEXT NOT NULL,
                queued_at TEXT,
                fetched_at TEXT,
                normalized_at TEXT,
                extracted_at TEXT,
                reconciled_at TEXT,
                failed_at TEXT,
                failure_reason TEXT,
                source_snapshot_id INTEGER,
                country TEXT
            )
        ''')
        columns = self.db.get_table_columns(conn, "ingestion_jobs")
        if "country" not in columns:
            c.execute("ALTER TABLE ingestion_jobs ADD COLUMN country TEXT")
        if "rules_extracted" not in columns:
            c.execute("ALTER TABLE ingestion_jobs ADD COLUMN rules_extracted INTEGER")
        conn.commit()
        conn.close()

    def create_job(self, source_url, country=None):
        conn = self.connect()
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute('''
            INSERT INTO ingestion_jobs (source_url, state, queued_at, country)
            VALUES (?, 'queued', ?, ?)
        ''', (source_url, now, country))
        job_id = c.lastrowid
        conn.commit()
        conn.close()
        return job_id

    def get_job(self, job_id):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT id, source_url, state, queued_at, fetched_at, normalized_at, extracted_at,
                   reconciled_at, failed_at, failure_reason, source_snapshot_id, country,
                   rules_extracted
            FROM ingestion_jobs WHERE id = ?
        """, (job_id,))
        r = c.fetchone()
        conn.close()
        if not r:
            return None
        return {
            "id": r[0], "source_url": r[1], "state": r[2],
            "queued_at": r[3], "fetched_at": r[4], "normalized_at": r[5],
            "extracted_at": r[6], "reconciled_at": r[7], "failed_at": r[8],
            "failure_reason": r[9], "source_snapshot_id": r[10], "country": r[11],
            "rules_extracted": r[12],
        }

    def transition_job(self, job_id, state, failure_reason=None, source_snapshot_id=None, rules_extracted=None):
        if state not in self.VALID_STATES:
            raise ValueError(f"Unsupported ingestion job state: {state}")

        timestamp_column = f"{state}_at"
        values = [state, datetime.now().isoformat()]
        assignments = ["state=?", f"{timestamp_column}=?"]

        if failure_reason is not None:
            assignments.append("failure_reason=?")
            values.append(failure_reason)

        if source_snapshot_id is not None:
            assignments.append("source_snapshot_id=?")
            values.append(source_snapshot_id)

        if rules_extracted is not None:
            assignments.append("rules_extracted=?")
            values.append(rules_extracted)

        values.append(job_id)

        conn = self.connect()
        c = conn.cursor()
        c.execute(
            f"UPDATE ingestion_jobs SET {', '.join(assignments)} WHERE id=?",
            tuple(values),
        )
        conn.commit()
        conn.close()

    def list_recent_jobs(self, limit=200):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT id, source_url, state, queued_at, fetched_at, normalized_at, extracted_at,
                   reconciled_at, failed_at, failure_reason, source_snapshot_id, country,
                   rules_extracted
            FROM ingestion_jobs
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        rows = c.fetchall()
        conn.close()
        return [{
            "id": r[0],
            "source_url": r[1],
            "state": r[2],
            "queued_at": r[3],
            "fetched_at": r[4],
            "normalized_at": r[5],
            "extracted_at": r[6],
            "reconciled_at": r[7],
            "failed_at": r[8],
            "failure_reason": r[9],
            "source_snapshot_id": r[10],
            "country": r[11],
            "rules_extracted": r[12],
        } for r in rows]

    def last_successful_sync_time(self):
        conn = self.connect()
        c = conn.cursor()
        c.execute(
            "SELECT MAX(reconciled_at) FROM ingestion_jobs WHERE state = 'reconciled'"
        )
        row = c.fetchone()
        conn.close()
        return row[0] if row else None
