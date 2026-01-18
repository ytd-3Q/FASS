import sqlite3
from pathlib import Path

from .migrations import apply_migrations


def open_db(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=3000;")
    conn.execute(
        """
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""
    )
    conn.execute(
        """
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  cron TEXT,
  payload_json TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at_unix_ms INTEGER NOT NULL,
  updated_at_unix_ms INTEGER NOT NULL
);
"""
    )
    conn.execute(
        """
CREATE TABLE IF NOT EXISTS automation_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  trigger_json TEXT NOT NULL,
  steps_json TEXT NOT NULL,
  created_at_unix_ms INTEGER NOT NULL,
  updated_at_unix_ms INTEGER NOT NULL
);
"""
    )
    conn.execute(
        """
CREATE TABLE IF NOT EXISTS automation_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rule_id INTEGER,
  status TEXT NOT NULL,
  run_at_unix_ms INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  result_json TEXT,
  error TEXT,
  created_at_unix_ms INTEGER NOT NULL,
  updated_at_unix_ms INTEGER NOT NULL
);
"""
    )
    conn.execute(
        """
CREATE TABLE IF NOT EXISTS research_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  query TEXT NOT NULL,
  collection TEXT NOT NULL,
  status TEXT NOT NULL,
  scheduled_at_unix_ms INTEGER NOT NULL,
  query_embedding_json TEXT,
  result_json TEXT,
  error TEXT,
  created_at_unix_ms INTEGER NOT NULL,
  updated_at_unix_ms INTEGER NOT NULL
);
"""
    )
    conn.execute(
        """
CREATE TABLE IF NOT EXISTS research_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  query TEXT NOT NULL,
  query_embedding_json TEXT,
  result_json TEXT,
  created_at_unix_ms INTEGER NOT NULL
);
"""
    )
    apply_migrations(conn)
    conn.commit()
    return conn

