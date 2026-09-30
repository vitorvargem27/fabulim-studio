"""Biblioteca de mídias: tudo o que o estúdio gera ou recebe (imagens, recortes, áudios, vídeos, legendas) fica em
``data/midias``, com um registro no banco (de onde veio, o prompt, a semente, o modelo, os tempos).

Nada é sobrescrito: cada geração é uma mídia nova, e ``pai_id`` liga a mídia à que a originou.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from ..db import Database
from ..security.caminhos import dentro_da_pasta

LADO_DA_MINIATURA = 384
TIPOS = ("imagem", "video", "audio", "legenda")
SEM_DONO = "nenhum"  # valor especial de ``dono_tipo`` nos filtros: só as mídias que não pertencem a ninguém


def _agora() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class Midia:
    id: str
    tipo: str
    papel: str
    caminho: str
    miniatura: str | None
    formato: str | None
    largura: int | None
    altura: int | None
    duracao_s: float | None
    tamanho_bytes: int
    dono_tipo: str | None
    dono_id: str | None
    pai_id: str | None
    prompt: str | None
    prompt_tecnico: str | None
    negativo: str | None
    estilo: str | None
    seed: int | None
    modelo: str | None
    metadados: dict[str, Any] = field(default_factory=dict)
    job_id: str | None = None
    criado_em: str = ""

    def para_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.tipo,
            "role": self.papel,
            "url": f"/api/media/{self.id}",
            "thumb_url": f"/api/media/{self.id}/thumb" if self.miniatura else None,
            "format": self.formato,
            "width": self.largura,
            "height": self.altura,
            "duration_s": self.duracao_s,
            "size_bytes": self.tamanho_bytes,
            "owner_type": self.dono_tipo,
            "owner_id": self.dono_id,
            "parent_id": self.pai_id,
            "prompt": self.prompt,
            "technical_prompt": self.prompt_tecnico,
            "negative_prompt": self.negativo,
            "style": self.estilo,
            "seed": self.seed,
            "model": self.modelo,
            "metadata": self.metadados,
            "job_id": self.job_id,
            "created_at": self.criado_em,
        }


def _de_linha(linha: sqlite3.Row) -> Midia:
    return Midia(
        id=linha["id"],
        tipo=linha["tipo"],
        papel=linha["papel"],
        caminho=linha["caminho"],
        miniatura=linha["miniatura"],
        formato=linha["formato"],
        largura=linha["largura"],
        altura=linha["altura"],
        duracao_s=linha["duracao_s"],
        tamanho_bytes=int(linha["tamanho_bytes"] or 0),
        dono_tipo=linha["dono_tipo"],
        dono_id=linha["dono_id"],
        pai_id=linha["pai_id"],
        prompt=linha["prompt"],
        prompt_tecnico=linha["prompt_tecnico"],
        negativo=linha["negativo"],
        estilo=linha["estilo"],
        seed=linha["seed"],
        modelo=linha["modelo"],
        metadados=json.loads(linha["metadados"] or "{}"),
        job_id=linha["job_id"],
        criado_em=linha["criado_em"],
    )


class RepositorioMidias:
    def __init__(self, db: Database, raiz: Path) -> None:
        self._db = db
        self.raiz = raiz

    # --- caminhos ---------------------------------------------------------------------------------------------------
    def caminho_absoluto(self, midia: Midia) -> Path:
        return dentro_da_pasta(self.raiz, midia.caminho)

    def caminho_da_miniatura(self, midia: Midia) -> Path | None:
        return dentro_da_pasta(self.raiz, midia.miniatura) if midia.miniatura else None

    def _destino(self, tipo: str, id_: str, extensao: str) -> tuple[str, Path]:
        pasta = f"{tipo}/{datetime.now(UTC):%Y-%m}"
        relativo = f"{pasta}/{id_}.{extensao.lstrip('.').lower()}"
        absoluto = dentro_da_pasta(self.raiz, relativo)
        absoluto.parent.mkdir(parents=True, exist_ok=True)
        return relativo, absoluto

    # --- criação ----------------------------------------------------------------------------------------------------
    def adotar(
        self,
        origem: Path,
        *,
        tipo: str,
        papel: str,
        extensao: str | None = None,
        largura: int | None = None,
        altura: int | None = None,
        duracao_s: float | None = None,
        miniatura_de: Path | None = None,
        mover: bool = True,
        dono_tipo: str | None = None,
        dono_id: str | None = None,
        pai_id: str | None = None,
        prompt: str | None = None,
        prompt_tecnico: str | None = None,
        negativo: str | None = None,
        estilo: str | None = None,
        seed: int | None = None,
        modelo: str | None = None,
        metadados: dict[str, Any] | None = None,
        job_id: str | None = None,
    ) -> Midia:
        """Traz um arquivo já pronto (gerado num lugar temporário) para a biblioteca e o registra."""
        if tipo not in TIPOS:
            raise ValueError(f"tipo de mídia desconhecido: {tipo}")
        id_ = uuid.uuid4().hex
        ext = extensao or origem.suffix.lstrip(".") or "bin"
        relativo, destino = self._destino(tipo, id_, ext)
        if mover:
            shutil.move(str(origem), destino)
        else:
            shutil.copyfile(origem, destino)
        if tipo == "imagem" and (largura is None or altura is None):
            with Image.open(destino) as imagem:
                largura, altura = imagem.size
        miniatura = self._miniatura(destino, id_, miniatura_de or (destino if tipo == "imagem" else None))
        criado = _agora()
        with self._db.transaction() as c:
            c.execute(
                "INSERT INTO midias (id, tipo, papel, caminho, miniatura, formato, largura, altura, duracao_s, tamanho_bytes,"
                " dono_tipo, dono_id, pai_id, prompt, prompt_tecnico, negativo, estilo, seed, modelo, metadados, job_id, criado_em)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    id_,
                    tipo,
                    papel,
                    relativo,
                    miniatura,
                    ext.lower(),
                    largura,
                    altura,
                    duracao_s,
                    destino.stat().st_size,
                    dono_tipo,
                    dono_id,
                    pai_id,
                    prompt,
                    prompt_tecnico,
                    negativo,
                    estilo,
                    seed,
                    modelo,
                    json.dumps(metadados or {}, ensure_ascii=False),
                    job_id,
                    criado,
                ),
            )
        registrada = self.obter(id_)
        assert registrada is not None
        return registrada

    def _miniatura(self, destino: Path, id_: str, fonte: Path | None) -> str | None:
        """Miniatura em WebP (guarda a transparência dos recortes). Sem imagem de onde tirar, não há miniatura."""
        if fonte is None:
            return None
        relativo, caminho = self._destino("miniatura", id_, "webp")
        try:
            with Image.open(fonte) as imagem:
                imagem.thumbnail((LADO_DA_MINIATURA, LADO_DA_MINIATURA))
                imagem.convert("RGBA" if "A" in imagem.getbands() else "RGB").save(caminho, "WEBP", quality=82)
        except OSError:
            return None
        return relativo

    # --- consulta ---------------------------------------------------------------------------------------------------
    def obter(self, id_: str) -> Midia | None:
        with self._db.transaction() as c:
            linha = c.execute("SELECT * FROM midias WHERE id = ?", (id_,)).fetchone()
        return _de_linha(linha) if linha else None

    @staticmethod
    def _onde(
        tipo: str | None,
        papeis: tuple[str, ...],
        dono_tipo: str | None,
        dono_id: str | None,
        busca: str | None,
        pai_id: str | None,
    ) -> tuple[str, list[Any]]:
        condicoes: list[str] = []
        valores: list[Any] = []
        if tipo:
            condicoes.append("tipo = ?")
            valores.append(tipo)
        if papeis:
            condicoes.append(f"papel IN ({', '.join('?' for _ in papeis)})")
            valores.extend(papeis)
        if dono_tipo == SEM_DONO:  # as avulsas: geradas na página Gerar imagem ou enviadas, sem projeto nem personagem
            condicoes.append("dono_tipo IS NULL")
        elif dono_tipo:
            condicoes.append("dono_tipo = ?")
            valores.append(dono_tipo)
        if dono_id:
            condicoes.append("dono_id = ?")
            valores.append(dono_id)
        if pai_id:
            condicoes.append("pai_id = ?")
            valores.append(pai_id)
        if busca:
            condicoes.append("(prompt LIKE ? ESCAPE '\\' OR prompt_tecnico LIKE ? ESCAPE '\\')")
            padrao = "%" + busca.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            valores.extend([padrao, padrao])
        return (f"WHERE {' AND '.join(condicoes)}" if condicoes else ""), valores

    def listar(
        self,
        *,
        tipo: str | None = None,
        papeis: tuple[str, ...] = (),
        dono_tipo: str | None = None,
        dono_id: str | None = None,
        pai_id: str | None = None,
        busca: str | None = None,
        limite: int = 100,
        deslocamento: int = 0,
        mais_antigas_primeiro: bool = False,
    ) -> list[Midia]:
        onde, valores = self._onde(tipo, papeis, dono_tipo, dono_id, busca, pai_id)
        ordem = "ASC" if mais_antigas_primeiro else "DESC"
        with self._db.transaction() as c:
            linhas = c.execute(
                f"SELECT * FROM midias {onde} ORDER BY criado_em {ordem}, id {ordem} LIMIT ? OFFSET ?",  # só colunas fixas
                (*valores, limite, deslocamento),
            ).fetchall()
        return [_de_linha(linha) for linha in linhas]

    def atualizar_metadados(self, id_: str, **novos: Any) -> None:
        atual = self.obter(id_)
        if atual is None:
            return
        with self._db.transaction() as c:
            c.execute(
                "UPDATE midias SET metadados = ? WHERE id = ?",
                (json.dumps({**atual.metadados, **novos}, ensure_ascii=False), id_),
            )

    def atualizar_papel(self, id_: str, papel: str) -> None:
        with self._db.transaction() as c:
            c.execute("UPDATE midias SET papel = ? WHERE id = ?", (papel, id_))

    # --- remoção ----------------------------------------------------------------------------------------------------
    def remover(self, id_: str) -> bool:
        """Apaga o registro e os arquivos (a mídia e a miniatura). Devolve False se não existia."""
        midia = self.obter(id_)
        if midia is None:
            return False
        for relativo in (midia.caminho, midia.miniatura):
            if relativo:
                dentro_da_pasta(self.raiz, relativo).unlink(missing_ok=True)
        with self._db.transaction() as c:
            c.execute("DELETE FROM midias WHERE id = ?", (id_,))
        return True

    def remover_do_dono(self, dono_tipo: str, dono_id: str) -> int:
        removidas = 0
        for midia in self.listar(dono_tipo=dono_tipo, dono_id=dono_id, limite=10_000):
            removidas += int(self.remover(midia.id))
        return removidas

    def contar(
        self,
        *,
        tipo: str | None = None,
        papeis: tuple[str, ...] = (),
        dono_tipo: str | None = None,
        dono_id: str | None = None,
        pai_id: str | None = None,
        busca: str | None = None,
    ) -> int:
        onde, valores = self._onde(tipo, papeis, dono_tipo, dono_id, busca, pai_id)
        with self._db.transaction() as c:
            linha = c.execute(f"SELECT COUNT(*) AS n FROM midias {onde}", valores).fetchone()  # só colunas fixas
        return int(linha["n"])
