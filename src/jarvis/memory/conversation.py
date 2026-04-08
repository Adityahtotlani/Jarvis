"""Persistent conversation memory backed by SQLite."""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class ConversationMemory:
    def __init__(self, config: dict):
        memory_cfg = config.get("memory", {})
        raw_path = memory_cfg.get("db_path", "~/.jarvis/memory.db")
        db_path = Path(os.path.expanduser(raw_path))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._create_table()

    def _create_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                role      TEXT    NOT NULL,
                content   TEXT    NOT NULL,
                timestamp TEXT    NOT NULL
            )
            """
        )
        self._conn.commit()

    def add_message(self, role: str, content: str) -> None:
        """Store a single conversation turn."""
        self._conn.execute(
            "INSERT INTO conversations (role, content, timestamp) VALUES (?, ?, ?)",
            (role, content, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def get_recent(self, n: int = 10) -> list[dict]:
        """Return the last *n* turns as a list of {role, content} dicts."""
        cursor = self._conn.execute(
            "SELECT role, content FROM conversations ORDER BY id DESC LIMIT ?",
            (n,),
        )
        rows = cursor.fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Simple keyword search over stored conversations."""
        cursor = self._conn.execute(
            "SELECT role, content FROM conversations WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{query}%", limit),
        )
        rows = cursor.fetchall()
        return [{"role": r[0], "content": r[1]} for r in rows]

    def close(self) -> None:
        self._conn.close()
