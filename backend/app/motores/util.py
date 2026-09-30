"""Pequenas funções que os motores e o benchmark compartilham: ler o final da saída de um processo, tempos de log..."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ASSINATURA_PNG = b"\x89PNG\r\n\x1a\n"


def final_da_saida(texto: str, linhas: int = 3) -> str:
    """As últimas linhas legíveis da saída de um processo, para explicar uma falha."""
    limpas = [" ".join(parte.split()) for parte in re.split(r"[\r\n]+", texto) if parte.strip()]
    return " | ".join(limpas[-linhas:])[:400]


def tempo_do_log(padrao: str, texto: str) -> float | None:
    achou = re.search(padrao, texto)
    return float(achou.group(1)) if achou else None


def e_png(arquivo: Path) -> bool:
    """Gerou mesmo uma imagem? (existe, não é minúscula e começa com a assinatura de um PNG)"""
    try:
        if arquivo.stat().st_size < 10_000:
            return False
        with arquivo.open("rb") as f:
            return f.read(8) == ASSINATURA_PNG
    except OSError:
        return False


_FALTA_DE_MEMORIA = re.compile(
    r"out of (device |host )?memory|outofdevicememory|out_of_device_memory|bad_alloc|failed to allocate|cannot allocate"
    r"|not enough memory|memoryerror|\boom\b",
    re.IGNORECASE,
)


def parece_falta_de_memoria(texto: str) -> bool:
    """A saída de um motor que morreu fala de memória? (briefing 12.8: sugerir uma configuração menor)"""
    return _FALTA_DE_MEMORIA.search(texto) is not None


def json_da_saida(texto: str) -> dict[str, Any]:
    """Os scripts dos motores imprimem o resultado como JSON na última linha; o resto da saída é ruído de bibliotecas."""
    for linha in reversed(texto.strip().splitlines()):
        linha = linha.strip()
        if linha.startswith("{") and linha.endswith("}"):
            try:
                dados = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if isinstance(dados, dict):
                return dados
    raise ValueError("o motor não devolveu o resultado")


def br(valor: Any, casas: int = 1) -> str:
    """Número com vírgula decimal, como o usuário lê (4,9 e não 4.9)."""
    try:
        return f"{float(valor):.{casas}f}".replace(".", ",")
    except (TypeError, ValueError):
        return "?"


def formatar_duracao(segundos: float) -> str:
    return f"{segundos:.0f} s" if segundos < 90 else f"{segundos / 60:.1f}".replace(".", ",") + " min"
