"""Saúde dos serviços para a página Status: cada um com estado, detalhe e instrução de como corrigir."""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from ..config import VERSAO
from ..ferramentas.detectar import MOTORES, pendencias, tem_modulo
from ..hardware.perfil import obter
from .ollama import OllamaIndisponivel

if TYPE_CHECKING:
    from ..container import Servicos

DISCO_ERRO_GB = 20
DISCO_AVISO_GB = 100


class EstadoServico(StrEnum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    INACTIVE = "inactive"  # opcional ou ainda não instalado: não conta como problema


class ServicoStatus(BaseModel):
    id: str
    name: str
    state: EstadoServico
    summary: str
    detail: str | None = None
    version: str | None = None
    how_to_fix: list[str] = Field(default_factory=list)
    log_service: str | None = None


class RelatorioStatus(BaseModel):
    overall: EstadoServico
    services: list[ServicoStatus]
    generated_at: str


def _gb(valor_mb: float) -> str:
    return f"{valor_mb / 1024:.1f}".replace(".", ",") + " GB"


def _backend(sv: Servicos) -> ServicoStatus:
    decorrido = int(time.monotonic() - sv.inicio)
    return ServicoStatus(
        id="backend",
        name="Servidor do Fabulim",
        state=EstadoServico.OK,
        version=VERSAO,
        summary=f"Escutando em {sv.settings.host}:{sv.settings.port}",
        detail=f"No ar há {decorrido // 60} min {decorrido % 60} s.",
        log_service="app",
    )


def _banco(sv: Servicos) -> ServicoStatus:
    try:
        with sv.db.transaction() as c:
            versao = c.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]
        return ServicoStatus(
            id="database",
            name="Banco de dados (SQLite)",
            state=EstadoServico.OK,
            version=f"esquema {versao}",
            summary="Respondendo",
            detail=f"{sv.db.tamanho_bytes() / 1024:.0f} KB em {sv.settings.db_path.name}",
        )
    except Exception as exc:  # o banco pode falhar de muitas formas; o usuário só precisa do resumo
        return ServicoStatus(
            id="database",
            name="Banco de dados (SQLite)",
            state=EstadoServico.ERROR,
            summary="Não respondeu",
            detail=str(exc),
            how_to_fix=[
                "Confira se a pasta de dados existe e tem permissão de escrita.",
                "Se o arquivo estiver corrompido, feche o app e renomeie fabulim.db (o app cria um novo).",
            ],
        )


def _fila(sv: Servicos) -> ServicoStatus:
    n = sv.store.contagens()
    ativos = n.get("running", 0) + n.get("queued", 0) + n.get("paused", 0)
    if sv.worker is not None and sv.worker.vivo:
        return ServicoStatus(
            id="queue",
            name="Fila de jobs",
            state=EstadoServico.OK,
            summary="Worker ativo",
            detail=f"{ativos} job(s) em andamento ou na fila; um por vez (lock global).",
            log_service="fila",
        )
    return ServicoStatus(
        id="queue",
        name="Fila de jobs",
        state=EstadoServico.ERROR,
        summary="Worker parado",
        how_to_fix=["Reinicie o app com iniciar.bat: os jobs pendentes continuam na fila."],
        log_service="fila",
    )


def _ollama(sv: Servicos) -> ServicoStatus:
    try:
        versao = sv.ollama.versao()
        modelos = sv.ollama.modelos()
    except OllamaIndisponivel as exc:
        return ServicoStatus(
            id="ollama",
            name="LLM local (Ollama)",
            state=EstadoServico.ERROR,
            summary="Não respondeu",
            detail=str(exc),
            how_to_fix=[
                "Abra o aplicativo Ollama (ícone na bandeja) ou rode `ollama serve` num terminal.",
                f"Confira se ele escuta em {sv.settings.ollama_url}.",
                "Se não estiver instalado: https://ollama.com/download",
            ],
        )
    if not modelos:
        return ServicoStatus(
            id="ollama",
            name="LLM local (Ollama)",
            state=EstadoServico.WARNING,
            version=versao,
            summary="Rodando, mas sem modelos instalados",
            how_to_fix=[
                "Instale um modelo, por exemplo `ollama pull qwen3:4b` (~2,5 GB). O app pede a sua autorização antes de baixar."
            ],
        )
    nomes = ", ".join(str(m.get("name")) for m in modelos[:4]) + ("..." if len(modelos) > 4 else "")
    return ServicoStatus(
        id="ollama",
        name="LLM local (Ollama)",
        state=EstadoServico.OK,
        version=versao,
        summary=f"{len(modelos)} modelo(s) instalado(s)",
        detail=nomes,
    )


def _claude(hw: dict[str, object]) -> ServicoStatus:
    instalado = bool(obter(hw, "tools.claude_code.installed"))
    logado = obter(hw, "tools.claude_code.logged_in")
    versao = obter(hw, "tools.claude_code.version")
    if instalado and logado is True:
        plano = obter(hw, "tools.claude_code.subscription")
        metodo = obter(hw, "tools.claude_code.auth_method")
        # OK significaria "conectado ao app" (briefing 15.2: só depois do botão Conectar e da chamada de teste). Enquanto o
        # app não fizer essa conexão, o Claude Code logado na máquina é só um fato detectado.
        return ServicoStatus(
            id="claude",
            name="Claude (opcional)",
            state=EstadoServico.INACTIVE,
            version=str(versao) if versao else None,
            summary="Encontrado e logado, ainda não conectado ao app",
            detail=(
                f"Claude Code com login {metodo or 'oficial'}{f', plano {plano}' if plano else ''}. "
                "O app ainda não usa o Claude; a conexão, sempre opcional, ainda não está disponível nesta versão."
            ),
        )
    if instalado:
        return ServicoStatus(
            id="claude",
            name="Claude (opcional)",
            state=EstadoServico.INACTIVE,
            version=str(versao) if versao else None,
            summary="Instalado, sem login",
            how_to_fix=["Faça login pelo fluxo oficial: `claude auth login`. O app nunca lê as suas credenciais."],
        )
    return ServicoStatus(
        id="claude",
        name="Claude (opcional)",
        state=EstadoServico.INACTIVE,
        summary="Não instalado",
        detail="O app funciona por completo só com os modelos locais.",
        how_to_fix=["Opcional: instale o Claude Code e faça login pelo fluxo oficial."],
    )


def _ffmpeg(hw: dict[str, object]) -> ServicoStatus:
    if obter(hw, "tools.ffmpeg.installed"):
        codificadores = obter(hw, "tools.ffmpeg.encoders") or []
        return ServicoStatus(
            id="ffmpeg",
            name="ffmpeg (montagem de vídeo)",
            state=EstadoServico.OK,
            version=str(obter(hw, "tools.ffmpeg.version") or "") or None,
            summary="Instalado",
            detail=("Codificadores: " + ", ".join(codificadores)) if codificadores else None,
        )
    return ServicoStatus(
        id="ffmpeg",
        name="ffmpeg (montagem de vídeo)",
        state=EstadoServico.WARNING,
        summary="Ainda não instalado",
        detail="Necessário para montar e exportar vídeos.",
        how_to_fix=["Abra «Modelos» e clique em «Instalar» no ffmpeg (cerca de 190 MB, dentro da pasta do projeto)."],
    )


def _disco(sv: Servicos) -> ServicoStatus:
    alvo = sv.settings.data_dir
    while not alvo.exists() and alvo != alvo.parent:
        alvo = alvo.parent
    uso = shutil.disk_usage(alvo)
    livre_mb = uso.free / 1048576
    detalhe = f"{_gb(livre_mb)} livres de {_gb(uso.total / 1048576)} em {Path(alvo.anchor or alvo)}"
    fix = [
        "Aponte a pasta de dados para um disco com mais espaço: variável de ambiente FABULIM_DATA_DIR (e FABULIM_MODELS_DIR).",
        "Apague exportações e temporários antigos.",
    ]
    if livre_mb / 1024 < DISCO_ERRO_GB:
        return ServicoStatus(
            id="disk",
            name="Espaço em disco",
            state=EstadoServico.ERROR,
            summary="Quase cheio",
            detail=detalhe,
            how_to_fix=fix,
        )
    if livre_mb / 1024 < DISCO_AVISO_GB:
        return ServicoStatus(
            id="disk",
            name="Espaço em disco",
            state=EstadoServico.WARNING,
            summary="Espaço apertado",
            detail=detalhe,
            how_to_fix=fix,
        )
    return ServicoStatus(
        id="disk", name="Espaço em disco", state=EstadoServico.OK, summary="Espaço confortável", detail=detalhe
    )


def _data_br(iso: object) -> str:
    """ISO 8601 → 29/09/2026 00:04 (dia/mês/ano, como o usuário lê)."""
    try:
        return datetime.fromisoformat(str(iso)).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return str(iso)


def _diagnostico(hw: dict[str, object]) -> ServicoStatus:
    if not hw:
        return ServicoStatus(
            id="diagnostic",
            name="Diagnóstico da máquina",
            state=EstadoServico.WARNING,
            summary="Ainda não rodou",
            how_to_fix=["Abra Status › Sua máquina e clique em «Refazer diagnóstico»."],
        )
    if hw.get("changed_since_last_run"):
        return ServicoStatus(
            id="diagnostic",
            name="Diagnóstico da máquina",
            state=EstadoServico.WARNING,
            summary="A máquina mudou",
            detail="CPU, memória, GPU, driver ou sistema diferentes da última coleta completa.",
            how_to_fix=["Clique em «Refazer diagnóstico» em Status › Sua máquina para atualizar o perfil e a matriz."],
        )
    modo = "completo" if hw.get("mode") == "full" else "leve"
    return ServicoStatus(
        id="diagnostic",
        name="Diagnóstico da máquina",
        state=EstadoServico.OK,
        summary=f"Coleta {modo} em dia",
        detail=f"Última coleta: {_data_br(hw.get('collected_at'))}",
    )


def _motor(sv: Servicos, motor: str, id_: str, nome: str, pronto: str) -> ServicoStatus:
    """Motor de IA local: pronto quando todos os arquivos do catálogo e as bibliotecas estão no lugar.

    "Incompleto" (aviso) só vale quando o usuário já instalou parte dos arquivos; se nada do motor foi instalado, ele
    simplesmente ainda não está ativo (as bibliotecas Python vêm com o próprio app e não contam como instalação).
    """
    itens_faltam, libs_faltam = pendencias(sv.settings, motor)
    if not itens_faltam and not libs_faltam:
        return ServicoStatus(id=id_, name=nome, state=EstadoServico.OK, summary="Instalado", detail=pronto)
    if len(itens_faltam) == len(MOTORES[motor][0]):
        return ServicoStatus(
            id=id_,
            name=nome,
            state=EstadoServico.INACTIVE,
            summary="Ainda não instalado",
            detail="Instale em Modelos para poder usar.",
            how_to_fix=["Abra «Modelos» e clique em «Instalar» (ou em «Instalar tudo o que falta»)."],
        )
    passos = []
    if itens_faltam:
        passos.append("Abra «Modelos» e clique em «Instalar» (ou em «Instalar tudo o que falta»).")
    if libs_faltam:
        passos.append(
            "Instale as bibliotecas Python do app: `.venv\\Scripts\\python -m pip install -r backend\\requirements.txt`."
        )
    return ServicoStatus(
        id=id_,
        name=nome,
        state=EstadoServico.WARNING,
        summary="Instalação incompleta",
        detail="Falta: " + "; ".join(itens_faltam + libs_faltam),
        how_to_fix=passos,
    )


def _animacao(sv: Servicos) -> ServicoStatus:
    """A animação por código: o Python desenha as camadas (Pillow) e o ffmpeg codifica e monta o vídeo."""
    bibliotecas = [n for n in ("PIL", "numpy", "soundfile") if not tem_modulo(n)]
    motivo = sv.motores.ffmpeg.indisponivel()
    if not bibliotecas and motivo is None:
        return ServicoStatus(
            id="animation_engine",
            name="Motor de animação por código",
            state=EstadoServico.OK,
            summary="Pronto",
            detail="O Python desenha as camadas (personagens, cenário, câmera) e o ffmpeg monta o vídeo.",
        )
    falta = [*(["ffmpeg"] if motivo else []), *[f"biblioteca Python {n}" for n in bibliotecas]]
    return ServicoStatus(
        id="animation_engine",
        name="Motor de animação por código",
        state=EstadoServico.INACTIVE,
        summary="Ainda não instalado",
        detail="Falta: " + " e ".join(falta) + ".",
        how_to_fix=["Abra «Modelos» e instale o ffmpeg (ou «Instalar tudo o que falta»)."],
    )


def _musica() -> ServicoStatus:
    return ServicoStatus(
        id="music_engine",
        name="Música e efeitos sonoros (por código)",
        state=EstadoServico.OK,
        summary="Pronto",
        detail=(
            "Músicas infantis instrumentais originais e efeitos sonoros gerados por código, sem modelo de IA e sem arquivos de "
            "terceiros. A música com letra cantada (ACE-Step) pede placa de vídeo dedicada e não está instalada."
        ),
    )


def _verificar(id_: str, nome: str, checagem: Callable[[], ServicoStatus]) -> ServicoStatus:
    """Uma checagem que quebra vira um serviço em erro; nunca derruba a página Status inteira."""
    try:
        return checagem()
    except Exception as exc:
        return ServicoStatus(
            id=id_,
            name=nome,
            state=EstadoServico.ERROR,
            summary="Falha ao verificar",
            detail=f"{type(exc).__name__}: {exc}",
            how_to_fix=["Veja o log em Status › Logs."],
            log_service="app",
        )


def coletar_status(sv: Servicos) -> RelatorioStatus:
    hw = sv.hardware.carregar() or {}
    servicos = [
        _verificar("backend", "Servidor do Fabulim", lambda: _backend(sv)),
        _verificar("database", "Banco de dados (SQLite)", lambda: _banco(sv)),
        _verificar("queue", "Fila de jobs", lambda: _fila(sv)),
        _verificar("diagnostic", "Diagnóstico da máquina", lambda: _diagnostico(hw)),
        _verificar("ollama", "LLM local (Ollama)", lambda: _ollama(sv)),
        _verificar("claude", "Claude (opcional)", lambda: _claude(hw)),
        _verificar("ffmpeg", "ffmpeg (montagem de vídeo)", lambda: _ffmpeg(hw)),
        _verificar("disk", "Espaço em disco", lambda: _disco(sv)),
        _verificar(
            "image_engine",
            "Motor de imagem (stable-diffusion.cpp)",
            lambda: _motor(
                sv,
                "imagem",
                "image_engine",
                "Motor de imagem (stable-diffusion.cpp)",
                "FLUX.2 klein 4B (Q4) com o motor Vulkan",
            ),
        ),
        _verificar(
            "tts_engine",
            "Voz dos personagens (Kokoro)",
            lambda: _motor(
                sv,
                "voz",
                "tts_engine",
                "Voz dos personagens (Kokoro)",
                "Kokoro 82M, com vozes em português do Brasil e inglês",
            ),
        ),
        _verificar(
            "cutout_engine",
            "Recorte de fundo (BiRefNet)",
            lambda: _motor(
                sv, "recorte", "cutout_engine", "Recorte de fundo (BiRefNet)", "BiRefNet lite em ONNX, no processador"
            ),
        ),
        _verificar("music_engine", "Música (ACE-Step)", _musica),
        _verificar("animation_engine", "Motor de animação por código", lambda: _animacao(sv)),
    ]
    estados = {s.state for s in servicos}
    geral = (
        EstadoServico.ERROR
        if EstadoServico.ERROR in estados
        else EstadoServico.WARNING
        if EstadoServico.WARNING in estados
        else EstadoServico.OK
    )
    return RelatorioStatus(
        overall=geral, services=servicos, generated_at=datetime.now(UTC).isoformat(timespec="seconds")
    )
