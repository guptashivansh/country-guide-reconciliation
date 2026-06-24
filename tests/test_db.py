"""Tests for the dual-backend SQL translation layer."""
import pytest
from app.utils.db import _adapt_sql


class TestAdaptSql:
    def test_basic_placeholder_replacement(self):
        assert _adapt_sql("SELECT * FROM t WHERE id = ?") == "SELECT * FROM t WHERE id = %s"

    def test_multiple_placeholders(self):
        assert _adapt_sql("INSERT INTO t (a, b) VALUES (?, ?)") == "INSERT INTO t (a, b) VALUES (%s, %s)"

    def test_no_placeholders(self):
        sql = "SELECT * FROM t"
        assert _adapt_sql(sql) == sql

    def test_question_mark_inside_string_literal(self):
        sql = "SELECT * FROM t WHERE name = '?' AND id = ?"
        assert _adapt_sql(sql) == "SELECT * FROM t WHERE name = '?' AND id = %s"

    def test_escaped_quotes_in_string(self):
        sql = "INSERT INTO t (val) VALUES ('it''s a test') WHERE id = ?"
        result = _adapt_sql(sql)
        assert "it''s a test" in result
        assert result.endswith("id = %s")

    def test_autoincrement(self):
        sql = "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT)"
        assert "SERIAL PRIMARY KEY" in _adapt_sql(sql)

    def test_insert_or_ignore(self):
        sql = "INSERT OR IGNORE INTO t (a) VALUES (?)"
        result = _adapt_sql(sql)
        assert "INSERT INTO" in result
        assert "ON CONFLICT DO NOTHING" in result
        assert "OR IGNORE" not in result

    def test_date_function(self):
        sql = "SELECT * FROM t WHERE created > date(col)"
        assert "(col)::date" in _adapt_sql(sql)

    def test_combined_transformations(self):
        sql = "INSERT OR IGNORE INTO t (created) VALUES (date(?))"
        result = _adapt_sql(sql)
        assert "%s" in result
        assert "ON CONFLICT DO NOTHING" in result
        assert "::date" in result
