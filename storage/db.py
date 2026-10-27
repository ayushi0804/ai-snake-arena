"""SQLite access layer with explicit transactions and versioned migrations.

All SQL lives in storage/ (db.py + services.py) and uses '?' parameters only. Moving to PostgreSQL
means swapping Database.connect()/placeholders in this package; callers (Flask, desktop) only use
the services API. Database access uses Python's built-in sqlite3 module and parameterized SQL.
"""
from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager

MIGRATIONS = [
    (1, """
CREATE TABLE players (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guest_id TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL DEFAULT 'Guest',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE matches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_match_id TEXT UNIQUE,
  player_id INTEGER NOT NULL REFERENCES players(id),
  source TEXT NOT NULL,                       -- web | desktop | legacy
  trust TEXT NOT NULL DEFAULT 'client_reported', -- client_reported | local_desktop | legacy_import
  mode TEXT NOT NULL,                         -- manual | ai | unknown
  algorithm TEXT,
  difficulty TEXT NOT NULL,
  board_w INTEGER NOT NULL, board_h INTEGER NOT NULL,
  wrap INTEGER NOT NULL DEFAULT 0, obstacles INTEGER NOT NULL DEFAULT 0,
  score INTEGER NOT NULL CHECK (score >= 0),
  apples_collected INTEGER NOT NULL DEFAULT 0,
  steps INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  outcome TEXT NOT NULL,
  ai_decisions INTEGER NOT NULL DEFAULT 0,
  ai_total_time_ms REAL NOT NULL DEFAULT 0,
  ai_total_nodes INTEGER NOT NULL DEFAULT 0,
  ai_total_path_len INTEGER NOT NULL DEFAULT 0,
  ai_paths_found INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX idx_matches_player ON matches(player_id, id);
CREATE INDEX idx_matches_score ON matches(score DESC);
CREATE TABLE benchmark_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  kind TEXT NOT NULL,                         -- pathfinding | survival
  algorithm TEXT NOT NULL,
  seed INTEGER NOT NULL, board_w INTEGER NOT NULL, board_h INTEGER NOT NULL,
  wrap INTEGER NOT NULL DEFAULT 0, scenarios INTEGER NOT NULL,
  success_rate REAL, safe_rate REAL, avg_time_ms REAL, avg_nodes REAL, avg_path_len REAL,
  avg_score REAL, avg_steps REAL, completion_rate REAL,
  details TEXT, provenance TEXT NOT NULL
);
CREATE TABLE settings (
  player_id INTEGER PRIMARY KEY REFERENCES players(id),
  data TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""),
]


class Database:
    def __init__(self, path: str):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)  # explicit txns
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    @contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    @contextmanager
    def read(self):
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    def init(self) -> list:
        """Create the DB if needed and apply pending migrations. Returns applied versions."""
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        applied = []
        conn = self.connect()
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                         "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
            for version, sql in MIGRATIONS:
                if version in done:
                    continue
                try:
                    conn.executescript(f"BEGIN;{sql};INSERT INTO schema_migrations(version) VALUES ({int(version)});COMMIT;")
                except sqlite3.Error:
                    conn.execute("ROLLBACK") if conn.in_transaction else None
                    raise
                applied.append(version)
        finally:
            conn.close()
        return applied
