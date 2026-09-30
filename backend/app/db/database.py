"""SQLite pela biblioteca padrão: uma conexão por operação (thread-safe), WAL e migrações versionadas."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .migrations import MIGRACOES


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)  # autocommit; transações explícitas
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    @contextmanager
    def transaction(self, *, imediata: bool = False) -> Iterator[sqlite3.Connection]:
        """BEGIN/COMMIT com ROLLBACK em caso de erro. ``imediata`` trava escrita já no início."""
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE" if imediata else "BEGIN")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")
        finally:
            conn.close()

    def migrar(self) -> int:
        """Aplica as migrações pendentes e devolve a versão do esquema."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = self.connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            aplicadas = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
            for versao, sql in MIGRACOES:
                if versao in aplicadas:
                    continue
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))", (versao,)
                )
            row = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations").fetchone()
            return int(row["v"])
        finally:
            conn.close()

    def tamanho_bytes(self) -> int:
        return self.path.stat().st_size if self.path.exists() else 0
