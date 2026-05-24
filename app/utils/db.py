"""
Dual-backend database layer: SQLite (default) or PostgreSQL.

Set the DATABASE_URL environment variable to a PostgreSQL connection string
(e.g. ``postgresql://user:pass@localhost/country_guides``) to use Postgres.
When DATABASE_URL is absent or doesn't start with ``postgres``, the system
falls back to SQLite using the file path from COUNTRY_GUIDE_DB (or
``country_guides.db``).

Install ``psycopg2-binary`` (or ``psycopg2``) to enable the Postgres backend::

    pip install psycopg2-binary
"""

import os
import re
import sqlite3


# ---------------------------------------------------------------------------
# SQL dialect translation
# ---------------------------------------------------------------------------

def _adapt_sql(sql):
    """Convert SQLite-flavored SQL to PostgreSQL-compatible SQL."""
    # Parameter placeholder: ? -> %s
    sql = sql.replace("?", "%s")

    # Auto-increment primary key
    sql = re.sub(
        r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
        "SERIAL PRIMARY KEY",
        sql,
        flags=re.IGNORECASE,
    )

    # INSERT OR IGNORE -> INSERT ... ON CONFLICT DO NOTHING
    if re.search(r"INSERT\s+OR\s+IGNORE\s+INTO", sql, flags=re.IGNORECASE):
        sql = re.sub(
            r"INSERT\s+OR\s+IGNORE\s+INTO",
            "INSERT INTO",
            sql,
            flags=re.IGNORECASE,
        )
        sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

    # SQLite date() function -> Postgres cast
    sql = re.sub(r"\bdate\(([^)]+)\)", r"(\1)::date", sql, flags=re.IGNORECASE)

    return sql


# ---------------------------------------------------------------------------
# Postgres cursor / connection wrappers
# ---------------------------------------------------------------------------

class _PgCursorWrapper:
    """Thin wrapper around a psycopg2 cursor that transparently adapts SQL."""

    def __init__(self, cursor):
        self._cursor = cursor
        self.lastrowid = None
        self.description = cursor.description

    def execute(self, sql, params=None):
        sql = _adapt_sql(sql)

        is_insert = sql.lstrip().upper().startswith("INSERT")
        needs_returning = (
            is_insert
            and "RETURNING" not in sql.upper()
            and "ON CONFLICT DO NOTHING" not in sql.upper()
        )

        if needs_returning:
            sql = sql.rstrip().rstrip(";") + " RETURNING id"
            self._cursor.execute(sql, params or ())
            row = self._cursor.fetchone()
            self.lastrowid = row[0] if row else None
        else:
            self._cursor.execute(sql, params or ())

        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class _PgConnectionWrapper:
    """Wraps a psycopg2 connection so repositories can use SQLite-flavored SQL."""

    def __init__(self, conn, dict_rows=False):
        self._conn = conn
        self._dict_rows = dict_rows

    def cursor(self):
        if self._dict_rows:
            import psycopg2.extras  # noqa: delay import
            raw = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            raw = self._conn.cursor()
        return _PgCursorWrapper(raw)

    def execute(self, sql, params=None):
        """Convenience for ``conn.execute(...)`` pattern (DriftRepository)."""
        c = self.cursor()
        c.execute(sql, params)
        return c

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *args):
        return self._conn.__exit__(*args)


# ---------------------------------------------------------------------------
# Public Database class
# ---------------------------------------------------------------------------

class Database:
    """
    Database handle that picks SQLite or PostgreSQL based on DATABASE_URL.

    Repositories receive a ``Database`` instance (or a plain string path for
    backward compatibility) and call ``self.db.connect()`` to get a
    DB-API 2.0 connection.  When Postgres is active the returned connection
    transparently rewrites SQLite-flavored SQL on every ``execute()`` call,
    so repository code stays unchanged.
    """

    def __init__(self, db_path=None):
        url = os.environ.get("DATABASE_URL", "")
        if url.startswith(("postgresql://", "postgres://")):
            self.dialect = "postgres"
            self._dsn = url
            self._db_path = None
        else:
            self.dialect = "sqlite"
            self._dsn = None
            self._db_path = db_path or "country_guides.db"

    # Backward compat: some code still reads .db_path
    @property
    def db_path(self):
        return self._db_path

    def connect(self):
        """Return a connection (wrapped for Postgres, raw for SQLite)."""
        if self.dialect == "postgres":
            import psycopg2  # noqa: delay import
            return _PgConnectionWrapper(psycopg2.connect(self._dsn))
        return sqlite3.connect(self._db_path)

    def dict_connect(self):
        """Connection whose rows behave like dicts (for DriftRepository)."""
        if self.dialect == "postgres":
            import psycopg2  # noqa: delay import
            return _PgConnectionWrapper(psycopg2.connect(self._dsn), dict_rows=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_table_columns(self, conn, table_name):
        """Return the set of column names for *table_name*."""
        if self.dialect == "postgres":
            c = conn.cursor()
            # Use raw psycopg2 execute — the wrapper will adapt the SQL,
            # but there are no ?-placeholders to replace here.
            c.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = %s",
                (table_name,),
            )
            return {row[0] for row in c.fetchall()}
        c = conn.cursor()
        c.execute(f"PRAGMA table_info({table_name})")
        return {row[1] for row in c.fetchall()}
