"""One transaction includes the update, domain changes and pending Telegram replies."""
from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY, role TEXT NOT NULL DEFAULT 'participant',
    name TEXT NOT NULL DEFAULT '', age TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '',
    goal TEXT NOT NULL DEFAULT '', company TEXT NOT NULL DEFAULT '',
    contact TEXT NOT NULL DEFAULT '', employer_city TEXT NOT NULL DEFAULT '',
    employer_status TEXT NOT NULL DEFAULT 'none',
    consent_at INTEGER, employer_consent_at INTEGER, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS flows (
    user_id INTEGER PRIMARY KEY REFERENCES members(id),
    kind TEXT NOT NULL, step INTEGER NOT NULL, data TEXT NOT NULL,
    nonce TEXT NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS vacancies (
    id INTEGER PRIMARY KEY AUTOINCREMENT, employer_id INTEGER NOT NULL REFERENCES members(id),
    company TEXT NOT NULL, title TEXT NOT NULL, city TEXT NOT NULL, schedule TEXT NOT NULL,
    pay TEXT NOT NULL, age TEXT NOT NULL, description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES members(id),
    vacancy_id INTEGER REFERENCES vacancies(id), topic TEXT NOT NULL, body TEXT NOT NULL,
    snapshot TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new', response TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL,
    UNIQUE(user_id, vacancy_id)
);
CREATE INDEX IF NOT EXISTS application_owner ON applications(user_id, id);
CREATE INDEX IF NOT EXISTS vacancy_status ON vacancies(status, id);
CREATE TABLE IF NOT EXISTS processed_updates (id INTEGER PRIMARY KEY, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT, method TEXT NOT NULL, payload TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0, available_at INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending'
);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, isolation_level=None, timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        # Additive migration keeps existing registrations, drafts and applications.
        with self.transaction():
            additions = {
                "members": {"origin": "TEXT NOT NULL DEFAULT 'telegram'", "source_url": "TEXT NOT NULL DEFAULT ''"},
                "vacancies": {"source_url": "TEXT NOT NULL DEFAULT ''", "source_checked_on": "TEXT NOT NULL DEFAULT ''", "seed_key": "TEXT"},
                "applications": {"is_demo": "INTEGER NOT NULL DEFAULT 0", "seed_key": "TEXT"},
            }
            for table, columns in additions.items():
                existing = {row["name"] for row in self.all(f"PRAGMA table_info({table})")}
                for column, definition in columns.items():
                    if column not in existing:
                        self.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            self.execute("CREATE UNIQUE INDEX IF NOT EXISTS vacancy_seed_key ON vacancies(seed_key)")
            self.execute("CREATE UNIQUE INDEX IF NOT EXISTS application_seed_key ON applications(seed_key)")

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def one(self, sql, params=()):
        return self.db.execute(sql, params).fetchone()

    def all(self, sql, params=()):
        return self.db.execute(sql, params).fetchall()

    def execute(self, sql, params=()):
        return self.db.execute(sql, params)

    def enqueue(self, method, payload):
        self.execute("INSERT INTO outbox(method,payload) VALUES (?,?)", (method, json.dumps(payload, ensure_ascii=False)))

    def offset(self):
        row = self.one("SELECT value FROM meta WHERE key='offset'")
        return int(row[0]) if row else 0

    def processed(self, update_id):
        return self.one("SELECT 1 FROM processed_updates WHERE id=?", (update_id,)) is not None

    def finish(self, update_id):
        self.execute("INSERT INTO processed_updates VALUES (?,?)", (update_id, int(time.time())))
        self.execute("INSERT INTO meta VALUES ('offset',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(max(self.offset(), update_id + 1)),))
        self.execute("DELETE FROM processed_updates WHERE created_at < ? AND id < ?", (int(time.time()) - 7 * 86400, update_id - 10000))

    def close(self):
        self.db.close()
