"""SQLite-opslag: per record de nieuwste versie; seq bepaalt wat een toestel nog moet ophalen."""
import json
import sqlite3
from pathlib import Path

TABLES = {"semesters", "courses", "sessions"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  tbl TEXT NOT NULL,
  id TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  seq INTEGER NOT NULL,
  data TEXT NOT NULL,
  PRIMARY KEY (tbl, id)
);
CREATE INDEX IF NOT EXISTS records_seq ON records (seq);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, data TEXT NOT NULL);
"""


class Store:
    def __init__(self, path: str | Path):
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def next_seq(self) -> int:
        row = self.db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM records").fetchone()
        return row[0]

    def apply(self, changes: list[dict]) -> None:
        """Conflicten per record: de recentste updatedAt wint."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            for change in changes:
                table, record = change["table"], change["record"]
                current = self.db.execute(
                    "SELECT updated_at FROM records WHERE tbl = ? AND id = ?", (table, record["id"])
                ).fetchone()
                if current and current[0] >= record["updatedAt"]:
                    continue
                self.db.execute(
                    "INSERT OR REPLACE INTO records (tbl, id, updated_at, seq, data) VALUES (?, ?, ?, ?, ?)",
                    (table, record["id"], record["updatedAt"], self.next_seq(), json.dumps(record)),
                )
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def since(self, cursor: int) -> tuple[list[dict], int]:
        rows = self.db.execute(
            "SELECT tbl, data, seq FROM records WHERE seq > ? ORDER BY seq", (cursor,)
        ).fetchall()
        records = [{"table": tbl, "record": json.loads(data)} for tbl, data, _ in rows]
        return records, rows[-1][2] if rows else cursor

    def add_event(self, event: dict) -> None:
        """Dubbels tellen niet: de afzender mag gerust opnieuw proberen."""
        self.db.execute("INSERT OR IGNORE INTO events (id, data) VALUES (?, ?)", (event["id"], json.dumps(event)))

    def events_since(self, after: int) -> tuple[list[dict], int]:
        rows = self.db.execute("SELECT seq, data FROM events WHERE seq > ? ORDER BY seq", (after,)).fetchall()
        return [json.loads(data) for _, data in rows], rows[-1][0] if rows else after

    def active_courses(self) -> list[dict]:
        """De vakken van het actieve semester, zoals Inhaal ze kent; verborgen vakken niet."""
        def records(table: str) -> list[dict]:
            rows = self.db.execute("SELECT data FROM records WHERE tbl = ?", (table,)).fetchall()
            return [r for r in (json.loads(data) for (data,) in rows) if not r.get("deletedAt")]

        active = {s["id"] for s in records("semesters") if s.get("isActive")}
        return [
            {"name": c.get("name"), "codes": c.get("codes", []), "language": c.get("language")}
            for c in records("courses")
            if c.get("semesterId") in active and not c.get("hidden")
        ]

    def get_meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
