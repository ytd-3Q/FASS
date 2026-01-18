import sqlite3


def apply_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY
);
"""
    )
    row = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations").fetchone()
    current = int(row["v"] if row is not None else 0)
    migrations: list[tuple[int, str]] = [
        (
            1,
            """
CREATE TABLE IF NOT EXISTS l3_categories (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  identity TEXT NOT NULL,
  system_prompt TEXT NOT NULL,
  routing_strategy_json TEXT NOT NULL,
  capability_requirements_json TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at_unix_ms INTEGER NOT NULL,
  updated_at_unix_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS personas (
  id TEXT PRIMARY KEY,
  l3_id TEXT NOT NULL,
  name TEXT NOT NULL,
  prompt_bundle_json TEXT NOT NULL,
  thinking_style TEXT NOT NULL,
  params_json TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at_unix_ms INTEGER NOT NULL,
  updated_at_unix_ms INTEGER NOT NULL,
  FOREIGN KEY(l3_id) REFERENCES l3_categories(id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS model_catalog (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider_id TEXT NOT NULL,
  model_id TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  capabilities_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'online',
  offline_since_unix_ms INTEGER,
  expire_at_unix_ms INTEGER,
  fetched_at_unix_ms INTEGER NOT NULL,
  etag_or_hash TEXT,
  created_at_unix_ms INTEGER NOT NULL,
  updated_at_unix_ms INTEGER NOT NULL,
  UNIQUE(provider_id, model_id)
);

CREATE INDEX IF NOT EXISTS idx_model_catalog_provider_status ON model_catalog(provider_id, status);
CREATE INDEX IF NOT EXISTS idx_model_catalog_expire ON model_catalog(expire_at_unix_ms);

CREATE TABLE IF NOT EXISTS layer_presets (
  layer TEXT PRIMARY KEY,
  selected_model_id TEXT,
  selection_reason_json TEXT,
  default_prompt_template TEXT NOT NULL,
  constraints_json TEXT NOT NULL,
  updated_at_unix_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  l3_id TEXT,
  persona_id TEXT,
  title TEXT,
  created_at_unix_ms INTEGER NOT NULL,
  updated_at_unix_ms INTEGER NOT NULL,
  FOREIGN KEY(l3_id) REFERENCES l3_categories(id) ON DELETE SET NULL ON UPDATE CASCADE,
  FOREIGN KEY(persona_id) REFERENCES personas(id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS trace_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id INTEGER NOT NULL,
  trace_id TEXT NOT NULL,
  parent_id TEXT,
  layer TEXT NOT NULL,
  from_agent TEXT,
  to_agent TEXT,
  event_kind TEXT NOT NULL,
  raw_command_text TEXT,
  content TEXT NOT NULL,
  ts_unix_ms INTEGER NOT NULL,
  status TEXT NOT NULL,
  provider_id TEXT,
  model_id TEXT,
  FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_trace_events_conversation ON trace_events(conversation_id, ts_unix_ms);

CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  encrypted_payload BLOB NOT NULL,
  created_at_unix_ms INTEGER NOT NULL,
  expire_at_unix_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_time ON audit_logs(created_at_unix_ms);

CREATE TABLE IF NOT EXISTS checksums (
  key TEXT PRIMARY KEY,
  checksum TEXT NOT NULL,
  computed_at_unix_ms INTEGER NOT NULL
);
""",
        )
    ]

    for version, sql in migrations:
        if version <= current:
            continue
        conn.executescript(sql)
        conn.execute("INSERT INTO schema_migrations(version) VALUES(?)", (version,))

