"""
Read-only DB queries that feed the drift detector.
All methods return plain dicts / lists of dicts — no ORM objects.
"""

from typing import Dict, List, Optional

from app.utils.db import Database


class DriftRepository:
    def __init__(self, db):
        if isinstance(db, str):
            db = Database(db)
        self.db = db

    def _connect(self):
        return self.db.dict_connect()

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

    def get_coverage_scores(self, core_sections: List[str]) -> Dict[str, dict]:
        """Compute coverage scores for all countries against core sections.

        Returns {country: {total, covered, missing, pct, has_provenance, sections}}.
        """
        if not core_sections:
            return {}
        with self._connect() as conn:
            guide_countries = {r["country"] for r in conn.execute(
                "SELECT DISTINCT country FROM country_guide"
            ).fetchall()}
            try:
                registry_countries = {r["name"] for r in conn.execute(
                    "SELECT name FROM source_countries WHERE is_active = 1"
                ).fetchall()}
            except Exception:
                registry_countries = set()
            countries = sorted(guide_countries | registry_countries)

            placeholders = ",".join("?" * len(core_sections))
            rows = conn.execute(
                f"SELECT country, section FROM country_guide WHERE section IN ({placeholders})",
                core_sections,
            ).fetchall()
            published = {}
            for r in rows:
                published.setdefault(r["country"], set()).add(r["section"])

            has_prov = {}
            try:
                prov_rows = conn.execute(
                    f"""SELECT rp.country, rp.section
                        FROM rule_provenance rp
                        JOIN country_guide cg ON cg.country = rp.country
                            AND cg.section = rp.section
                        WHERE rp.section IN ({placeholders})""",
                    core_sections,
                ).fetchall()
                for r in prov_rows:
                    has_prov.setdefault(r["country"], set()).add(r["section"])
            except Exception:
                pass

            total = len(core_sections)
            core_set = set(core_sections)
            result = {}
            for country in countries:
                pub = published.get(country, set())
                prov = has_prov.get(country, set())
                covered = pub & core_set
                verified = covered & prov
                missing = sorted(core_set - covered)
                result[country] = {
                    "total": total,
                    "covered": len(covered),
                    "verified": len(verified),
                    "missing": missing,
                    "pct": round(len(covered) / total * 100) if total else 0,
                    "verified_pct": round(len(verified) / total * 100) if total else 0,
                }
            return result

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
                    SELECT rp.section, rp.id, rp.source_url, rp.reviewed_at,
                           rp.crawled_at, rp.extraction_confidence,
                           rp.parser_version, rp.reviewer_action,
                           rp.created_at
                    FROM rule_provenance rp
                    INNER JOIN (
                        SELECT section, MAX(created_at) AS max_created
                        FROM rule_provenance
                        WHERE country = ? AND section NOT IN ({placeholders})
                        GROUP BY section
                    ) latest ON rp.section = latest.section
                              AND rp.created_at = latest.max_created
                    WHERE rp.country = ? AND rp.section NOT IN ({placeholders})
                    """,
                    (country, *linked, country, *linked),
                ).fetchall()
            else:
                fallback_rows = conn.execute(
                    """
                    SELECT rp.section, rp.id, rp.source_url, rp.reviewed_at,
                           rp.crawled_at, rp.extraction_confidence,
                           rp.parser_version, rp.reviewer_action,
                           rp.created_at
                    FROM rule_provenance rp
                    INNER JOIN (
                        SELECT section, MAX(created_at) AS max_created
                        FROM rule_provenance
                        WHERE country = ?
                        GROUP BY section
                    ) latest ON rp.section = latest.section
                              AND rp.created_at = latest.max_created
                    WHERE rp.country = ?
                    """,
                    (country, country),
                ).fetchall()
            for r in fallback_rows:
                result[r["section"]] = dict(r)

            return result
