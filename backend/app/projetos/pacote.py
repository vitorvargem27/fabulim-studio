"""Pacote ``.fabulim`` (briefing, seção 2.7): levar um projeto, ou só personagens, de uma máquina para outra.

É um zip com ``manifest.json`` e os arquivos em ``media/``: enredo, roteiro, cenas com todas as versões, aprovações,
personagens (ficha, prompts, voz, imagens e PNG transparentes) e os cenários do storyboard. Nunca leva pesos de modelo.
Assim o roteiro e o storyboard são aprovados no notebook e o vídeo é renderizado no desktop.

Ao importar, **tudo é conferido**: estrutura do zip, tamanhos, nomes (nenhuma entrada sai da pasta), esquema do manifesto e o
tipo real de cada arquivo. Imagens são decodificadas e regravadas (sem metadados), vídeo passa pelo ffprobe, áudio e legenda
têm formato próprio. Todos os ids são refeitos e nada que já existe é sobrescrito: personagem com o mesmo nome vira
«Nome (importado)». Se algo falha no meio, o que já entrou é desfeito.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import uuid
import warnings
import wave
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..config import VERSAO
from ..erros import ErroParaOUsuario
from ..midias.repositorio import Midia
from ..midias.servico import adotar_e_avisar, remover_e_avisar
from ..motores.tipos import MotorFalhou
from ..personagens import fluxos
from ..personagens.repositorio import NomeEmUso, Personagem
from ..personagens.servico import voz_valida
from ..prompts.formatos import FichaPersonagem
from ..security.caminhos import CaminhoInseguro, entrada_de_pacote_segura
from ..security.uploads import MAX_PIXELS, tipo_real_da_imagem
from .cenas import DadosDaCena, cena_valida
from .repositorio import ETAPAS, Projeto

if TYPE_CHECKING:
    from ..container import Servicos

FORMATO = "fabulim"
VERSAO_DO_PACOTE = 1
EXTENSAO = ".fabulim"

LIMITE_DO_MANIFESTO = 8 * 1024 * 1024
LIMITE_TOTAL = 4 * 1024**3
LIMITE_DE_ENTRADAS = 6500
LIMITE_POR_TIPO = {
    "imagem": 60 * 1024 * 1024,
    "video": 700 * 1024 * 1024,
    "audio": 300 * 1024 * 1024,
    "legenda": 2 * 1024 * 1024,
}
EXTENSOES = {
    "imagem": frozenset({"png", "jpg", "jpeg", "webp"}),
    "video": frozenset({"mp4", "webm", "mov"}),
    "audio": frozenset({"wav"}),
    "legenda": frozenset({"srt"}),
}
RAZAO_MAXIMA_DE_COMPRESSAO = 250  # arquivos grandes que descompactam mais que isso são bomba de descompressão

ID = r"^[0-9a-f]{32}$"
PAPEL = r"^[a-z_]{1,30}$"
ENTRADA_DE_MIDIA = re.compile(r"^media/([0-9a-f]{32})\.(png|jpg|jpeg|webp|mp4|webm|mov|wav|srt)$")

PAPEIS_DO_PERSONAGEM = ("upload", "pose", "recorte")
PAPEIS_DA_CENA = ("fundo", "quadro")
PAPEIS_DO_PROJETO = ("fundo_ligacao", "quadro_final")
PAPEIS_DE_RENDER_DA_CENA = ("cena_clipe",)
PAPEIS_DE_RENDER_DO_PROJETO = ("musica", "mix", "legenda", "video_final", "thumbnail")
CHAVES_DOS_AJUSTES = ("fps", "transition", "narrator", "metadata")


class PacoteInvalido(ErroParaOUsuario):
    """O arquivo não é um pacote .fabulim válido (a mensagem diz o que está errado, em linguagem simples)."""


# --- o manifesto -----------------------------------------------------------------------------------------------------------
class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")  # campos novos de versões futuras não derrubam a leitura


class MidiaDoPacote(_Base):
    id: str = Field(pattern=ID)
    kind: Literal["imagem", "video", "audio", "legenda"]
    role: str = Field(pattern=PAPEL)
    file: str = Field(max_length=100)
    format: str | None = Field(default=None, max_length=10)
    width: int | None = Field(default=None, ge=1, le=20_000)
    height: int | None = Field(default=None, ge=1, le=20_000)
    duration_s: float | None = Field(default=None, ge=0, le=36_000)
    owner_type: Literal["personagem", "cena", "projeto"] | None = None
    owner_id: str | None = Field(default=None, pattern=ID)
    parent_id: str | None = Field(default=None, pattern=ID)
    prompt: str | None = Field(default=None, max_length=30_000)
    technical_prompt: str | None = Field(default=None, max_length=8_000)
    negative_prompt: str | None = Field(default=None, max_length=4_000)
    style: str | None = Field(default=None, max_length=10)
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    model: str | None = Field(default=None, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(max_length=40)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)

    @field_validator("metadata")
    @classmethod
    def _metadados_pequenos(cls, valor: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(valor, ensure_ascii=False)) > 20_000:
            raise ValueError("metadados grandes demais")
        return valor


class PersonagemDoPacote(_Base):
    id: str = Field(pattern=ID)
    name: str = Field(min_length=1, max_length=80)
    style: Literal["2D", "3D"]
    form: dict[str, Any]
    original_prompt: str = Field(default="", max_length=30_000)
    technical_prompt: str = Field(default="", max_length=4_000)
    voice: dict[str, Any] = Field(default_factory=dict)
    state: str = Field(default="rascunho", max_length=20)
    version: int = Field(default=1, ge=1, le=10_000)
    main_image_id: str | None = Field(default=None, pattern=ID)


class VersaoDaCena(_Base):
    version: int = Field(ge=1, le=100_000)
    data: dict[str, Any]
    reason: str = Field(default="", max_length=300)
    created_at: str = Field(default="", max_length=40)


class CenaDoPacote(_Base):
    id: str = Field(pattern=ID)
    order: int = Field(ge=1, le=500)
    data: dict[str, Any]
    status: str = Field(default="pendente", max_length=20)
    version: int = Field(default=1, ge=1, le=100_000)
    versions: list[VersaoDaCena] = Field(default_factory=list, max_length=300)


class ProjetoDoPacote(_Base):
    title: str = Field(min_length=1, max_length=160)
    format: Literal["short", "longo"]
    language: Literal["pt-BR", "en"]
    style: Literal["2D", "3D"]
    target_duration_s: int = Field(ge=1, le=3600)
    story: dict[str, Any] = Field(default_factory=dict)
    character_ids: list[str] = Field(default_factory=list, max_length=8)
    stage: str = Field(default="enredo", max_length=20)
    approvals: dict[str, bool] = Field(default_factory=dict)
    music: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)


class Manifesto(_Base):
    format: str
    version: int = Field(ge=1)
    kind: Literal["project", "characters"]
    app_version: str = Field(default="", max_length=40)
    exported_at: str = Field(default="", max_length=40)
    profile: str | None = Field(default=None, max_length=2)
    includes_renders: bool = False
    project: ProjetoDoPacote | None = None
    scenes: list[CenaDoPacote] = Field(default_factory=list, max_length=500)
    characters: list[PersonagemDoPacote] = Field(default_factory=list, max_length=200)
    media: list[MidiaDoPacote] = Field(default_factory=list, max_length=6000)


# --- relatórios ------------------------------------------------------------------------------------------------------------
@dataclass
class RelatorioDeExportacao:
    arquivo: Path
    kind: str
    midias: int
    tamanho_bytes: int
    avisos: list[str] = field(default_factory=list)


@dataclass
class RelatorioDeImportacao:
    kind: str
    projeto_id: str | None = None
    personagens: list[dict[str, Any]] = field(default_factory=list)
    cenas: int = 0
    midias: int = 0
    avisos: list[str] = field(default_factory=list)

    def para_api(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "project_id": self.projeto_id,
            "characters": self.personagens,
            "scenes": self.cenas,
            "media": self.midias,
            "warnings": self.avisos,
        }


def _agora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# =========================================================================================================================
# exportar
# =========================================================================================================================
def _sha256_e_tamanho(caminho: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    total = 0
    with caminho.open("rb") as arquivo:
        for pedaco in iter(lambda: arquivo.read(1024 * 1024), b""):
            h.update(pedaco)
            total += len(pedaco)
    return h.hexdigest(), total


def _midias_do_personagem(sv: Servicos, personagem: Personagem, *, todas_as_variacoes: bool) -> list[Midia]:
    papeis = (*PAPEIS_DO_PERSONAGEM, *(("variacao",) if todas_as_variacoes else ()))
    achadas = {
        m.id: m for m in sv.midias.listar(papeis=papeis, dono_tipo="personagem", dono_id=personagem.id, limite=5000)
    }
    if personagem.imagem_principal_id and personagem.imagem_principal_id not in achadas:
        principal = sv.midias.obter(personagem.imagem_principal_id)
        if principal is not None:
            achadas[principal.id] = principal
    return list(achadas.values())


def _ajustes_para_exportar(projeto: Projeto, *, renders: bool) -> dict[str, Any]:
    """Só o que faz sentido levar: o que o usuário ajustou (e, com renders, as referências ao que foi gerado)."""
    origem = projeto.configuracoes
    saida: dict[str, Any] = {k: origem[k] for k in CHAVES_DOS_AJUSTES if k in origem}
    if "voices" in origem:
        saida["voices"] = origem["voices"]
    if renders:
        for chave in ("final_media_id", "audio", "quality"):
            if chave in origem:
                saida[chave] = origem[chave]
    return saida


def _grava_no_zip(zf: zipfile.ZipFile, midia: Midia, caminho: Path) -> tuple[str, int, str]:
    extensao = (midia.formato or caminho.suffix.lstrip(".") or "bin").lower()
    entrada = f"media/{midia.id}.{extensao}"
    agora = datetime.now(UTC)
    info = zipfile.ZipInfo(
        entrada, date_time=(agora.year, agora.month, agora.day, agora.hour, agora.minute, agora.second)
    )
    info.compress_type = zipfile.ZIP_STORED  # imagens, vídeos e áudio já vêm comprimidos
    h = hashlib.sha256()
    total = 0
    with caminho.open("rb") as origem, zf.open(info, "w", force_zip64=True) as saida:
        for pedaco in iter(lambda: origem.read(1024 * 1024), b""):
            h.update(pedaco)
            total += len(pedaco)
            saida.write(pedaco)
    return entrada, total, h.hexdigest()


def _manifesto_da_midia(midia: Midia, entrada: str, tamanho: int, sha: str) -> dict[str, Any]:
    api = midia.para_api()
    return {
        "id": midia.id,
        "kind": midia.tipo,
        "role": midia.papel,
        "file": entrada,
        "format": api["format"],
        "width": api["width"],
        "height": api["height"],
        "duration_s": api["duration_s"],
        "owner_type": midia.dono_tipo,
        "owner_id": midia.dono_id,
        "parent_id": midia.pai_id,
        "prompt": midia.prompt,
        "technical_prompt": midia.prompt_tecnico,
        "negative_prompt": midia.negativo,
        "style": midia.estilo,
        "seed": midia.seed,
        "model": midia.modelo,
        "metadata": midia.metadados,
        "created_at": midia.criado_em,
        "sha256": sha,
        "size": tamanho,
    }


def _personagem_do_manifesto(p: Personagem) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.nome,
        "style": p.estilo,
        "form": p.ficha,
        "original_prompt": p.prompt_original,
        "technical_prompt": p.prompt_tecnico,
        "voice": p.voz,
        "state": p.estado,
        "version": p.versao,
        "main_image_id": p.imagem_principal_id,
    }


def _escrever_pacote(
    sv: Servicos, destino: Path, manifesto: dict[str, Any], midias: list[Midia], avisos: list[str]
) -> RelatorioDeExportacao:
    destino.parent.mkdir(parents=True, exist_ok=True)
    registros: list[dict[str, Any]] = []
    with zipfile.ZipFile(destino, "w", allowZip64=True) as zf:
        for midia in sorted(midias, key=lambda m: (m.criado_em, m.id)):
            try:
                caminho = sv.midias.caminho_absoluto(midia)
            except CaminhoInseguro:
                avisos.append(f"Um arquivo com caminho inválido ficou de fora ({midia.papel}).")
                continue
            if not caminho.is_file():
                avisos.append(f"O arquivo de uma mídia ({midia.papel}) não está mais no disco e ficou de fora.")
                continue
            entrada, tamanho, sha = _grava_no_zip(zf, midia, caminho)
            registros.append(_manifesto_da_midia(midia, entrada, tamanho, sha))
        manifesto["media"] = registros
        zf.writestr(
            "manifest.json", json.dumps(manifesto, ensure_ascii=False, indent=1), compress_type=zipfile.ZIP_DEFLATED
        )
    return RelatorioDeExportacao(destino, str(manifesto["kind"]), len(registros), destino.stat().st_size, avisos)


def _perfil_atual(sv: Servicos) -> str | None:
    try:
        perfil = sv.hardware.snapshot().get("profile") or {}
        letra = perfil.get("letter")
        return str(letra) if letra else None
    except Exception:
        return None


def exportar_projeto(sv: Servicos, projeto: Projeto, destino: Path, *, renders: bool = False) -> RelatorioDeExportacao:
    """Grava o projeto em ``destino``. ``renders`` leva também os clipes, o áudio, o vídeo final e as miniaturas."""
    avisos: list[str] = []
    cenas = sv.projetos.cenas(projeto.id)
    personagens = [p for i in projeto.personagens if (p := sv.personagens.obter(i)) is not None]
    midias: dict[str, Midia] = {}
    for personagem in personagens:
        for m in _midias_do_personagem(sv, personagem, todas_as_variacoes=False):
            midias[m.id] = m
    papeis_da_cena = (*PAPEIS_DA_CENA, *(PAPEIS_DE_RENDER_DA_CENA if renders else ()))
    for cena in cenas:
        for m in sv.midias.listar(papeis=papeis_da_cena, dono_tipo="cena", dono_id=cena.id, limite=2000):
            midias[m.id] = m
    papeis_do_projeto = (*PAPEIS_DO_PROJETO, *(PAPEIS_DE_RENDER_DO_PROJETO if renders else ()))
    for m in sv.midias.listar(papeis=papeis_do_projeto, dono_tipo="projeto", dono_id=projeto.id, limite=2000):
        midias[m.id] = m
    manifesto: dict[str, Any] = {
        "format": FORMATO,
        "version": VERSAO_DO_PACOTE,
        "kind": "project",
        "app_version": VERSAO,
        "exported_at": _agora(),
        "profile": _perfil_atual(sv),
        "includes_renders": renders,
        "project": {
            "title": projeto.titulo,
            "format": projeto.formato,
            "language": projeto.idioma,
            "style": projeto.estilo,
            "target_duration_s": projeto.duracao_alvo_s,
            "story": projeto.enredo,
            "character_ids": projeto.personagens,
            "stage": projeto.etapa,
            "approvals": projeto.aprovacoes,
            "music": projeto.musica,
            "settings": _ajustes_para_exportar(projeto, renders=renders),
        },
        "scenes": [
            {
                "id": cena.id,
                "order": cena.ordem,
                "data": cena.dados,
                "status": cena.status,
                "version": cena.versao,
                "versions": sv.projetos.versoes_da_cena(cena.id),
            }
            for cena in cenas
        ],
        "characters": [_personagem_do_manifesto(p) for p in personagens],
    }
    faltando = [i for i in projeto.personagens if sv.personagens.obter(i) is None]
    if faltando:
        avisos.append(f"{len(faltando)} personagem(ns) do projeto não estão mais na biblioteca e ficaram de fora.")
    return _escrever_pacote(sv, destino, manifesto, list(midias.values()), avisos)


def exportar_personagens(
    sv: Servicos, personagens: list[Personagem], destino: Path, *, todas_as_variacoes: bool = True
) -> RelatorioDeExportacao:
    """A biblioteca de personagens (todos ou os escolhidos) sozinha, sem projeto."""
    midias: dict[str, Midia] = {}
    for personagem in personagens:
        for m in _midias_do_personagem(sv, personagem, todas_as_variacoes=todas_as_variacoes):
            midias[m.id] = m
    manifesto: dict[str, Any] = {
        "format": FORMATO,
        "version": VERSAO_DO_PACOTE,
        "kind": "characters",
        "app_version": VERSAO,
        "exported_at": _agora(),
        "profile": _perfil_atual(sv),
        "includes_renders": False,
        "characters": [_personagem_do_manifesto(p) for p in personagens],
    }
    return _escrever_pacote(sv, destino, manifesto, list(midias.values()), [])


# =========================================================================================================================
# importar
# =========================================================================================================================
def _abrir_e_conferir_o_zip(arquivo: Path) -> zipfile.ZipFile:
    if not zipfile.is_zipfile(arquivo):
        raise PacoteInvalido("O arquivo não é um pacote .fabulim (não é um zip válido).")
    try:
        zf = zipfile.ZipFile(arquivo)
    except (zipfile.BadZipFile, OSError) as exc:
        raise PacoteInvalido("O pacote está corrompido e não pôde ser aberto.") from exc
    try:
        infos = zf.infolist()
        if len(infos) > LIMITE_DE_ENTRADAS:
            raise PacoteInvalido("O pacote tem arquivos demais.")
        vistos: set[str] = set()
        total = 0
        for info in infos:
            if info.is_dir():
                continue
            try:
                nome = entrada_de_pacote_segura(info.filename)
            except CaminhoInseguro as exc:
                raise PacoteInvalido(f"O pacote tem um nome de arquivo perigoso e foi recusado ({exc}).") from exc
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise PacoteInvalido("O pacote tem um link simbólico e foi recusado.")
            if nome != "manifest.json" and not ENTRADA_DE_MIDIA.match(nome):
                raise PacoteInvalido(f"O pacote tem um arquivo que não faz parte do formato: {nome[:60]!r}.")
            if nome in vistos:
                raise PacoteInvalido("O pacote repete o mesmo arquivo duas vezes.")
            vistos.add(nome)
            total += info.file_size
            if total > LIMITE_TOTAL:
                raise PacoteInvalido("O pacote descompactado é grande demais (limite de 4 GB).")
            if info.file_size > 10 * 1024 * 1024 and info.file_size > RAZAO_MAXIMA_DE_COMPRESSAO * max(
                info.compress_size, 1
            ):
                raise PacoteInvalido(
                    "O pacote tem um arquivo com compressão suspeita (possível bomba de descompressão)."
                )
        if "manifest.json" not in vistos:
            raise PacoteInvalido("O pacote não tem o manifest.json.")
        return zf
    except BaseException:
        zf.close()
        raise


def _ler_manifesto(zf: zipfile.ZipFile) -> Manifesto:
    info = zf.getinfo("manifest.json")
    if info.file_size > LIMITE_DO_MANIFESTO:
        raise PacoteInvalido("O manifest.json é grande demais.")
    try:
        with zf.open(info) as arquivo:
            bruto = arquivo.read(LIMITE_DO_MANIFESTO + 1)
        if len(bruto) > LIMITE_DO_MANIFESTO:
            raise PacoteInvalido("O manifest.json é grande demais.")
        dados = json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise PacoteInvalido("O manifest.json está corrompido ou não é um JSON válido.") from exc
    if not isinstance(dados, dict) or dados.get("format") != FORMATO:
        raise PacoteInvalido("Este arquivo não é um pacote do Fabulim (.fabulim).")
    try:
        manifesto = Manifesto.model_validate(dados)
    except ValidationError as exc:
        primeiro = exc.errors()[0]
        campo = ".".join(str(p) for p in primeiro["loc"])
        raise PacoteInvalido(f"O manifesto tem um campo inválido («{campo}»: {primeiro['msg']}).") from exc
    if manifesto.version > VERSAO_DO_PACOTE:
        raise PacoteInvalido(
            f"Este pacote vem de uma versão mais nova do Fabulim (formato {manifesto.version}). Atualize o estúdio para importar."
        )
    return manifesto


def _conferir_referencias(zf: zipfile.ZipFile, m: Manifesto) -> None:
    ids_de_personagens = {p.id for p in m.characters}
    ids_de_cenas = {c.id for c in m.scenes}
    ids_de_midias: set[str] = set()
    nomes = {entrada_de_pacote_segura(i.filename) for i in zf.infolist() if not i.is_dir()}
    for midia in m.media:
        if midia.id in ids_de_midias:
            raise PacoteInvalido("O manifesto repete o mesmo id de mídia.")
        ids_de_midias.add(midia.id)
        achou = ENTRADA_DE_MIDIA.match(midia.file)
        if achou is None or achou.group(1) != midia.id:
            raise PacoteInvalido("O manifesto aponta para um arquivo com nome fora do formato.")
        if achou.group(2) not in EXTENSOES[midia.kind]:
            raise PacoteInvalido(f"A extensão .{achou.group(2)} não é aceita para {midia.kind}.")
        if midia.file not in nomes:
            raise PacoteInvalido("O manifesto cita um arquivo que não está no pacote.")
        info = zf.getinfo(midia.file)
        if info.file_size != midia.size or info.file_size > LIMITE_POR_TIPO[midia.kind]:
            raise PacoteInvalido("O tamanho de um arquivo não bate com o manifesto (ou passa do limite do tipo).")
    if nomes - {"manifest.json"} - {midia.file for midia in m.media}:
        raise PacoteInvalido("O pacote tem arquivos que o manifesto não cita.")
    if len(ids_de_personagens) != len(m.characters) or len(ids_de_cenas) != len(m.scenes):
        raise PacoteInvalido("O manifesto repete ids de personagem ou de cena.")
    if m.kind == "project":
        if m.project is None:
            raise PacoteInvalido("O pacote de projeto não tem os dados do projeto.")
        if m.project.stage not in ETAPAS or any(e not in ETAPAS for e in m.project.approvals):
            raise PacoteInvalido("O projeto cita uma etapa que não existe.")
    for midia in m.media:
        if midia.owner_type == "personagem" and midia.owner_id not in ids_de_personagens:
            raise PacoteInvalido("Uma mídia pertence a um personagem que não está no pacote.")
        if midia.owner_type == "cena" and midia.owner_id not in ids_de_cenas:
            raise PacoteInvalido("Uma mídia pertence a uma cena que não está no pacote.")


def _reencodar_imagem(dados: bytes, extensao: str, destino: Path) -> tuple[int, int]:
    """Decodifica de verdade e regrava a imagem no mesmo formato, sem metadados. O tipo real tem de bater com a extensão."""
    tipo = tipo_real_da_imagem(dados)
    esperado = {"png": "png", "jpg": "jpeg", "jpeg": "jpeg", "webp": "webp"}[extensao]
    if tipo != esperado:
        raise PacoteInvalido(f"Um arquivo .{extensao} do pacote não é uma imagem {esperado.upper()} de verdade.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(dados)) as original:
                if original.width * original.height > MAX_PIXELS:
                    raise PacoteInvalido("Uma imagem do pacote tem pixels demais.")
                original.load()
                com_alfa = "A" in original.getbands() or "transparency" in original.info
                limpa = original.convert("RGBA" if com_alfa else "RGB")
    except PacoteInvalido:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise PacoteInvalido("Uma imagem do pacote está corrompida.") from exc
    destino.parent.mkdir(parents=True, exist_ok=True)
    if extensao in ("jpg", "jpeg"):
        limpa.convert("RGB").save(destino, "JPEG", quality=92)
    elif extensao == "webp":
        limpa.save(destino, "WEBP", quality=92)
    else:
        limpa.save(destino, "PNG")
    return limpa.size


def _conferir_wav(caminho: Path) -> float:
    try:
        with wave.open(str(caminho), "rb") as onda:
            canais, taxa, quadros = onda.getnchannels(), onda.getframerate(), onda.getnframes()
    except (wave.Error, EOFError, OSError) as exc:
        raise PacoteInvalido("Um áudio do pacote não é um WAV válido.") from exc
    if canais not in (1, 2) or not 8000 <= taxa <= 96_000 or quadros <= 0:
        raise PacoteInvalido("Um áudio do pacote tem formato fora do aceito.")
    return quadros / taxa


def _conferir_legenda(caminho: Path) -> None:
    try:
        texto = caminho.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PacoteInvalido("Um arquivo de legenda do pacote não é texto UTF-8.") from exc
    if "\x00" in texto:
        raise PacoteInvalido("Um arquivo de legenda do pacote tem bytes inválidos.")


def _extrair_e_validar(
    sv: Servicos, zf: zipfile.ZipFile, midia: MidiaDoPacote, pasta: Path
) -> tuple[Path, dict[str, Any]]:
    """Extrai uma mídia para a pasta temporária e confere o tipo real. Devolve (arquivo pronto, campos medidos)."""
    extensao = ENTRADA_DE_MIDIA.match(midia.file).group(2)  # type: ignore[union-attr]  # já conferido antes
    bruto = pasta / f"{midia.id}.bruto"
    h = hashlib.sha256()
    total = 0
    with zf.open(midia.file) as origem, bruto.open("wb") as saida:
        for pedaco in iter(lambda: origem.read(1024 * 1024), b""):
            total += len(pedaco)
            if total > LIMITE_POR_TIPO[midia.kind]:
                raise PacoteInvalido("Um arquivo do pacote passou do tamanho permitido.")
            h.update(pedaco)
            saida.write(pedaco)
    if h.hexdigest() != midia.sha256:
        raise PacoteInvalido("Um arquivo do pacote está corrompido (a soma de verificação não bate).")
    if midia.kind == "imagem":
        pronto = pasta / f"{midia.id}.{extensao}"
        largura, altura = _reencodar_imagem(bruto.read_bytes(), extensao, pronto)
        bruto.unlink(missing_ok=True)
        return pronto, {"largura": largura, "altura": altura, "extensao": extensao}
    if midia.kind == "video":
        pronto = pasta / f"{midia.id}.{extensao}"
        bruto.replace(pronto)
        if sv.motores.ffmpeg.indisponivel():
            raise PacoteInvalido("Sem o ffmpeg não dá para conferir os vídeos do pacote.")
        try:
            sonda = sv.motores.ffmpeg.sondar(pronto)
        except MotorFalhou as exc:
            raise PacoteInvalido(f"Um vídeo do pacote não abre como vídeo de verdade: {exc}") from exc
        if not sonda.tem_video or not sonda.largura or not sonda.altura or not 0.1 <= sonda.duracao_s <= 3600:
            raise PacoteInvalido("Um vídeo do pacote tem formato ou duração fora do aceito.")
        return pronto, {
            "largura": sonda.largura,
            "altura": sonda.altura,
            "duracao_s": sonda.duracao_s,
            "extensao": extensao,
        }
    pronto = pasta / f"{midia.id}.{extensao}"
    bruto.replace(pronto)
    if midia.kind == "audio":
        return pronto, {"duracao_s": _conferir_wav(pronto), "extensao": extensao}
    _conferir_legenda(pronto)
    return pronto, {"extensao": extensao}


def _nome_livre(sv: Servicos, nome: str, estilo: str) -> str:
    """«Lila» → «Lila (importado)», «Lila (importado 2)»... (nunca sobrescreve nem funde com quem já existe)."""

    def existe(candidato: str) -> bool:
        return any(p.estilo == estilo for p in sv.personagens.por_nome(candidato))

    if not existe(nome):
        return nome
    for n in range(1, 200):
        candidato = f"{nome} (importado)" if n == 1 else f"{nome} (importado {n})"
        if not existe(candidato):
            return candidato[:80]
    raise PacoteInvalido("Há personagens demais com esse nome na biblioteca.")


def _ficha_valida(p: PersonagemDoPacote, nome: str) -> FichaPersonagem:
    try:
        return FichaPersonagem.model_validate({**p.form, "name": nome, "style": p.style})
    except ValidationError as exc:
        raise PacoteInvalido(f"A ficha do personagem «{p.name[:40]}» é inválida.") from exc


def _voz_do_pacote(voz: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return voz_valida(dict(voz))
    except (ValueError, TypeError):
        return None  # voz que esta versão não conhece: o cadastro usa a padrão


def _remapear_cena(
    dados: dict[str, Any], personagens: dict[str, str], midias: dict[str, str], *, com_renders: bool = True
) -> dict[str, Any]:
    cena = DadosDaCena.model_validate(dados).model_dump()
    cena["characters"] = [personagens[i] for i in cena["characters"] if i in personagens]
    cena["dialogue"] = [
        {"character_id": personagens.get(f["character_id"]) if f["character_id"] else None, "text": f["text"]}
        for f in cena["dialogue"]
    ]
    if cena["layout"]:
        cena["layout"] = [
            {**i, "personagem_id": personagens[i["personagem_id"]]}
            for i in cena["layout"]
            if i.get("personagem_id") in personagens
        ]
    aprovada = dict(cena["approved"])
    fundo = cena["background"]
    cena["background"] = (
        {**fundo, "media_id": midias[fundo["media_id"]]} if fundo and fundo["media_id"] in midias else None
    )
    if cena["background"] is None:
        aprovada.pop("storyboard", None)  # sem cenário não há o que estar aprovado
    cena["candidates"] = [midias[i] for i in cena["candidates"] if i in midias]
    cena["keyframe_media_id"] = midias.get(cena["keyframe_media_id"] or "")
    clipe = cena["clip"]
    if com_renders and clipe and clipe["media_id"] in midias:
        cena["clip"] = {**clipe, "media_id": midias[clipe["media_id"]]}
    else:
        cena["clip"] = None
        cena["timeline"] = None
        aprovada.pop("animacao", None)
    cena["approved"] = aprovada
    return DadosDaCena.model_validate(cena).model_dump()


def _remapear_ajustes(ajustes: dict[str, Any], personagens: dict[str, str], midias: dict[str, str]) -> dict[str, Any]:
    saida: dict[str, Any] = {k: ajustes[k] for k in CHAVES_DOS_AJUSTES if k in ajustes}
    if isinstance(ajustes.get("voices"), dict):
        saida["voices"] = {personagens[k]: v for k, v in ajustes["voices"].items() if k in personagens}
    if ajustes.get("final_media_id") in midias:
        saida["final_media_id"] = midias[ajustes["final_media_id"]]
        if "quality" in ajustes:
            saida["quality"] = ajustes["quality"]
    audio = ajustes.get("audio")
    if isinstance(audio, dict):
        novo = {k: v for k, v in audio.items() if not k.endswith("_media_id")}
        for chave in ("mix_media_id", "music_media_id", "srt_media_id"):
            if audio.get(chave) in midias:
                novo[chave] = midias[audio[chave]]
        if "mix_media_id" in novo:
            saida["audio"] = novo
    return saida


def _etapas_depois_de_importar(
    aprovacoes: dict[str, bool], etapa: str, *, trouxe_os_renders: bool, avisos: list[str]
) -> tuple[dict[str, bool], str]:
    """Sem os clipes, o áudio e o vídeo no pacote, a animação e o que vem depois voltam a «não aprovada» (serão refeitos aqui)."""
    if trouxe_os_renders:
        return dict(aprovacoes), etapa
    primeira = ETAPAS.index("animacao")
    depois = set(ETAPAS[primeira:])
    perdeu = any(aprovacoes.get(e) for e in depois) or ETAPAS.index(etapa) > primeira
    if perdeu:
        avisos.append(
            "O pacote não traz os vídeos e o áudio já gerados: as etapas de animação, áudio e montagem voltaram a "
            "«não aprovada» e serão refeitas nesta máquina."
        )
    novas = {k: v for k, v in aprovacoes.items() if k not in depois}
    return novas, ("animacao" if ETAPAS.index(etapa) > primeira else etapa)


def _notas_da_maquina(sv: Servicos, m: Manifesto) -> list[str]:
    """Recalcula o que muda nesta máquina (briefing 2.7): perfil diferente e o que não roda aqui."""
    notas: list[str] = []
    atual = _perfil_atual(sv)
    if m.profile and atual and m.profile != atual:
        notas.append(
            f"O pacote foi exportado de uma máquina de perfil {m.profile}; esta é de perfil {atual}. "
            "Veja em Status › Sua máquina o que muda."
        )
    try:
        capacidades = sv.hardware.snapshot().get("capabilities") or []
    except Exception:
        capacidades = []
    precisa = ("imagem", "voz", "animacao_cena", "montagem")
    for cap in capacidades:
        if cap.get("id") in precisa and cap.get("state") == "unavailable":
            notas.append(f"«{cap.get('name')}» não está disponível aqui: {cap.get('reason')}")
        elif cap.get("id") in ("imagem", "animacao_cena") and cap.get("state") == "slow":
            notas.append(f"«{cap.get('name')}» é lenta nesta máquina: {cap.get('reason')}")
    for motor, motivo in sv.motores.indisponiveis().items():
        notas.append(f"Sem o motor «{motor}» aqui: {motivo}")
    return notas


def importar_pacote(sv: Servicos, arquivo: Path) -> RelatorioDeImportacao:
    """Importa o pacote (projeto ou personagens). Nada existente é alterado; se algo falha, o que entrou é desfeito."""
    zf = _abrir_e_conferir_o_zip(arquivo)
    criadas: list[str] = []  # ids de mídia
    personagens_criados: list[str] = []
    projeto_criado: str | None = None
    pasta = sv.settings.temp_dir / f"importar-{uuid.uuid4().hex}"
    pasta.mkdir(parents=True, exist_ok=True)
    try:
        with zf:
            manifesto = _ler_manifesto(zf)
            _conferir_referencias(zf, manifesto)
            relatorio = RelatorioDeImportacao(kind=manifesto.kind)
            mapa_personagens: dict[str, str] = {}
            # 1. personagens (nomes livres, fichas validadas)
            for p in manifesto.characters:
                nome = _nome_livre(sv, p.name, p.style)
                ficha = _ficha_valida(p, nome)
                voz = _voz_do_pacote(p.voice)
                try:
                    novo = sv.personagens.criar(
                        nome,
                        p.style,
                        ficha.model_dump(),
                        prompt_original=p.original_prompt,
                        prompt_tecnico=p.technical_prompt,
                        voz=voz,
                        origem="importado",
                        estado=p.state,
                        versao=p.version,
                    )
                except NomeEmUso as exc:  # corrida improvável: outro pedido criou o mesmo nome agora
                    raise PacoteInvalido(str(exc)) from exc
                personagens_criados.append(novo.id)
                mapa_personagens[p.id] = novo.id
                relatorio.personagens.append(
                    {"id": novo.id, "name": novo.nome, "renamed_from": p.name if novo.nome != p.name else None}
                )
                if novo.nome != p.name:
                    relatorio.avisos.append(
                        f"«{p.name}» já existia na biblioteca: o personagem importado ficou como «{novo.nome}»."
                    )
            # 2. projeto e cenas
            mapa_cenas: dict[str, str] = {}
            projeto: Projeto | None = None
            if manifesto.kind == "project" and manifesto.project is not None:
                pj = manifesto.project
                projeto = sv.projetos.criar(
                    pj.title,
                    pj.format,
                    pj.language,
                    pj.style,
                    pj.target_duration_s,
                    pj.story,
                    [mapa_personagens[i] for i in pj.character_ids if i in mapa_personagens],
                    musica=pj.music,
                )
                projeto_criado = projeto.id
                relatorio.projeto_id = projeto.id
                for c in sorted(manifesto.scenes, key=lambda x: x.order):
                    try:
                        cena_valida(c.data)
                        for v in c.versions:
                            cena_valida(v.data)
                    except ValueError as exc:
                        raise PacoteInvalido(f"A cena {c.order} do pacote é inválida: {exc}") from exc
                    nova = sv.projetos.importar_cena(
                        projeto.id,
                        c.order,
                        c.data,
                        [v.model_dump() for v in c.versions],
                        c.version,
                        status=c.status,
                    )
                    mapa_cenas[c.id] = nova.id
                relatorio.cenas = len(manifesto.scenes)
            # 3. mídias, na ordem em que foram criadas (a «mais nova» de cada pose continua sendo a mais nova)
            mapa_midias: dict[str, str] = {}
            ffmpeg_ausente = False
            for midia in sorted(manifesto.media, key=lambda x: (x.created_at, x.id)):
                if midia.kind == "video" and sv.motores.ffmpeg.indisponivel():
                    ffmpeg_ausente = True
                    continue
                pronto, medido = _extrair_e_validar(sv, zf, midia, pasta)
                dono_tipo, dono_id = midia.owner_type, None
                if midia.owner_type == "personagem":
                    dono_id = mapa_personagens.get(midia.owner_id or "")
                elif midia.owner_type == "cena":
                    dono_id = mapa_cenas.get(midia.owner_id or "")
                elif midia.owner_type == "projeto":
                    dono_id = relatorio.projeto_id
                if midia.owner_type and dono_id is None:
                    continue  # o dono não veio (por exemplo, mídia de projeto num pacote só de personagens)
                registrada = adotar_e_avisar(
                    sv,
                    pronto,
                    tipo=midia.kind,
                    papel=midia.role,
                    extensao=medido["extensao"],
                    largura=medido.get("largura"),
                    altura=medido.get("altura"),
                    duracao_s=medido.get("duracao_s"),
                    dono_tipo=dono_tipo,
                    dono_id=dono_id,
                    pai_id=mapa_midias.get(midia.parent_id or ""),
                    prompt=midia.prompt,
                    prompt_tecnico=midia.technical_prompt,
                    negativo=midia.negative_prompt,
                    estilo=midia.style,
                    seed=midia.seed,
                    modelo=midia.model,
                    metadados={
                        **midia.metadata,
                        "imported_from": midia.id,
                        **({"project_id": relatorio.projeto_id} if midia.owner_type == "cena" else {}),
                    },
                )
                criadas.append(registrada.id)
                mapa_midias[midia.id] = registrada.id
            relatorio.midias = len(mapa_midias)
            if ffmpeg_ausente:
                relatorio.avisos.append("Os vídeos do pacote não foram importados: o ffmpeg não está instalado.")
            # 4. amarrar tudo: imagem principal dos personagens e as referências dentro das cenas e do projeto
            for p in manifesto.characters:
                novo_id = mapa_personagens[p.id]
                principal = mapa_midias.get(p.main_image_id or "")
                if principal:
                    sv.personagens.definir_imagem_principal(novo_id, principal)
            if projeto is not None and manifesto.project is not None:
                com_renders = manifesto.includes_renders and not ffmpeg_ausente
                for cena_antiga in manifesto.scenes:
                    nova_id = mapa_cenas[cena_antiga.id]
                    atual = sv.projetos.cena(nova_id)
                    assert atual is not None
                    sv.projetos.atualizar_cena_sem_versao(
                        nova_id, _remapear_cena(atual.dados, mapa_personagens, mapa_midias, com_renders=com_renders)
                    )
                    sv.projetos.atualizar_versoes_da_cena(
                        nova_id,
                        lambda d: _remapear_cena(d, mapa_personagens, mapa_midias, com_renders=com_renders),
                    )
                ajustes = _remapear_ajustes(manifesto.project.settings, mapa_personagens, mapa_midias)
                aprovacoes, etapa = _etapas_depois_de_importar(
                    manifesto.project.approvals,
                    manifesto.project.stage,
                    trouxe_os_renders=com_renders,
                    avisos=relatorio.avisos,
                )
                sv.projetos.atualizar(projeto.id, configuracoes=ajustes, aprovacoes=aprovacoes, etapa=etapa)
            relatorio.avisos.extend(_notas_da_maquina(sv, manifesto))
            return relatorio
    except BaseException:
        for id_ in criadas:
            remover_e_avisar(sv, id_)
        if projeto_criado:
            sv.projetos.remover(projeto_criado)
        for id_ in personagens_criados:
            sv.personagens.remover(id_)
        raise
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def resumo_dos_personagens(sv: Servicos, ids: list[str]) -> list[dict[str, Any]]:
    """Os personagens recém-importados no formato da biblioteca (para a interface abrir o primeiro)."""
    saida: list[dict[str, Any]] = []
    for id_ in ids:
        personagem = sv.personagens.obter(id_)
        if personagem is not None:
            saida.append(fluxos.resumo(sv, personagem))
    return saida
