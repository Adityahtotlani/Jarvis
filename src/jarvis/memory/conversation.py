"""Persistent conversation memory and user facts — backed by SQLite."""

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
        self._create_tables()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _create_tables(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                role      TEXT    NOT NULL,
                content   TEXT    NOT NULL,
                timestamp TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS facts (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                content   TEXT    NOT NULL UNIQUE,
                timestamp TEXT    NOT NULL
            );
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------

    def add_message(self, role: str, content: str) -> None:
        """Store a single conversation turn."""
        self._conn.execute(
            "INSERT INTO conversations (role, content, timestamp) VALUES (?, ?, ?)",
            (role, content, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def get_recent(self, n: int = 10) -> list[dict]:
        """Return the last *n* turns as {role, content} dicts, oldest first."""
        cursor = self._conn.execute(
            "SELECT role, content FROM conversations ORDER BY id DESC LIMIT ?",
            (n,),
        )
        rows = cursor.fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Keyword search over stored conversations."""
        cursor = self._conn.execute(
            "SELECT role, content FROM conversations "
            "WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{query}%", limit),
        )
        rows = cursor.fetchall()
        return [{"role": r[0], "content": r[1]} for r in rows]

    # ------------------------------------------------------------------
    # User facts (persistent across sessions)
    # ------------------------------------------------------------------

    def remember_fact(self, fact: str) -> str:
        """
        Permanently store a fact about the user.
        Silently ignores duplicates.
        """
        if not fact:
            return "There was nothing to remember, sir."
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO facts (content, timestamp) VALUES (?, ?)",
                (fact.strip(), datetime.now(timezone.utc).isoformat()),
            )
            self._conn.commit()
            return f"Understood, sir. I've made a note of that."
        except sqlite3.Error:
            return "I encountered an issue saving that fact, sir."

    def recall_facts(self) -> str:
        """Return all stored user facts as a spoken sentence."""
        cursor = self._conn.execute(
            "SELECT content FROM facts ORDER BY id ASC"
        )
        rows = cursor.fetchall()
        if not rows:
            return "I have no stored facts about you, sir."
        facts = ". ".join(r[0] for r in rows)
        return f"Here is what I know about you, sir: {facts}."

    def forget_fact(self, keyword: str) -> str:
        """Delete facts matching *keyword*."""
        cursor = self._conn.execute(
            "DELETE FROM facts WHERE content LIKE ?",
            (f"%{keyword}%",),
        )
        self._conn.commit()
        count = cursor.rowcount
        if count == 0:
            return f"I found no stored facts matching that, sir."
        return f"Done. I've removed {count} fact{'s' if count != 1 else ''}, sir."

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()
