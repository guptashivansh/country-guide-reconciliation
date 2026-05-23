import sqlite3
from datetime import datetime


class ProvenanceRepository:
    def __init__(self, db_path):
        self.db_path = db_path

    def connect(self):
        return sqlite3.connect(self.db_path)

    def initialize_schema(self):
        conn = self.connect()
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS rule_provenance (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                country              TEXT NOT NULL,
                section              TEXT NOT NULL,
                rule_value           TEXT,
                -- foreign keys to existing tables (nullable — denormalized for durability)
                review_queue_id      INTEGER,
                source_snapshot_id   INTEGER,
                ingestion_job_id     INTEGER,
                -- denormalized extraction context
                source_url           TEXT,
                source_hash          TEXT,
                source_fragment      TEXT,
                extraction_confidence REAL,
                parser_version       TEXT,
                -- reviewer context
                reviewer_action      TEXT,    -- 'approved' | 'bulk_approved' | 'seeded'
                reviewer_assignee    TEXT,
                reviewer_rationale   TEXT,
                reviewer_comment     TEXT,
                -- timestamps
                crawled_at           TEXT,
                extracted_at         TEXT,
                reviewed_at          TEXT,
                created_at           TEXT NOT NULL
            )
        """)

        c.execute("CREATE INDEX IF NOT EXISTS idx_rp_country_section ON rule_provenance(country, section)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rp_review_queue ON rule_provenance(review_queue_id)")

        # Add current_provenance_id to country_guide if not present
        c.execute("PRAGMA table_info(country_guide)")
        cg_cols = {row[1] for row in c.fetchall()}
        if "current_provenance_id" not in cg_cols:
            c.execute("ALTER TABLE country_guide ADD COLUMN current_provenance_id INTEGER")

        conn.commit()
        conn.close()

    def write(self, country, section, rule_value, review_queue_id=None, source_snapshot_id=None,
              ingestion_job_id=None, source_url=None, source_hash=None, source_fragment=None,
              extraction_confidence=None, parser_version=None, reviewer_action=None,
              reviewer_assignee=None, reviewer_rationale=None, reviewer_comment=None,
              crawled_at=None, extracted_at=None, reviewed_at=None):
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            INSERT INTO rule_provenance
            (country, section, rule_value, review_queue_id, source_snapshot_id, ingestion_job_id,
             source_url, source_hash, source_fragment, extraction_confidence, parser_version,
             reviewer_action, reviewer_assignee, reviewer_rationale, reviewer_comment,
             crawled_at, extracted_at, reviewed_at, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (country, section, rule_value, review_queue_id, source_snapshot_id, ingestion_job_id,
              source_url, source_hash, source_fragment, extraction_confidence, parser_version,
              reviewer_action, reviewer_assignee, reviewer_rationale, reviewer_comment,
              crawled_at, extracted_at, reviewed_at, datetime.now().isoformat()))
        provenance_id = c.lastrowid
        conn.commit()
        conn.close()
        return provenance_id

    def set_current(self, country, section, provenance_id):
        conn = self.connect()
        c = conn.cursor()
        c.execute(
            "UPDATE country_guide SET current_provenance_id=? WHERE country=? AND section=?",
            (provenance_id, country, section),
        )
        conn.commit()
        conn.close()

    def get_current_chain(self, country, section):
        """Single query — full provenance chain for the current rule value."""
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT
                rp.id, rp.country, rp.section, rp.rule_value,
                rp.review_queue_id, rp.source_snapshot_id, rp.ingestion_job_id,
                rp.source_url, rp.source_hash, rp.source_fragment,
                rp.extraction_confidence, rp.parser_version,
                rp.reviewer_action, rp.reviewer_assignee, rp.reviewer_rationale, rp.reviewer_comment,
                rp.crawled_at, rp.extracted_at, rp.reviewed_at, rp.created_at,
                cg.last_updated,
                ss.content_hash AS snapshot_hash, ss.captured_at, ss.extraction_status,
                ij.source_url AS job_url, ij.state AS job_state,
                ij.queued_at, ij.fetched_at, ij.reconciled_at, ij.failed_at
            FROM rule_provenance rp
            JOIN country_guide cg
                ON cg.country = rp.country AND cg.section = rp.section
                AND cg.current_provenance_id = rp.id
            LEFT JOIN source_snapshots ss ON ss.id = rp.source_snapshot_id
            LEFT JOIN ingestion_jobs ij ON ij.id = rp.ingestion_job_id
            WHERE rp.country = ? AND rp.section = ?
        """, (country, section))
        row = c.fetchone()
        conn.close()
        return _row_to_chain(row) if row else None

    def get_history(self, country, section):
        """All historical provenance records for a rule, newest first."""
        conn = self.connect()
        c = conn.cursor()
        c.execute("""
            SELECT id, rule_value, reviewer_action, reviewer_assignee,
                   reviewer_rationale, source_url, extraction_confidence,
                   parser_version, reviewed_at, created_at
            FROM rule_provenance
            WHERE country = ? AND section = ?
            ORDER BY id DESC
        """, (country, section))
        rows = c.fetchall()
        conn.close()
        return [
            {
                "provenance_id": r[0],
                "rule_value": r[1],
                "reviewer_action": r[2],
                "reviewer_assignee": r[3],
                "reviewer_rationale": r[4],
                "source_url": r[5],
                "extraction_confidence": r[6],
                "parser_version": r[7],
                "reviewed_at": r[8],
                "created_at": r[9],
            }
            for r in rows
        ]

    def resolve_ingestion_job_id(self, source_snapshot_id):
        """Find the ingestion job that produced a given snapshot."""
        if not source_snapshot_id:
            return None
        conn = self.connect()
        c = conn.cursor()
        c.execute(
            "SELECT id, extracted_at, queued_at FROM ingestion_jobs WHERE source_snapshot_id=? ORDER BY id DESC LIMIT 1",
            (source_snapshot_id,),
        )
        row = c.fetchone()
        conn.close()
        return {"id": row[0], "extracted_at": row[1], "queued_at": row[2]} if row else None


def _row_to_chain(row):
    (pid, country, section, rule_value,
     rq_id, ss_id, ij_id,
     source_url, source_hash, source_fragment,
     confidence, p_version,
     action, assignee, rationale, comment,
     crawled_at, extracted_at, reviewed_at, created_at,
     last_updated,
     snap_hash, captured_at, extraction_status,
     job_url, job_state, queued_at, fetched_at, reconciled_at, failed_at) = row

    return {
        "provenance_id": pid,
        "country": country,
        "section": section,
        "chain": {
            "canonical_rule": {
                "country": country,
                "section": section,
                "value": rule_value,
                "last_updated": last_updated,
            },
            "reviewer_action": {
                "action": action,
                "assignee": assignee,
                "rationale": rationale,
                "comment": comment,
                "reviewed_at": reviewed_at,
            },
            "extraction": {
                "confidence": confidence,
                "parser_version": p_version,
                "source_fragment": source_fragment,
                "source_hash": source_hash,
                "extracted_at": extracted_at,
            },
            "source_snapshot": {
                "snapshot_id": ss_id,
                "content_hash": snap_hash,
                "captured_at": captured_at,
                "extraction_status": extraction_status,
            } if ss_id else None,
            "crawl_event": {
                "ingestion_job_id": ij_id,
                "source_url": job_url or source_url,
                "state": job_state,
                "queued_at": queued_at,
                "fetched_at": fetched_at,
                "reconciled_at": reconciled_at,
                "failed_at": failed_at,
            } if ij_id else None,
            "source_url": source_url,
        },
    }
