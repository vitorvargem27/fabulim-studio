"""Histórico de prompts reutilizáveis (briefing, seção 6): o que o usuário já colou, do mais novo para o mais antigo."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..db import Database

MAXIMO_POR_TIPO = 100


class HistoricoDePrompts:
    def __init__(self, db: Database) -> None:
        self._db = db

    def registrar(self, tipo: str, texto: str) -> None:
        """Guarda o prompt. O mesmo texto colado de novo sobe para o topo em vez de duplicar."""
        texto = texto.strip()
        if not texto:
            return
        with self._db.transaction() as c:
            c.execute("DELETE FROM historico_prompts WHERE tipo = ? AND texto = ?", (tipo, texto))
            c.execute(
                "INSERT INTO historico_prompts (tipo, texto, criado_em) VALUES (?, ?, ?)",
                (tipo, texto, datetime.now(UTC).isoformat(timespec="seconds")),
            )
            c.execute(
                "DELETE FROM historico_prompts WHERE tipo = ? AND id NOT IN"
                " (SELECT id FROM historico_prompts WHERE tipo = ? ORDER BY id DESC LIMIT ?)",
                (tipo, tipo, MAXIMO_POR_TIPO),
            )

    def listar(self, tipo: str | None = None, limite: int = 30) -> list[dict[str, Any]]:
        with self._db.transaction() as c:
            if tipo:
                linhas = c.execute(
                    "SELECT * FROM historico_prompts WHERE tipo = ? ORDER BY id DESC LIMIT ?", (tipo, limite)
                ).fetchall()
            else:
                linhas = c.execute("SELECT * FROM historico_prompts ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        return [
            {"id": linha["id"], "type": linha["tipo"], "text": linha["texto"], "created_at": linha["criado_em"]}
            for linha in linhas
        ]

    def remover(self, id_: int) -> bool:
        with self._db.transaction() as c:
            return c.execute("DELETE FROM historico_prompts WHERE id = ?", (id_,)).rowcount > 0

    def limpar(self, tipo: str | None = None) -> int:
        with self._db.transaction() as c:
            if tipo:
                return c.execute("DELETE FROM historico_prompts WHERE tipo = ?", (tipo,)).rowcount
            return c.execute("DELETE FROM historico_prompts").rowcount
