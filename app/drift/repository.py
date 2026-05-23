"""
Read-only DB queries that feed the drift detector.
All methods return plain dicts / lists of dicts — no ORM objects.
"""

import sqlite3
from typing import List, Optional


class DriftRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── countries ─────────────────────────────────────────────────────────────

    def list_countries(self) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT country FROM country_guide ORDER BY country"
            ).fetchall()
            return [r["country"] for r in rows]

    # ── canonical rules (live guide) ──────────────────────────────────────────

    def get_canonical_entries(self, country: str) -> List[dict]:
        """All live guide entries for a country, keyed by section."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT section, value, last_updated, current_provenance_id, country "
                "FROM country_guide WHERE country = ?",
                (country,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_canonical_entry(self, country: str, section: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT section, value, last_updated, current_provenance_id, country "
                "FROM country_guide WHERE country = ? AND section = ?",
                (country, section),
            ).fetchone()
            return dict(row) if row else None

    # ── pending / escalated items ─────────────────────────────────────────────

    def get_pending_items(self, country: str) -> List[dict]:
        """All pending or escalated review_queue items for a country."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, country, section, old_value, new_value,
                       status, severity, confidence, created_at
                FROM review_queue
                WHERE country = ? AND status IN ('pending', 'escalated')
                ORDER BY created_at ASC
                """,
                (country,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ── provenance summaries ──────────────────────────────────────────────────

    def get_provenance_for_entry(self, country: str, section: str) -> Optional[dict]:
        """Most recent provenance record for a canonical rule."""
        with self._connect() as conn:
            # Try to follow current_provenance_id first
            row = conn.execute(
                """
                SELECT rp.id, rp.source_url, rp.reviewed_at, rp.crawled_at,
                       rp.extraction_confidence, rp.parser_version, rp.reviewer_action
                FROM rule_provenance rp
                JOIN country_guide cg
                    ON cg.country = rp.country AND cg.section = rp.section
                    AND cg.current_provenance_id = rp.id
                WHERE rp.country = ? AND rp.section = ?
                """,
                (country, section),
            ).fetchone()
            if row:
                return dict(row)

            # Fall back to most recent provenance for this country+section
            row = conn.execute(
                """
                SELECT id, source_url, reviewed_at, crawled_at,
                       extraction_confidence, parser_version, reviewer_action
                FROM rule_provenance
                WHERE country = ? AND section = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (country, section),
            ).fetchone()
            return dict(row) if row else None

    def get_all_provenances(self, country: str) -> dict:
        """Returns {section: provenance_dict} for all sections of a country."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT rp.section, rp.id, rp.source_url, rp.reviewed_at,
                       rp.crawled_at, rp.extraction_confidence, rp.parser_version,
                       rp.reviewer_action
                FROM rule_provenance rp
                JOIN country_guide cg
                    ON cg.country = rp.country AND cg.section = rp.section
                    AND cg.current_provenance_id = rp.id
                WHERE rp.country = ?
                """,
                (country,),
            ).fetchall()
            result = {r["section"]: dict(r) for r in rows}

            # For sections without a current_provenance_id link, grab latest
            linked = set(result.keys())
            if linked:
                placeholders = ",".join("?" * len(linked))
                fallback_rows = conn.execute(
                    f"""
                    SELECT section, id, source_url, reviewed_at, crawled_at,
                           extraction_confidence, parser_version, reviewer_action,
                           MAX(created_at) AS created_at
                    FROM rule_provenance
                    WHERE country = ? AND section NOT IN ({placeholders})
                    GROUP BY section
                    """,
                    (country, *linked),
                ).fetchall()
            else:
                fallback_rows = conn.execute(
                    """
                    SELECT section, id, source_url, reviewed_at, crawled_at,
                           extraction_confidence, parser_version, reviewer_action,
                           MAX(created_at) AS created_at
                    FROM rule_provenance
                    WHERE country = ?
                    GROUP BY section
                    """,
                    (country,),
                ).fetchall()
            for r in fallback_rows:
                result[r["section"]] = dict(r)

            return result
