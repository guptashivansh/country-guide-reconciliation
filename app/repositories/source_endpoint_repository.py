from __future__ import annotations

import json
import logging
import os
import urllib.request

from app.models.source_endpoint import SourceEndpoint
from app.utils.db import Database

logger = logging.getLogger(__name__)

_DEFAULT_LOCAL_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "official-sources.json",
)


class TrustedSourceEndpointRepository:
    """DB-backed registry of official government source endpoints.

    On first call to initialize_schema(), creates the four registry tables
    (source_countries, source_authorities, source_endpoints, parser_registry).
    If the tables are empty, seeds them from a local JSON file (preferred)
    or a remote URL as fallback.
    """

    def __init__(self, db, json_url: str = "", json_path: str = ""):
        if isinstance(db, str):
            db = Database(db)
        self.db = db
        self.json_url = json_url
        self.json_path = json_path or _DEFAULT_LOCAL_JSON

    def initialize_schema(self):
        conn = self.db.connect()
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS source_countries (
                id TEXT PRIMARY KEY,
                iso_code TEXT NOT NULL,
                name TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS source_authorities (
                id TEXT PRIMARY KEY,
                country_id TEXT NOT NULL REFERENCES source_countries(id),
                name TEXT NOT NULL,
                authority_type TEXT,
                website_url TEXT,
                trust_level TEXT DEFAULT 'official',
                precedence_rank INTEGER DEFAULT 1,
                is_active INTEGER NOT NULL DEFAULT 1,
                notes TEXT,
                owner_team TEXT,
                owner_user_id TEXT,
                reviewer_group TEXT,
                escalation_required INTEGER DEFAULT 0,
                supports_replay INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS source_endpoints (
                id TEXT PRIMARY KEY,
                authority_id TEXT NOT NULL REFERENCES source_authorities(id),
                name TEXT,
                url TEXT NOT NULL,
                source_type TEXT DEFAULT 'html',
                content_language TEXT DEFAULT 'en',
                sections_covered TEXT DEFAULT '[]',
                authority_category TEXT,
                extraction_strategy TEXT DEFAULT 'html_readability',
                parser_key TEXT DEFAULT 'html_readability_v1',
                crawl_frequency TEXT DEFAULT 'monthly',
                change_detection_strategy TEXT DEFAULT 'semantic',
                requires_authentication INTEGER DEFAULT 0,
                is_javascript_heavy INTEGER DEFAULT 0,
                supports_incremental_diffs INTEGER DEFAULT 1,
                is_human_curated INTEGER DEFAULT 1,
                status TEXT DEFAULT 'active',
                last_crawled_at TEXT,
                last_successful_crawl_at TEXT,
                last_change_detected_at TEXT,
                owner_team TEXT,
                owner_user_id TEXT,
                reviewer_group TEXT,
                escalation_required INTEGER DEFAULT 0,
                supports_replay INTEGER DEFAULT 1,
                notes TEXT,
                parent_endpoint_id TEXT REFERENCES source_endpoints(id),
                created_at TEXT,
                updated_at TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS parser_registry (
                id TEXT PRIMARY KEY,
                parser_key TEXT NOT NULL,
                description TEXT,
                supported_source_types TEXT DEFAULT '[]',
                supported_countries TEXT DEFAULT '[]',
                parser_version TEXT DEFAULT '1.0.0',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS url_classifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                domain TEXT NOT NULL,
                classification TEXT NOT NULL,
                matched_authority TEXT,
                matched_country TEXT,
                notes TEXT,
                classified_by TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(url)
            )
        """)

        c.execute("CREATE INDEX IF NOT EXISTS idx_source_authorities_country ON source_authorities(country_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_source_endpoints_authority ON source_endpoints(authority_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_source_endpoints_status ON source_endpoints(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_url_classifications_domain ON url_classifications(domain)")

        try:
            c.execute("ALTER TABLE source_endpoints ADD COLUMN parent_endpoint_id TEXT REFERENCES source_endpoints(id)")
        except Exception:
            pass

        try:
            c.execute("ALTER TABLE source_endpoints ADD COLUMN consecutive_failures INTEGER DEFAULT 0")
        except Exception:
            pass

        conn.commit()

        c.execute("SELECT COUNT(*) FROM source_countries")
        if c.fetchone()[0] == 0:
            if self.json_path and os.path.isfile(self.json_path):
                logger.info("Source registry tables empty — seeding from local JSON: %s", self.json_path)
                self._seed_from_file(conn, self.json_path)
            elif self.json_url:
                logger.info("Source registry tables empty — seeding from remote JSON: %s", self.json_url)
                self._seed_from_url(conn, self.json_url)

        conn.close()

    def seed_from_url(self, url=None):
        conn = self.db.connect()
        self._seed_from_url(conn, url or self.json_url)
        conn.close()

    def reseed_from_file(self, path: str = ""):
        """Clear all registry tables and re-import from a local JSON file."""
        path = path or self.json_path
        conn = self.db.connect()
        c = conn.cursor()
        for table in ("source_endpoints", "source_authorities", "source_countries", "parser_registry"):
            c.execute(f"DELETE FROM {table}")
        conn.commit()
        self._seed_from_file(conn, path)
        conn.close()

    def _seed_from_file(self, conn, path: str):
        with open(path, "r") as f:
            data = json.load(f)
        self._seed_from_dict(conn, data)

    def _seed_from_url(self, conn, url: str):
        data = self._fetch_json(url)
        self._seed_from_dict(conn, data)

    def seed_from_dict(self, data: dict):
        conn = self.db.connect()
        self._seed_from_dict(conn, data)
        conn.close()

    def _seed_from_dict(self, conn, data: dict):
        c = conn.cursor()

        for country in data.get("countries", []):
            c.execute("""
                INSERT OR IGNORE INTO source_countries (id, iso_code, name, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                country["id"], country["iso_code"], country["name"],
                1 if country.get("is_active", True) else 0,
                country.get("created_at"), country.get("updated_at"),
            ))

        for auth in data.get("authorities", []):
            c.execute("""
                INSERT OR IGNORE INTO source_authorities
                (id, country_id, name, authority_type, website_url, trust_level,
                 precedence_rank, is_active, notes, owner_team, owner_user_id,
                 reviewer_group, escalation_required, supports_replay, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                auth["id"], auth["country_id"], auth["name"],
                auth.get("authority_type"), auth.get("website_url"),
                auth.get("trust_level", "official"),
                auth.get("precedence_rank", 1),
                1 if auth.get("is_active", True) else 0,
                auth.get("notes"),
                auth.get("owner_team"), auth.get("owner_user_id"),
                auth.get("reviewer_group"),
                1 if auth.get("escalation_required") else 0,
                1 if auth.get("supports_replay", True) else 0,
                auth.get("created_at"), auth.get("updated_at"),
            ))

        for ep in data.get("source_endpoints", []):
            c.execute("""
                INSERT OR IGNORE INTO source_endpoints
                (id, authority_id, name, url, source_type, content_language,
                 sections_covered, authority_category, extraction_strategy,
                 parser_key, crawl_frequency, change_detection_strategy,
                 requires_authentication, is_javascript_heavy,
                 supports_incremental_diffs, is_human_curated, status,
                 last_crawled_at, last_successful_crawl_at, last_change_detected_at,
                 owner_team, owner_user_id, reviewer_group,
                 escalation_required, supports_replay, notes,
                 parent_endpoint_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ep["id"], ep["authority_id"], ep.get("name"),
                ep["url"], ep.get("source_type", "html"),
                ep.get("content_language", "en"),
                json.dumps(ep.get("sections_covered", [])),
                ep.get("authority_category"),
                ep.get("extraction_strategy", "html_readability"),
                ep.get("parser_key", "html_readability_v1"),
                ep.get("crawl_frequency", "monthly"),
                ep.get("change_detection_strategy", "semantic"),
                1 if ep.get("requires_authentication") else 0,
                1 if ep.get("is_javascript_heavy") else 0,
                1 if ep.get("supports_incremental_diffs", True) else 0,
                1 if ep.get("is_human_curated", True) else 0,
                ep.get("status", "active"),
                ep.get("last_crawled_at"), ep.get("last_successful_crawl_at"),
                ep.get("last_change_detected_at"),
                ep.get("owner_team"), ep.get("owner_user_id"),
                ep.get("reviewer_group"),
                1 if ep.get("escalation_required") else 0,
                1 if ep.get("supports_replay", True) else 0,
                ep.get("notes"),
                ep.get("parent_endpoint_id"),
                ep.get("created_at"), ep.get("updated_at"),
            ))

        for parser in data.get("parser_registry", []):
            c.execute("""
                INSERT OR IGNORE INTO parser_registry
                (id, parser_key, description, supported_source_types,
                 supported_countries, parser_version, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                parser["id"], parser["parser_key"], parser.get("description"),
                json.dumps(parser.get("supported_source_types", [])),
                json.dumps(parser.get("supported_countries", [])),
                parser.get("parser_version", "1.0.0"),
                1 if parser.get("is_active", True) else 0,
                parser.get("created_at"),
            ))

        conn.commit()
        c.execute("SELECT COUNT(*) FROM source_countries")
        countries = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM source_endpoints")
        endpoints = c.fetchone()[0]
        logger.info("Source registry seeded", extra={"countries": countries, "endpoints": endpoints})

    def list_active_source_endpoints(self) -> list[SourceEndpoint]:
        conn = self.db.connect()
        c = conn.cursor()
        c.execute("""
            SELECT
                e.id, e.url, e.sections_covered, e.source_type, e.content_language,
                e.authority_category, e.extraction_strategy, e.parser_key,
                e.crawl_frequency, e.change_detection_strategy,
                e.requires_authentication, e.is_javascript_heavy,
                e.escalation_required, e.supports_replay, e.owner_team,
                e.notes, e.status, e.name,
                a.id, a.name, a.authority_type, a.website_url,
                a.trust_level, a.precedence_rank, a.escalation_required,
                a.supports_replay,
                sc.id, sc.iso_code, sc.name,
                e.parent_endpoint_id
            FROM source_endpoints e
            JOIN source_authorities a ON e.authority_id = a.id
            JOIN source_countries sc ON a.country_id = sc.id
            WHERE e.status IN ('active', 'suspended')
              AND a.is_active = 1
              AND sc.is_active = 1
            ORDER BY sc.name, a.precedence_rank, e.name
        """)
        rows = c.fetchall()
        conn.close()

        return [self._row_to_endpoint(r) for r in rows]

    def list_all_source_endpoints(self) -> list[SourceEndpoint]:
        conn = self.db.connect()
        c = conn.cursor()
        c.execute("""
            SELECT
                e.id, e.url, e.sections_covered, e.source_type, e.content_language,
                e.authority_category, e.extraction_strategy, e.parser_key,
                e.crawl_frequency, e.change_detection_strategy,
                e.requires_authentication, e.is_javascript_heavy,
                e.escalation_required, e.supports_replay, e.owner_team,
                e.notes, e.status, e.name,
                a.id, a.name, a.authority_type, a.website_url,
                a.trust_level, a.precedence_rank, a.escalation_required,
                a.supports_replay,
                sc.id, sc.iso_code, sc.name,
                e.parent_endpoint_id
            FROM source_endpoints e
            JOIN source_authorities a ON e.authority_id = a.id
            JOIN source_countries sc ON a.country_id = sc.id
            WHERE a.is_active = 1
              AND sc.is_active = 1
            ORDER BY sc.name, a.precedence_rank, e.name
        """)
        rows = c.fetchall()
        conn.close()

        return [self._row_to_endpoint(r) for r in rows]

    def list_endpoints_for_country(self, country_name: str) -> list[SourceEndpoint]:
        conn = self.db.connect()
        c = conn.cursor()
        c.execute("""
            SELECT
                e.id, e.url, e.sections_covered, e.source_type, e.content_language,
                e.authority_category, e.extraction_strategy, e.parser_key,
                e.crawl_frequency, e.change_detection_strategy,
                e.requires_authentication, e.is_javascript_heavy,
                e.escalation_required, e.supports_replay, e.owner_team,
                e.notes, e.status, e.name,
                a.id, a.name, a.authority_type, a.website_url,
                a.trust_level, a.precedence_rank, a.escalation_required,
                a.supports_replay,
                sc.id, sc.iso_code, sc.name,
                e.parent_endpoint_id
            FROM source_endpoints e
            JOIN source_authorities a ON e.authority_id = a.id
            JOIN source_countries sc ON a.country_id = sc.id
            WHERE sc.name = ? AND e.status IN ('active', 'suspended') AND a.is_active = 1
            ORDER BY a.precedence_rank, e.name
        """, (country_name,))
        rows = c.fetchall()
        conn.close()
        return [self._row_to_endpoint(r) for r in rows]

    def list_countries(self, include_inactive: bool = False) -> list[dict]:
        conn = self.db.connect()
        c = conn.cursor()
        where = "" if include_inactive else "WHERE sc.is_active = 1"
        c.execute(f"""
            SELECT sc.id, sc.iso_code, sc.name, sc.is_active,
                   COUNT(DISTINCT a.id) AS authority_count,
                   COUNT(DISTINCT e.id) AS endpoint_count
            FROM source_countries sc
            LEFT JOIN source_authorities a ON a.country_id = sc.id AND a.is_active = 1
            LEFT JOIN source_endpoints e ON e.authority_id = a.id AND e.status = 'active'
            {where}
            GROUP BY sc.id
            ORDER BY sc.name
        """)
        rows = c.fetchall()
        conn.close()
        return [{
            "id": r[0], "iso_code": r[1], "name": r[2], "is_active": bool(r[3]),
            "authority_count": r[4], "endpoint_count": r[5],
        } for r in rows]

    def list_authorities(self, country_id: str = None) -> list[dict]:
        conn = self.db.connect()
        c = conn.cursor()
        if country_id:
            c.execute("""
                SELECT a.id, a.country_id, a.name, a.authority_type, a.website_url,
                       a.trust_level, a.precedence_rank, a.is_active, a.notes,
                       a.owner_team, a.escalation_required, a.supports_replay,
                       sc.name AS country_name
                FROM source_authorities a
                JOIN source_countries sc ON a.country_id = sc.id
                WHERE a.country_id = ? AND a.is_active = 1
                ORDER BY a.precedence_rank
            """, (country_id,))
        else:
            c.execute("""
                SELECT a.id, a.country_id, a.name, a.authority_type, a.website_url,
                       a.trust_level, a.precedence_rank, a.is_active, a.notes,
                       a.owner_team, a.escalation_required, a.supports_replay,
                       sc.name AS country_name
                FROM source_authorities a
                JOIN source_countries sc ON a.country_id = sc.id
                WHERE a.is_active = 1
                ORDER BY sc.name, a.precedence_rank
            """)
        rows = c.fetchall()
        conn.close()
        return [{
            "id": r[0], "country_id": r[1], "name": r[2], "authority_type": r[3],
            "website_url": r[4], "trust_level": r[5], "precedence_rank": r[6],
            "is_active": bool(r[7]), "notes": r[8], "owner_team": r[9],
            "escalation_required": bool(r[10]), "supports_replay": bool(r[11]),
            "country_name": r[12],
        } for r in rows]

    def get_registry_stats(self) -> dict:
        conn = self.db.connect()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM source_countries WHERE is_active = 1")
        countries = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM source_authorities WHERE is_active = 1")
        authorities = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM source_endpoints WHERE status = 'active'")
        endpoints = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM parser_registry WHERE is_active = 1")
        parsers = c.fetchone()[0]
        conn.close()
        return {
            "countries": countries,
            "authorities": authorities,
            "endpoints": endpoints,
            "parsers": parsers,
        }

    # ── CRUD: Countries ────────────────────────────────────────────────────

    def create_country(self, data: dict) -> dict:
        import uuid
        from datetime import datetime
        conn = self.db.connect()
        c = conn.cursor()
        country_id = data.get("id") or f"c-{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        c.execute("""
            INSERT INTO source_countries (id, iso_code, name, is_active, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
        """, (country_id, data["iso_code"].upper(), data["name"], now, now))
        conn.commit()
        conn.close()
        return {"id": country_id, "created_at": now}

    def update_country(self, country_id: str, data: dict) -> dict:
        from datetime import datetime
        conn = self.db.connect()
        c = conn.cursor()
        now = datetime.now().isoformat()
        fields, vals = [], []
        for col in ("iso_code", "name", "is_active"):
            if col in data:
                fields.append(f"{col} = ?")
                vals.append(data[col])
        if not fields:
            conn.close()
            return {"id": country_id, "updated": False}
        fields.append("updated_at = ?")
        vals.append(now)
        vals.append(country_id)
        c.execute(f"UPDATE source_countries SET {', '.join(fields)} WHERE id = ?", vals)
        conn.commit()
        updated = c._cursor.rowcount if hasattr(c, '_cursor') else conn.total_changes if hasattr(conn, 'total_changes') else 1
        conn.close()
        return {"id": country_id, "updated": updated > 0, "updated_at": now}

    def delete_country(self, country_id: str) -> dict:
        from datetime import datetime
        conn = self.db.connect()
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute("UPDATE source_countries SET is_active = 0, updated_at = ? WHERE id = ?", (now, country_id))
        c.execute("UPDATE source_authorities SET is_active = 0, updated_at = ? WHERE country_id = ?", (now, country_id))
        c.execute("""
            UPDATE source_endpoints SET status = 'inactive', updated_at = ?
            WHERE authority_id IN (SELECT id FROM source_authorities WHERE country_id = ?)
        """, (now, country_id))
        conn.commit()
        conn.close()
        return {"id": country_id, "deactivated_at": now}

    # ── CRUD: Authorities ────────────────────────────────────────────────

    def create_authority(self, data: dict) -> dict:
        import uuid
        from datetime import datetime
        conn = self.db.connect()
        c = conn.cursor()
        auth_id = data.get("id") or f"a-{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        c.execute("""
            INSERT INTO source_authorities
            (id, country_id, name, authority_type, website_url, trust_level,
             precedence_rank, is_active, notes, owner_team, escalation_required,
             supports_replay, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
        """, (
            auth_id, data["country_id"], data["name"],
            data.get("authority_type", "government_ministry"),
            data.get("website_url", ""),
            data.get("trust_level", "official"),
            data.get("precedence_rank", 1),
            data.get("notes", ""),
            data.get("owner_team", ""),
            1 if data.get("escalation_required") else 0,
            1 if data.get("supports_replay", True) else 0,
            now, now,
        ))
        conn.commit()
        conn.close()
        return {"id": auth_id, "created_at": now}

    def update_authority(self, authority_id: str, data: dict) -> dict:
        from datetime import datetime
        conn = self.db.connect()
        c = conn.cursor()
        now = datetime.now().isoformat()
        allowed = ("name", "authority_type", "website_url", "trust_level",
                    "precedence_rank", "is_active", "notes", "owner_team",
                    "escalation_required", "supports_replay")
        fields, vals = [], []
        for col in allowed:
            if col in data:
                fields.append(f"{col} = ?")
                val = data[col]
                if col in ("is_active", "escalation_required", "supports_replay"):
                    val = 1 if val else 0
                vals.append(val)
        if not fields:
            conn.close()
            return {"id": authority_id, "updated": False}
        fields.append("updated_at = ?")
        vals.append(now)
        vals.append(authority_id)
        c.execute(f"UPDATE source_authorities SET {', '.join(fields)} WHERE id = ?", vals)
        conn.commit()
        conn.close()
        return {"id": authority_id, "updated": True, "updated_at": now}

    def delete_authority(self, authority_id: str) -> dict:
        from datetime import datetime
        conn = self.db.connect()
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute("UPDATE source_authorities SET is_active = 0, updated_at = ? WHERE id = ?", (now, authority_id))
        c.execute("UPDATE source_endpoints SET status = 'inactive', updated_at = ? WHERE authority_id = ?", (now, authority_id))
        conn.commit()
        conn.close()
        return {"id": authority_id, "deactivated_at": now}

    # ── CRUD: Endpoints ──────────────────────────────────────────────────

    def create_endpoint(self, data: dict) -> dict:
        import uuid
        from datetime import datetime

        conn = self.db.connect()
        c = conn.cursor()
        endpoint_id = data.get("id") or f"ep-{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        c.execute("""
            INSERT INTO source_endpoints
            (id, authority_id, name, url, source_type, content_language,
             sections_covered, authority_category, extraction_strategy,
             parser_key, crawl_frequency, change_detection_strategy,
             requires_authentication, is_javascript_heavy,
             supports_incremental_diffs, is_human_curated, status,
             owner_team, owner_user_id, reviewer_group,
             escalation_required, supports_replay, notes,
             parent_endpoint_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            endpoint_id,
            data["authority_id"],
            data.get("name", ""),
            data["url"],
            data.get("source_type", "html"),
            data.get("content_language", "en"),
            json.dumps(data.get("sections_covered", [])),
            data.get("authority_category", ""),
            data.get("extraction_strategy", "html_readability"),
            data.get("parser_key", "html_readability_v1"),
            data.get("crawl_frequency", "monthly"),
            data.get("change_detection_strategy", "semantic"),
            1 if data.get("requires_authentication") else 0,
            1 if data.get("is_javascript_heavy") else 0,
            1 if data.get("supports_incremental_diffs", True) else 0,
            1 if data.get("is_human_curated", True) else 0,
            data.get("status", "active"),
            data.get("owner_team", ""),
            data.get("owner_user_id", ""),
            data.get("reviewer_group", ""),
            1 if data.get("escalation_required") else 0,
            1 if data.get("supports_replay", True) else 0,
            data.get("notes", ""),
            data.get("parent_endpoint_id"),
            now, now,
        ))
        conn.commit()
        conn.close()
        return {"id": endpoint_id, "created_at": now}

    def update_endpoint(self, endpoint_id: str, data: dict) -> dict:
        from datetime import datetime
        conn = self.db.connect()
        c = conn.cursor()
        now = datetime.now().isoformat()
        allowed = (
            "name", "url", "source_type", "content_language", "sections_covered",
            "authority_category", "extraction_strategy", "parser_key",
            "crawl_frequency", "change_detection_strategy",
            "requires_authentication", "is_javascript_heavy",
            "supports_incremental_diffs", "is_human_curated", "status",
            "owner_team", "owner_user_id", "reviewer_group",
            "escalation_required", "supports_replay", "notes",
            "parent_endpoint_id",
        )
        fields, vals = [], []
        for col in allowed:
            if col in data:
                val = data[col]
                if col == "sections_covered" and isinstance(val, list):
                    val = json.dumps(val)
                elif col in ("requires_authentication", "is_javascript_heavy",
                             "supports_incremental_diffs", "is_human_curated",
                             "escalation_required", "supports_replay"):
                    val = 1 if val else 0
                fields.append(f"{col} = ?")
                vals.append(val)
        if not fields:
            conn.close()
            return {"id": endpoint_id, "updated": False}
        fields.append("updated_at = ?")
        vals.append(now)
        vals.append(endpoint_id)
        c.execute(f"UPDATE source_endpoints SET {', '.join(fields)} WHERE id = ?", vals)
        conn.commit()
        conn.close()
        return {"id": endpoint_id, "updated": True, "updated_at": now}

    def delete_endpoint(self, endpoint_id: str) -> dict:
        from datetime import datetime
        conn = self.db.connect()
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute("UPDATE source_endpoints SET status = 'inactive', updated_at = ? WHERE id = ?", (now, endpoint_id))
        conn.commit()
        conn.close()
        return {"id": endpoint_id, "deactivated_at": now}

    def update_crawl_timestamp(self, endpoint_id: str, success: bool):
        conn = self.db.connect()
        c = conn.cursor()
        from datetime import datetime
        now = datetime.now().isoformat()
        if success:
            c.execute("""
                UPDATE source_endpoints
                SET last_crawled_at = ?, last_successful_crawl_at = ?,
                    consecutive_failures = 0
                WHERE id = ?
            """, (now, now, endpoint_id))
        else:
            c.execute("""
                UPDATE source_endpoints
                SET last_crawled_at = ?,
                    consecutive_failures = COALESCE(consecutive_failures, 0) + 1
                WHERE id = ?
            """, (now, endpoint_id))
            c.execute("""
                UPDATE source_endpoints
                SET status = 'suspended'
                WHERE id = ? AND consecutive_failures >= 3 AND status = 'active'
            """, (endpoint_id,))
            if c.rowcount > 0:
                logger.warning("Auto-suspended endpoint %s after 3+ consecutive failures", endpoint_id)
        conn.commit()
        conn.close()

    def verify_url(self, url: str) -> dict:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.lower().lstrip("www.")

        conn = self.db.connect()
        c = conn.cursor()

        c.execute("""
            SELECT e.id, e.url, e.name, e.sections_covered,
                   a.name, a.authority_type, a.website_url, a.trust_level,
                   a.escalation_required, a.supports_replay,
                   sc.name, sc.iso_code
            FROM source_endpoints e
            JOIN source_authorities a ON e.authority_id = a.id
            JOIN source_countries sc ON a.country_id = sc.id
            WHERE e.url = ? AND e.status = 'active' AND a.is_active = 1
            LIMIT 1
        """, (url,))
        exact = c.fetchone()

        if exact:
            conn.close()
            sections = []
            try:
                sections = json.loads(exact[3] or "[]")
            except (json.JSONDecodeError, TypeError):
                pass
            return {
                "match": "exact",
                "classification": "official",
                "endpoint_id": exact[0],
                "endpoint_url": exact[1],
                "endpoint_name": exact[2],
                "sections": sections,
                "authority": exact[4],
                "authority_type": exact[5],
                "authority_url": exact[6],
                "trust_level": exact[7],
                "escalation_required": bool(exact[8]),
                "supports_replay": bool(exact[9]),
                "country": exact[10],
                "iso_code": exact[11],
            }

        c.execute("""
            SELECT a.name, a.authority_type, a.website_url, a.trust_level,
                   a.escalation_required, a.supports_replay,
                   sc.name, sc.iso_code
            FROM source_authorities a
            JOIN source_countries sc ON a.country_id = sc.id
            WHERE LOWER(a.website_url) LIKE ? AND a.is_active = 1
            ORDER BY a.precedence_rank
            LIMIT 1
        """, (f"%{domain}%",))
        domain_match = c.fetchone()

        if domain_match:
            conn.close()
            return {
                "match": "domain",
                "classification": "official",
                "authority": domain_match[0],
                "authority_type": domain_match[1],
                "authority_url": domain_match[2],
                "trust_level": domain_match[3],
                "escalation_required": bool(domain_match[4]),
                "supports_replay": bool(domain_match[5]),
                "country": domain_match[6],
                "iso_code": domain_match[7],
            }

        c.execute("""
            SELECT classification, matched_authority, matched_country, notes, classified_by, created_at
            FROM url_classifications
            WHERE url = ? OR domain = ?
            ORDER BY CASE WHEN url = ? THEN 0 ELSE 1 END
            LIMIT 1
        """, (url, domain, url))
        prev = c.fetchone()
        conn.close()

        if prev:
            return {
                "match": "previously_classified",
                "classification": prev[0],
                "authority": prev[1] or "",
                "country": prev[2] or "",
                "notes": prev[3] or "",
                "classified_by": prev[4] or "",
                "classified_at": prev[5],
            }

        return {"match": "none", "classification": "unknown", "domain": domain}

    def classify_url(self, url: str, classification: str, notes: str = "",
                     classified_by: str = "", matched_authority: str = "",
                     matched_country: str = "") -> dict:
        from urllib.parse import urlparse
        from datetime import datetime
        parsed = urlparse(url)
        domain = parsed.netloc.lower().lstrip("www.")
        now = datetime.now().isoformat()

        conn = self.db.connect()
        c = conn.cursor()
        c.execute("""
            INSERT INTO url_classifications
            (url, domain, classification, matched_authority, matched_country, notes, classified_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                classification=excluded.classification,
                notes=excluded.notes,
                classified_by=excluded.classified_by,
                matched_authority=excluded.matched_authority,
                matched_country=excluded.matched_country,
                created_at=excluded.created_at
        """, (url, domain, classification, matched_authority, matched_country, notes, classified_by, now))
        conn.commit()
        conn.close()
        return {"url": url, "classification": classification, "classified_at": now}

    def list_classifications(self, limit: int = 50) -> list:
        conn = self.db.connect()
        c = conn.cursor()
        c.execute("""
            SELECT id, url, domain, classification, matched_authority, matched_country,
                   notes, classified_by, created_at
            FROM url_classifications
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        rows = c.fetchall()
        conn.close()
        return [{
            "id": r[0], "url": r[1], "domain": r[2], "classification": r[3],
            "matched_authority": r[4], "matched_country": r[5],
            "notes": r[6], "classified_by": r[7], "created_at": r[8],
        } for r in rows]

    def _row_to_endpoint(self, r) -> SourceEndpoint:
        sections_raw = r[2] or "[]"
        try:
            sections = tuple(json.loads(sections_raw))
        except (json.JSONDecodeError, TypeError):
            sections = ()

        return SourceEndpoint(
            country=r[28],
            authority=r[19],
            url=r[1],
            sections=sections,
            name=r[17] or "",
            endpoint_id=r[0],
            authority_id=r[18],
            country_id=r[26],
            iso_code=r[27],
            authority_type=r[20] or "",
            authority_url=r[21] or "",
            trust_level=r[22] or "official",
            precedence_rank=r[23] or 1,
            escalation_required=bool(r[12]),
            supports_replay=bool(r[13]),
            source_type=r[3] or "html",
            content_language=r[4] or "en",
            authority_category=r[5] or "",
            extraction_strategy=r[6] or "html_readability",
            parser_key=r[7] or "html_readability_v1",
            crawl_frequency=r[8] or "monthly",
            change_detection_strategy=r[9] or "semantic",
            requires_authentication=bool(r[10]),
            is_javascript_heavy=bool(r[11]),
            owner_team=r[14] or "",
            notes=r[15] or "",
            parent_endpoint_id=r[29] or "" if len(r) > 29 else "",
            status=r[16] or "active",
        )

    def _fetch_json(self, url: str) -> dict:
        logger.debug("Fetching source endpoints JSON from %s", url)
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                raw = response.read()
            return json.loads(raw)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to fetch source endpoints from {url}: {exc}"
            ) from exc
