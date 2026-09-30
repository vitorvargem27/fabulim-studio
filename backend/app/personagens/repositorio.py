"""Biblioteca de personagens: a ficha, o estilo (2D ou 3D), a voz e o estado de cada um.

As imagens ficam na biblioteca de mídias, ligadas ao personagem (``dono_tipo='personagem'``). Editar a ficha sobe a versão,
e as imagens de versões anteriores continuam guardadas: nada é sobrescrito.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..db import Database

ESTADOS = ("rascunho", "variacoes", "escolhido", "pronto")
VOZ_PADRAO: dict[str, Any] = {"id": "pf_dora", "speed": 1.0, "pitch": 1.0, "language": "pt-BR"}


class NomeEmUso(ValueError):
    """Já existe um personagem com este nome neste estilo."""


def _agora() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class Personagem:
    id: str
    nome: str
    estilo: str
    ficha: dict[str, Any] = field(default_factory=dict)
    prompt_original: str = ""
    prompt_tecnico: str = ""
    voz: dict[str, Any] = field(default_factory=dict)
    estado: str = "rascunho"
    imagem_principal_id: str | None = None
    versao: int = 1
    origem: str = "prompt"
    origem_id: str | None = None
    criado_em: str = ""
    atualizado_em: str = ""

    def para_api(self) -> dict[str, Any]:
        principal = self.imagem_principal_id
        return {
            "id": self.id,
            "name": self.nome,
            "style": self.estilo,
            "form": self.ficha,
            "original_prompt": self.prompt_original,
            "technical_prompt": self.prompt_tecnico,
            "voice": self.voz,
            "state": self.estado,
            "main_image_id": principal,
            "main_image_url": f"/api/media/{principal}/thumb" if principal else None,
            "version": self.versao,
            "origin": self.origem,
            "origin_id": self.origem_id,
            "created_at": self.criado_em,
            "updated_at": self.atualizado_em,
        }


def _de_linha(linha: sqlite3.Row) -> Personagem:
    return Personagem(
        id=linha["id"],
        nome=linha["nome"],
        estilo=linha["estilo"],
        ficha=json.loads(linha["ficha"] or "{}"),
        prompt_original=linha["prompt_original"],
        prompt_tecnico=linha["prompt_tecnico"],
        voz=json.loads(linha["voz"] or "{}"),
        estado=linha["estado"],
        imagem_principal_id=linha["imagem_principal_id"],
        versao=int(linha["versao"]),
        origem=linha["origem"],
        origem_id=linha["origem_id"],
        criado_em=linha["criado_em"],
        atualizado_em=linha["atualizado_em"],
    )


class RepositorioPersonagens:
    def __init__(self, db: Database) -> None:
        self._db = db

    def criar(
        self,
        nome: str,
        estilo: str,
        ficha: dict[str, Any],
        *,
        prompt_original: str = "",
        prompt_tecnico: str = "",
        voz: dict[str, Any] | None = None,
        origem: str = "prompt",
        origem_id: str | None = None,
        estado: str = "rascunho",
        versao: int = 1,
    ) -> Personagem:
        id_ = uuid.uuid4().hex
        agora = _agora()
        try:
            with self._db.transaction() as c:
                c.execute(
                    "INSERT INTO personagens (id, nome, estilo, ficha, prompt_original, prompt_tecnico, voz, estado, versao,"
                    " origem, origem_id, criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        id_,
                        nome,
                        estilo,
                        json.dumps(ficha, ensure_ascii=False),
                        prompt_original,
                        prompt_tecnico,
                        json.dumps(voz or VOZ_PADRAO, ensure_ascii=False),
                        estado if estado in ESTADOS else "rascunho",
                        max(int(versao), 1),
                        origem,
                        origem_id,
                        agora,
                        agora,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise NomeEmUso(f"Já existe um personagem chamado «{nome}» em {estilo}.") from exc
        criado = self.obter(id_)
        assert criado is not None
        return criado

    def obter(self, id_: str) -> Personagem | None:
        with self._db.transaction() as c:
            linha = c.execute("SELECT * FROM personagens WHERE id = ?", (id_,)).fetchone()
        return _de_linha(linha) if linha else None

    def obter_por_nome(self, nome: str, estilo: str | None = None) -> Personagem | None:
        """Acha pelo nome (sem diferenciar maiúsculas). Se houver nos dois estilos, o pedido decide."""
        with self._db.transaction() as c:
            if estilo:
                linha = c.execute(
                    "SELECT * FROM personagens WHERE lower(nome) = lower(?) ORDER BY (estilo = ?) DESC, criado_em LIMIT 1",
                    (nome, estilo),
                ).fetchone()
            else:
                linha = c.execute("SELECT * FROM personagens WHERE lower(nome) = lower(?) LIMIT 1", (nome,)).fetchone()
        return _de_linha(linha) if linha else None

    def por_nome(self, nome: str) -> list[Personagem]:
        """Todos os personagens com este nome (um por estilo), sem diferenciar maiúsculas."""
        with self._db.transaction() as c:
            linhas = c.execute(
                "SELECT * FROM personagens WHERE lower(nome) = lower(?) ORDER BY estilo", (nome,)
            ).fetchall()
        return [_de_linha(linha) for linha in linhas]

    def listar(self, *, busca: str | None = None, estilo: str | None = None, limite: int = 500) -> list[Personagem]:
        condicoes: list[str] = []
        valores: list[Any] = []
        if busca:
            condicoes.append("lower(nome) LIKE ? ESCAPE '\\'")
            valores.append("%" + busca.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
        if estilo:
            condicoes.append("estilo = ?")
            valores.append(estilo)
        onde = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""
        with self._db.transaction() as c:
            linhas = c.execute(
                f"SELECT * FROM personagens {onde} ORDER BY atualizado_em DESC LIMIT ?", (*valores, limite)
            ).fetchall()
        return [_de_linha(linha) for linha in linhas]

    def atualizar_ficha(
        self, id_: str, ficha: dict[str, Any], *, nome: str, prompt_tecnico: str | None = None
    ) -> Personagem | None:
        """Grava a ficha nova e sobe a versão (as imagens antigas continuam na biblioteca)."""
        try:
            with self._db.transaction() as c:
                cursor = c.execute(
                    "UPDATE personagens SET ficha = ?, nome = ?, prompt_tecnico = COALESCE(?, prompt_tecnico),"
                    " versao = versao + 1, atualizado_em = ? WHERE id = ?",
                    (json.dumps(ficha, ensure_ascii=False), nome, prompt_tecnico, _agora(), id_),
                )
                if cursor.rowcount == 0:
                    return None
        except sqlite3.IntegrityError as exc:
            raise NomeEmUso(f"Já existe um personagem chamado «{nome}» neste estilo.") from exc
        return self.obter(id_)

    def definir_prompt_tecnico(self, id_: str, prompt_tecnico: str) -> None:
        with self._db.transaction() as c:
            c.execute(
                "UPDATE personagens SET prompt_tecnico = ?, atualizado_em = ? WHERE id = ?",
                (prompt_tecnico, _agora(), id_),
            )

    def definir_voz(self, id_: str, voz: dict[str, Any]) -> None:
        with self._db.transaction() as c:
            c.execute(
                "UPDATE personagens SET voz = ?, atualizado_em = ? WHERE id = ?", (json.dumps(voz), _agora(), id_)
            )

    def definir_estado(self, id_: str, estado: str) -> None:
        if estado not in ESTADOS:
            raise ValueError(f"estado desconhecido: {estado}")
        with self._db.transaction() as c:
            c.execute("UPDATE personagens SET estado = ?, atualizado_em = ? WHERE id = ?", (estado, _agora(), id_))

    def definir_imagem_principal(self, id_: str, midia_id: str | None) -> None:
        with self._db.transaction() as c:
            c.execute(
                "UPDATE personagens SET imagem_principal_id = ?, atualizado_em = ? WHERE id = ?",
                (midia_id, _agora(), id_),
            )

    def remover(self, id_: str) -> bool:
        with self._db.transaction() as c:
            return c.execute("DELETE FROM personagens WHERE id = ?", (id_,)).rowcount > 0

    def contar(self) -> int:
        with self._db.transaction() as c:
            return int(c.execute("SELECT COUNT(*) AS n FROM personagens").fetchone()["n"])
