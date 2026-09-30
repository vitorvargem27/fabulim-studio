"""Legendas SRT geradas do roteiro, sincronizadas com o momento em que cada fala começa e termina."""

from __future__ import annotations

import re
import textwrap

LARGURA_DA_LINHA = 42
MAXIMO_POR_LEGENDA = LARGURA_DA_LINHA * 2  # duas linhas
DURACAO_MINIMA_S = 0.9


def formatar_tempo(segundos: float) -> str:
    """``HH:MM:SS,mmm``, como o formato SRT pede."""
    milissegundos = max(0, round(segundos * 1000))
    horas, resto = divmod(milissegundos, 3_600_000)
    minutos, resto = divmod(resto, 60_000)
    segs, ms = divmod(resto, 1000)
    return f"{horas:02d}:{minutos:02d}:{segs:02d},{ms:03d}"


def quebrar_em_partes(texto: str, maximo: int = MAXIMO_POR_LEGENDA) -> list[str]:
    """Texto longo vira várias legendas (quebra em fim de frase ou de palavra, nunca no meio de uma palavra)."""
    limpo = " ".join(texto.split())
    if not limpo:
        return []
    if len(limpo) <= maximo:
        return [limpo]
    frases = re.split(r"(?<=[.!?…])\s+", limpo)
    partes: list[str] = []
    atual = ""
    for frase in frases:
        for pedaco in textwrap.wrap(frase, maximo) or [frase]:
            if atual and len(atual) + 1 + len(pedaco) > maximo:
                partes.append(atual)
                atual = pedaco
            else:
                atual = f"{atual} {pedaco}".strip()
    if atual:
        partes.append(atual)
    return partes


def gerar_srt(falas: list[tuple[float, float, str]]) -> str:
    """De uma lista de (início, fim, texto) em segundos monta o arquivo SRT. Ordena, não deixa legendas se sobreporem."""
    legendas: list[tuple[float, float, str]] = []
    for inicio, fim, texto in sorted(falas, key=lambda f: f[0]):
        partes = quebrar_em_partes(texto)
        if not partes:
            continue
        total = sum(len(p) for p in partes)
        duracao = max(fim - inicio, DURACAO_MINIMA_S)
        cursor = inicio
        for parte in partes:
            pedaco = duracao * len(parte) / total
            legendas.append((cursor, cursor + pedaco, parte))
            cursor += pedaco
    saida: list[str] = []
    for i, (inicio, fim, texto) in enumerate(legendas):
        if i + 1 < len(legendas):
            fim = min(fim, legendas[i + 1][0])  # a próxima só entra quando esta acabar
        fim = max(fim, inicio + 0.3)
        linhas = textwrap.wrap(texto, LARGURA_DA_LINHA) or [texto]
        saida.append(f"{i + 1}\n{formatar_tempo(inicio)} --> {formatar_tempo(fim)}\n" + "\n".join(linhas))
    return "\n\n".join(saida) + ("\n" if saida else "")
