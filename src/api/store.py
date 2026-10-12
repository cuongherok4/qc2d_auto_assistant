"""Append-only review history. A retry key identifies one immutable submission."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


class DuplicateSubmission(ValueError):
    pass


class ReviewStore:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=15) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA busy_timeout=15000")
            db.execute("""CREATE TABLE IF NOT EXISTS verdicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT UNIQUE NOT NULL,
                payload_hash TEXT NOT NULL,
                image_id TEXT NOT NULL, verdict TEXT NOT NULL,
                reviewer TEXT NOT NULL, seconds_spent REAL NOT NULL,
                note TEXT, obj_ids TEXT NOT NULL, created_at TEXT NOT NULL,
                batch_id TEXT, queue_id TEXT NOT NULL, model_version TEXT NOT NULL,
                rank INTEGER NOT NULL, is_audit INTEGER NOT NULL,
                session_id TEXT NOT NULL, review_order TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS verdict_queue ON verdicts(queue_id, reviewer, session_id)")
            for action in ("UPDATE", "DELETE"):
                db.execute(f"""CREATE TRIGGER IF NOT EXISTS verdicts_no_{action.lower()}
                    BEFORE {action} ON verdicts BEGIN
                    SELECT RAISE(ABORT, 'verdict history is append-only'); END""")
            db.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            yield db

    def append(self, payload: dict, *, is_audit: bool) -> tuple[dict, bool]:
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT * FROM verdicts WHERE request_id=?", (payload["request_id"],)
            ).fetchone()
            if previous:
                if previous["payload_hash"] != digest:
                    raise DuplicateSubmission("request_id đã dùng cho nội dung khác")
                return self._decode(previous), True
            values = {
                **payload,
                "payload_hash": digest,
                "is_audit": int(is_audit),
                "created_at": datetime.now(UTC).isoformat(),
            }
            values["obj_ids"] = json.dumps(values["obj_ids"], ensure_ascii=False)
            cols = list(values)
            cur = db.execute(
                f"INSERT INTO verdicts ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                [values[c] for c in cols],
            )
            row = db.execute("SELECT * FROM verdicts WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode(row), False

    @staticmethod
    def _decode(row) -> dict:
        result = dict(row)
        result.pop("payload_hash", None)
        result["obj_ids"] = json.loads(result["obj_ids"])
        result["is_audit"] = bool(result["is_audit"])
        return result

    def records(self, **filters) -> list[dict]:
        allowed = {"queue_id", "reviewer", "session_id", "review_order", "batch_id"}
        if set(filters) - allowed:
            raise ValueError("Unknown history filter")
        selected = {k: v for k, v in filters.items() if v is not None}
        clause = " AND ".join(f"{k}=?" for k in selected)
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM verdicts" + (f" WHERE {clause}" if clause else "") + " ORDER BY id",
                list(selected.values()),
            ).fetchall()
            return [self._decode(row) for row in rows]

    def state(self, key: str, value: dict | None = None) -> dict | None:
        with self.connection() as db:
            if value is not None:
                db.execute(
                    "INSERT INTO state VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(value, allow_nan=False)),
                )
            row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def submission(self, request_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM verdicts WHERE request_id=?", (request_id,)).fetchone()
            return self._decode(row) if row else None

    def states(self, values: dict[str, dict]):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            for key, value in values.items():
                db.execute(
                    "INSERT INTO state VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(value, allow_nan=False)),
                )

    def state_items(self, prefix: str) -> dict[str, dict]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT key, value FROM state WHERE substr(key, 1, ?) = ?", (len(prefix), prefix)
            )
            return {row["key"]: json.loads(row["value"]) for row in rows}
