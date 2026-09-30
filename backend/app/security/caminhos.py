"""Nomes de arquivo e caminhos seguros (briefing, seção 11: sanitizar nomes e bloquear path traversal)."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_RESERVADOS_WINDOWS = frozenset(
    {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
)
_PROIBIDOS = re.compile(r"[\x00-\x1f\x7f<>:\"|?*]")


class CaminhoInseguro(ValueError):
    """O caminho sai da pasta permitida, é absoluto ou tem componentes perigosos."""


def nome_de_arquivo_seguro(nome: str, *, padrao: str = "arquivo", max_len: int = 100) -> str:
    """Só o nome-base: sem pastas, sem ``..``, sem caracteres de controle e sem nomes reservados do Windows."""
    base = re.split(r"[\\/]", nome)[-1]
    base = unicodedata.normalize("NFKC", base)
    base = _PROIBIDOS.sub("", base).strip().strip(".")
    base = re.sub(r"\s+", "_", base)
    if not base:
        return padrao
    corpo, ponto, extensao = base.rpartition(".")
    radical = corpo if ponto else base
    if radical.lower() in _RESERVADOS_WINDOWS:
        base = f"_{base}"
    if len(base) > max_len:
        corpo, ponto, extensao = base.rpartition(".")
        base = (
            (corpo[: max_len - len(extensao) - 1] + "." + extensao) if ponto and len(extensao) < 20 else base[:max_len]
        )
    return base


def dentro_da_pasta(base: Path, alvo: str | Path) -> Path:
    """Resolve ``alvo`` dentro de ``base`` e garante que continua lá (bloqueia ``..``, absolutos e links para fora)."""
    base_resolvida = base.resolve()
    candidato = (base_resolvida / alvo).resolve()
    if not candidato.is_relative_to(base_resolvida):
        raise CaminhoInseguro(f"caminho fora da pasta permitida: {alvo!r}")
    return candidato


def entrada_de_pacote_segura(nome: str) -> str:
    """Valida o nome de uma entrada de zip/.fabulim (contra zip slip) e devolve o caminho normalizado com ``/``."""
    if not nome or "\x00" in nome:
        raise CaminhoInseguro("entrada vazia ou com byte nulo")
    normalizado = nome.replace("\\", "/")
    if normalizado.startswith("/") or re.match(r"^[A-Za-z]:", normalizado) or normalizado.startswith("//"):
        raise CaminhoInseguro(f"entrada com caminho absoluto: {nome!r}")
    partes = [p for p in normalizado.split("/") if p not in ("", ".")]
    if not partes or ".." in partes:
        raise CaminhoInseguro(f"entrada tenta sair da pasta: {nome!r}")
    return "/".join(partes)
