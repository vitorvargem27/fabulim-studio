"""Configuração do backend: pastas, porta e variáveis de ambiente (prefixo ``FABULIM_``).

Regras de segurança (briefing, seção 11): tudo em 127.0.0.1 e nenhuma IA externa além do Claude. Por isso o
servidor e o Ollama só aceitam endereços de loopback.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

VERSAO = "0.1.0"
NOME_APP = "Fabulim Studio"
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
PORTA_PADRAO = 8765  # a 8000 costuma estar ocupada por outros programas


class ConfiguracaoInvalida(ValueError):
    """Variável de ambiente ou combinação de opções que violam as regras de segurança."""


def raiz_do_projeto() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    root: Path
    host: str
    port: int
    data_dir: Path
    models_dir: Path
    tools_dir: Path
    config_dir: Path
    hardware_json: Path
    capabilities_json: Path
    frontend_dist: Path
    ollama_url: str
    auto_diagnostico: bool
    allowed_hosts: tuple[str, ...]
    cors_origins: tuple[str, ...]

    @property
    def db_path(self) -> Path:
        return self.data_dir / "fabulim.db"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def midias_dir(self) -> Path:
        return self.data_dir / "midias"

    @property
    def temp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def scripts_dir(self) -> Path:
        return self.root / "scripts"


def _host_da_url(url: str) -> str:
    return urlparse(url).hostname or ""


def _caminho(env: Mapping[str, str], chave: str, padrao: Path) -> Path:
    valor = env.get(chave)
    return Path(valor).expanduser().resolve() if valor else padrao


def _valor_do_dotenv(bruto: str) -> str:
    bruto = bruto.strip()
    if bruto[:1] in ("'", '"'):
        fim = bruto.find(bruto[0], 1)
        if fim != -1:
            return bruto[1:fim]
    return bruto.split(" #", 1)[0].strip()


def ler_dotenv(arquivo: Path) -> dict[str, str]:
    """Lê um ``.env`` simples (``CHAVE=valor``, ``#`` para comentário). Só aceita chaves ``FABULIM_*``.

    Assim o arquivo não consegue mexer em ``PATH`` nem em outras variáveis do sistema. Arquivo ausente ou ilegível
    vale como vazio.
    """
    try:
        linhas = arquivo.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError):
        return {}
    valores: dict[str, str] = {}
    for linha in linhas:
        chave, separador, bruto = linha.strip().removeprefix("export ").partition("=")
        chave = chave.strip()
        if separador and re.fullmatch(r"FABULIM_[A-Z0-9_]+", chave):
            valores[chave] = _valor_do_dotenv(bruto)
    return valores


def carregar_configuracao(env: Mapping[str, str] | None = None, root: Path | None = None) -> Settings:
    """Lê a configuração e valida as regras de segurança.

    Sem ``env`` (uso real), lê o ``.env`` da raiz do projeto e, por cima, as variáveis de ambiente de verdade, que têm
    prioridade. Com ``env`` (testes), usa só o que foi passado.
    """
    raiz = (root or raiz_do_projeto()).resolve()
    ambiente: Mapping[str, str] = {**ler_dotenv(raiz / ".env"), **os.environ} if env is None else env

    host = ambiente.get("FABULIM_HOST", "127.0.0.1").strip()
    if host not in LOOPBACK:
        raise ConfiguracaoInvalida(
            f"FABULIM_HOST={host!r} não é permitido: o Fabulim só escuta em 127.0.0.1 (nenhuma porta exposta à rede)."
        )

    try:
        porta = int(ambiente.get("FABULIM_PORT", PORTA_PADRAO))
    except ValueError as exc:
        raise ConfiguracaoInvalida("FABULIM_PORT deve ser um número inteiro") from exc
    if not 1024 <= porta <= 65535:
        raise ConfiguracaoInvalida("FABULIM_PORT deve estar entre 1024 e 65535")

    ollama = ambiente.get("FABULIM_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    if _host_da_url(ollama) not in LOOPBACK:
        raise ConfiguracaoInvalida("FABULIM_OLLAMA_URL deve apontar para esta máquina (127.0.0.1)")

    config_dir = raiz / "config"
    hardware_json = _caminho(ambiente, "FABULIM_HARDWARE_JSON", config_dir / "hardware.json")
    origens = tuple(f"http://{h}:{p}" for h in ("127.0.0.1", "localhost") for p in (porta, 4200))
    return Settings(
        root=raiz,
        host=host,
        port=porta,
        data_dir=_caminho(ambiente, "FABULIM_DATA_DIR", raiz / "data"),
        models_dir=_caminho(ambiente, "FABULIM_MODELS_DIR", raiz / "models"),
        tools_dir=_caminho(ambiente, "FABULIM_TOOLS_DIR", raiz / "tools"),
        config_dir=config_dir,
        hardware_json=hardware_json,
        capabilities_json=hardware_json.parent / "capabilities.json",
        frontend_dist=_caminho(ambiente, "FABULIM_FRONTEND_DIST", raiz / "frontend" / "dist" / "frontend" / "browser"),
        ollama_url=ollama,
        auto_diagnostico=ambiente.get("FABULIM_AUTO_DIAGNOSTICO", "1") != "0",
        allowed_hosts=("127.0.0.1", "localhost"),
        cors_origins=origens,
    )
