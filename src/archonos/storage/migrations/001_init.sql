-- ArchonOS Next schema v1 — canonical DDL from docs/architecture/CORE_ARCHITECTURE.md §2
-- INTEGER primary keys everywhere. UUIDs banned (FTS5 content_rowid requires integer).

CREATE TABLE IF NOT EXISTS schema_version (
  version     INTEGER NOT NULL,
  applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE settings (
  key         TEXT PRIMARY KEY,
  value       TEXT NOT NULL,
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE documents (
  id          INTEGER PRIMARY KEY,
  source_path TEXT NOT NULL,
  title       TEXT NOT NULL,
  doc_type    TEXT NOT NULL DEFAULT 'md',
  sha256      TEXT NOT NULL UNIQUE,
  byte_size   INTEGER NOT NULL,
  imported_at TEXT NOT NULL DEFAULT (datetime('now')),
  meta        TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE chunks (
  id          INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_idx   INTEGER NOT NULL,
  body        TEXT NOT NULL,
  body_chars  INTEGER NOT NULL,
  UNIQUE(document_id, chunk_idx)
);

CREATE VIRTUAL TABLE chunks_fts USING fts5(
  body,
  content='chunks', content_rowid='id'
);

CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, body) VALUES (new.id, new.body);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, body) VALUES ('delete', old.id, old.body);
END;
CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, body) VALUES ('delete', old.id, old.body);
  INSERT INTO chunks_fts(rowid, body) VALUES (new.id, new.body);
END;

CREATE TABLE memories (
  id          INTEGER PRIMARY KEY,
  kind        TEXT NOT NULL CHECK(kind IN ('decision','state','lesson','note','workflow_outcome')),
  body        TEXT NOT NULL,
  project     TEXT NOT NULL DEFAULT 'default',
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  meta        TEXT NOT NULL DEFAULT '{}'
);

CREATE VIRTUAL TABLE memories_fts USING fts5(
  body,
  content='memories', content_rowid='id'
);

CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid, body) VALUES (new.id, new.body);
END;
CREATE TRIGGER memories_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, body) VALUES ('delete', old.id, old.body);
END;
CREATE TRIGGER memories_au AFTER UPDATE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, body) VALUES ('delete', old.id, old.body);
  INSERT INTO memories_fts(rowid, body) VALUES (new.id, new.body);
END;

CREATE TABLE workflows (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  spec        TEXT NOT NULL,
  version     INTEGER NOT NULL DEFAULT 1,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE workflow_runs (
  id          INTEGER PRIMARY KEY,
  workflow_id INTEGER NOT NULL REFERENCES workflows(id),
  status      TEXT NOT NULL CHECK(status IN ('running','succeeded','failed','aborted')),
  started_at  TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at TEXT,
  log         TEXT NOT NULL DEFAULT '[]'
);
