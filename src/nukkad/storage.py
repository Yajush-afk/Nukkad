from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def now() -> str:
    return datetime.now(UTC).isoformat()


def identity() -> str:
    return uuid4().hex


class Store:
    """Transactional local documents with a versioned schema and stable identities."""

    def __init__(self, root: Path):
        self.root = root
        self.path = root / "nukkad.sqlite3"
        with self.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("This database needs a newer Nukkad version")
            if version == 0:
                if self.path.stat().st_size:
                    destination = root / "backups" / f"before-migration-{identity()}.sqlite3"
                    with sqlite3.connect(destination) as backup:
                        connection.backup(backup)
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL, updated TEXT NOT NULL, PRIMARY KEY(kind, id))"
                )
                connection.execute("PRAGMA user_version=1")
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def get(self, kind: str, key: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT data FROM records WHERE kind=? AND id=?", (kind, key)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT data FROM records WHERE kind=? ORDER BY updated DESC, id", (kind,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def put(self, kind: str, key: str, value: dict) -> dict:
        self.atomic([(kind, key, value)])
        return value

    def atomic(self, records: list[tuple[str, str, dict]]) -> None:
        with self.connect() as connection:
            connection.executemany(
                "INSERT INTO records(kind,id,data,updated) VALUES(?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data, updated=excluded.updated",
                [
                    (kind, key, json.dumps(value, ensure_ascii=False, allow_nan=False), now())
                    for kind, key, value in records
                ],
            )

    def delete(self, kind: str, key: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM records WHERE kind=? AND id=?", (kind, key))
