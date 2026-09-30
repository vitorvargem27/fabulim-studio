"""Projetos de vídeo e as cenas deles, com histórico de versões por cena (nada é sobrescrito)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..db import Database

ETAPAS = ("enredo", "roteiro", "storyboard", "animacao", "audio", "montagem", "revisao")
FORMATOS = ("short", "longo")


def _agora() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def proporcao_do_formato(formato: str) -> str:
    """Vídeo longo é 16:9; Short é 9:16 (briefing, seção 1)."""
    return "9:16" if formato == "short" else "16:9"


@dataclass(frozen=True)
class Projeto:
    id: str
    titulo: str
    formato: str
    idioma: str
    estilo: str
    duracao_alvo_s: int
    enredo: dict[str, Any] = field(default_factory=dict)
    personagens: list[str] = field(default_factory=list)
    etapa: str = "enredo"
    aprovacoes: dict[str, bool] = field(default_factory=dict)
    musica: dict[str, Any] = field(default_factory=dict)
    configuracoes: dict[str, Any] = field(default_factory=dict)
    origem_id: str | None = None
    criado_em: str = ""
    atualizado_em: str = ""

    @property
    def proporcao(self) -> str:
        return proporcao_do_formato(self.formato)

    def para_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.titulo,
            "format": self.formato,
            "aspect": self.proporcao,
            "language": self.idioma,
            "style": self.estilo,
            "target_duration_s": self.duracao_alvo_s,
            "story": self.enredo,
            "character_ids": self.personagens,
            "stage": self.etapa,
            "approvals": self.aprovacoes,
            "music": self.musica,
            "settings": self.configuracoes,
            "origin_id": self.origem_id,
            "created_at": self.criado_em,
            "updated_at": self.atualizado_em,
        }


@dataclass(frozen=True)
class Cena:
    id: str
    projeto_id: str
    ordem: int
    dados: dict[str, Any]
    status: str
    versao: int
    criado_em: str
    atualizado_em: str

    def para_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.projeto_id,
            "order": self.ordem,
            "data": self.dados,
            "status": self.status,
            "version": self.versao,
            "created_at": self.criado_em,
            "updated_at": self.atualizado_em,
        }


def _projeto(linha: sqlite3.Row) -> Projeto:
    return Projeto(
        id=linha["id"],
        titulo=linha["titulo"],
        formato=linha["formato"],
        idioma=linha["idioma"],
        estilo=linha["estilo"],
        duracao_alvo_s=int(linha["duracao_alvo_s"]),
        enredo=json.loads(linha["enredo"] or "{}"),
        personagens=json.loads(linha["personagens"] or "[]"),
        etapa=linha["etapa"],
        aprovacoes=json.loads(linha["aprovacoes"] or "{}"),
        musica=json.loads(linha["musica"] or "{}"),
        configuracoes=json.loads(linha["configuracoes"] or "{}"),
        origem_id=linha["origem_id"],
        criado_em=linha["criado_em"],
        atualizado_em=linha["atualizado_em"],
    )


def _cena(linha: sqlite3.Row) -> Cena:
    return Cena(
        id=linha["id"],
        projeto_id=linha["projeto_id"],
        ordem=int(linha["ordem"]),
        dados=json.loads(linha["dados"] or "{}"),
        status=linha["status"],
        versao=int(linha["versao"]),
        criado_em=linha["criado_em"],
        atualizado_em=linha["atualizado_em"],
    )


def _json(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False)


class RepositorioProjetos:
    def __init__(self, db: Database) -> None:
        self._db = db

    # --- projetos ---------------------------------------------------------------------------------------------------
    def criar(
        self,
        titulo: str,
        formato: str,
        idioma: str,
        estilo: str,
        duracao_alvo_s: int,
        enredo: dict[str, Any],
        personagens: list[str],
        *,
        musica: dict[str, Any] | None = None,
        configuracoes: dict[str, Any] | None = None,
        origem_id: str | None = None,
    ) -> Projeto:
        id_ = uuid.uuid4().hex
        agora = _agora()
        with self._db.transaction() as c:
            c.execute(
                "INSERT INTO projetos (id, titulo, formato, idioma, estilo, duracao_alvo_s, enredo, personagens, etapa,"
                " aprovacoes, musica, configuracoes, origem_id, criado_em, atualizado_em)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'enredo', '{}', ?, ?, ?, ?, ?)",
                (
                    id_,
                    titulo,
                    formato,
                    idioma,
                    estilo,
                    duracao_alvo_s,
                    _json(enredo),
                    _json(personagens),
                    _json(musica or {}),
                    _json(configuracoes or {}),
                    origem_id,
                    agora,
                    agora,
                ),
            )
        criado = self.obter(id_)
        assert criado is not None
        return criado

    def obter(self, id_: str) -> Projeto | None:
        with self._db.transaction() as c:
            linha = c.execute("SELECT * FROM projetos WHERE id = ?", (id_,)).fetchone()
        return _projeto(linha) if linha else None

    def listar(self, limite: int = 200) -> list[Projeto]:
        with self._db.transaction() as c:
            linhas = c.execute("SELECT * FROM projetos ORDER BY atualizado_em DESC LIMIT ?", (limite,)).fetchall()
        return [_projeto(linha) for linha in linhas]

    def atualizar(self, id_: str, **campos: Any) -> Projeto | None:
        """Atualiza só os campos informados: titulo, formato, idioma, estilo, duracao_alvo_s, enredo, personagens,
        musica, configuracoes (os dicionários e listas viram JSON)."""
        permitidos = {
            "titulo",
            "formato",
            "idioma",
            "estilo",
            "duracao_alvo_s",
            "enredo",
            "personagens",
            "musica",
            "configuracoes",
            "aprovacoes",
            "etapa",
        }
        desconhecidos = set(campos) - permitidos
        if desconhecidos:
            raise ValueError(f"campo de projeto desconhecido: {', '.join(sorted(desconhecidos))}")
        if not campos:
            return self.obter(id_)
        if "etapa" in campos and campos["etapa"] not in ETAPAS:
            raise ValueError(f"etapa desconhecida: {campos['etapa']}")
        colunas = ", ".join(f"{nome} = ?" for nome in campos)
        valores = [_json(v) if isinstance(v, (dict, list)) else v for v in campos.values()]
        with self._db.transaction() as c:
            cursor = c.execute(
                f"UPDATE projetos SET {colunas}, atualizado_em = ? WHERE id = ?",  # colunas vêm da lista fixa acima
                (*valores, _agora(), id_),
            )
            if cursor.rowcount == 0:
                return None
        return self.obter(id_)

    def remover(self, id_: str) -> bool:
        with self._db.transaction() as c:
            return c.execute("DELETE FROM projetos WHERE id = ?", (id_,)).rowcount > 0

    def usam_o_personagem(self, personagem_id: str) -> list[Projeto]:
        return [p for p in self.listar(limite=1000) if personagem_id in p.personagens]

    def variantes_de(self, id_: str) -> list[Projeto]:
        return [p for p in self.listar(limite=1000) if p.origem_id == id_]

    # --- cenas ------------------------------------------------------------------------------------------------------
    def cenas(self, projeto_id: str) -> list[Cena]:
        with self._db.transaction() as c:
            linhas = c.execute(
                "SELECT * FROM cenas WHERE projeto_id = ? ORDER BY ordem, criado_em", (projeto_id,)
            ).fetchall()
        return [_cena(linha) for linha in linhas]

    def cena(self, id_: str) -> Cena | None:
        with self._db.transaction() as c:
            linha = c.execute("SELECT * FROM cenas WHERE id = ?", (id_,)).fetchone()
        return _cena(linha) if linha else None

    def criar_cena(self, projeto_id: str, dados: dict[str, Any], ordem: int | None = None) -> Cena:
        id_ = uuid.uuid4().hex
        agora = _agora()
        with self._db.transaction() as c:
            if ordem is None:
                ordem = int(
                    c.execute(
                        "SELECT COALESCE(MAX(ordem), 0) + 1 FROM cenas WHERE projeto_id = ?", (projeto_id,)
                    ).fetchone()[0]
                )
            else:
                c.execute("UPDATE cenas SET ordem = ordem + 1 WHERE projeto_id = ? AND ordem >= ?", (projeto_id, ordem))
            c.execute(
                "INSERT INTO cenas (id, projeto_id, ordem, dados, status, versao, criado_em, atualizado_em)"
                " VALUES (?, ?, ?, ?, 'pendente', 1, ?, ?)",
                (id_, projeto_id, ordem, _json(dados), agora, agora),
            )
            c.execute(
                "INSERT INTO cena_versoes (cena_id, versao, dados, motivo, criado_em) VALUES (?, 1, ?, 'criada', ?)",
                (id_, _json(dados), agora),
            )
            c.execute("UPDATE projetos SET atualizado_em = ? WHERE id = ?", (agora, projeto_id))
        criada = self.cena(id_)
        assert criada is not None
        return criada

    def importar_cena(
        self,
        projeto_id: str,
        ordem: int,
        dados: dict[str, Any],
        versoes: list[dict[str, Any]],
        versao: int,
        status: str = "pendente",
    ) -> Cena:
        """Traz uma cena de um pacote com o histórico de versões inteiro (cada versão guarda o motivo e a data originais)."""
        id_ = uuid.uuid4().hex
        agora = _agora()
        historico = sorted(versoes, key=lambda v: int(v["version"])) or [
            {"version": versao, "data": dados, "reason": "importada", "created_at": agora}
        ]
        with self._db.transaction() as c:
            c.execute(
                "INSERT INTO cenas (id, projeto_id, ordem, dados, status, versao, criado_em, atualizado_em)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (id_, projeto_id, ordem, _json(dados), status, versao, agora, agora),
            )
            for v in historico:
                c.execute(
                    "INSERT INTO cena_versoes (cena_id, versao, dados, motivo, criado_em) VALUES (?, ?, ?, ?, ?)",
                    (id_, int(v["version"]), _json(v["data"]), str(v["reason"]), str(v["created_at"])),
                )
            c.execute("UPDATE projetos SET atualizado_em = ? WHERE id = ?", (agora, projeto_id))
        criada = self.cena(id_)
        assert criada is not None
        return criada

    def atualizar_versoes_da_cena(self, id_: str, transformar: Any) -> None:
        """Reescreve os dados de todas as versões guardadas de uma cena com ``transformar(dados) -> dados`` (usado ao importar)."""
        with self._db.transaction() as c:
            linhas = c.execute("SELECT versao, dados FROM cena_versoes WHERE cena_id = ?", (id_,)).fetchall()
            for linha in linhas:
                c.execute(
                    "UPDATE cena_versoes SET dados = ? WHERE cena_id = ? AND versao = ?",
                    (_json(transformar(json.loads(linha["dados"]))), id_, linha["versao"]),
                )

    def atualizar_cena(self, id_: str, dados: dict[str, Any], motivo: str) -> Cena | None:
        """Grava os novos dados e guarda uma versão nova (a anterior continua no histórico)."""
        agora = _agora()
        with self._db.transaction() as c:
            atual = c.execute("SELECT versao, projeto_id FROM cenas WHERE id = ?", (id_,)).fetchone()
            if atual is None:
                return None
            versao = int(atual["versao"]) + 1
            c.execute(
                "UPDATE cenas SET dados = ?, versao = ?, atualizado_em = ? WHERE id = ?",
                (_json(dados), versao, agora, id_),
            )
            c.execute(
                "INSERT INTO cena_versoes (cena_id, versao, dados, motivo, criado_em) VALUES (?, ?, ?, ?, ?)",
                (id_, versao, _json(dados), motivo, agora),
            )
            c.execute("UPDATE projetos SET atualizado_em = ? WHERE id = ?", (agora, atual["projeto_id"]))
        return self.cena(id_)

    def atualizar_cena_sem_versao(self, id_: str, dados: dict[str, Any]) -> Cena | None:
        """Para o que é só andamento (um clipe que acabou de sair, uma aprovação): não vira versão do histórico."""
        with self._db.transaction() as c:
            cursor = c.execute(
                "UPDATE cenas SET dados = ?, atualizado_em = ? WHERE id = ?", (_json(dados), _agora(), id_)
            )
            if cursor.rowcount == 0:
                return None
        return self.cena(id_)

    def versoes_da_cena(self, id_: str) -> list[dict[str, Any]]:
        with self._db.transaction() as c:
            linhas = c.execute("SELECT * FROM cena_versoes WHERE cena_id = ? ORDER BY versao DESC", (id_,)).fetchall()
        return [
            {
                "version": r["versao"],
                "data": json.loads(r["dados"]),
                "reason": r["motivo"],
                "created_at": r["criado_em"],
            }
            for r in linhas
        ]

    def restaurar_versao(self, id_: str, versao: int) -> Cena | None:
        """Volta os dados da cena para os de uma versão antiga, gravando isso como uma versão nova (nada se perde)."""
        with self._db.transaction() as c:
            linha = c.execute(
                "SELECT dados FROM cena_versoes WHERE cena_id = ? AND versao = ?", (id_, versao)
            ).fetchone()
        if linha is None:
            return None
        return self.atualizar_cena(id_, json.loads(linha["dados"]), f"voltou para a versão {versao}")

    def reordenar_cenas(self, projeto_id: str, ids_na_ordem: list[str]) -> None:
        agora = _agora()
        with self._db.transaction() as c:
            existentes = {r["id"] for r in c.execute("SELECT id FROM cenas WHERE projeto_id = ?", (projeto_id,))}
            if set(ids_na_ordem) != existentes:
                raise ValueError("a lista precisa ter exatamente as cenas do projeto")
            for ordem, cena_id in enumerate(ids_na_ordem, start=1):
                c.execute("UPDATE cenas SET ordem = ? WHERE id = ?", (ordem, cena_id))
            c.execute("UPDATE projetos SET atualizado_em = ? WHERE id = ?", (agora, projeto_id))

    def remover_cena(self, id_: str) -> bool:
        with self._db.transaction() as c:
            linha = c.execute("SELECT projeto_id, ordem FROM cenas WHERE id = ?", (id_,)).fetchone()
            if linha is None:
                return False
            c.execute("DELETE FROM cenas WHERE id = ?", (id_,))
            c.execute(
                "UPDATE cenas SET ordem = ordem - 1 WHERE projeto_id = ? AND ordem > ?",
                (linha["projeto_id"], linha["ordem"]),
            )
            c.execute("UPDATE projetos SET atualizado_em = ? WHERE id = ?", (_agora(), linha["projeto_id"]))
        return True

    def apagar_todas_as_cenas(self, projeto_id: str) -> int:
        with self._db.transaction() as c:
            return c.execute("DELETE FROM cenas WHERE projeto_id = ?", (projeto_id,)).rowcount
