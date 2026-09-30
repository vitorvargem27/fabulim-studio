"""Mixagem da trilha final: vozes, efeitos e música, com a música abaixando sozinha enquanto alguém fala (ducking)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf

TAXA = 44_100
Onda = npt.NDArray[np.float32]
QUADRO_S = 0.01  # o ducking decide a cada 10 ms


@dataclass(frozen=True)
class Fala:
    inicio_s: float
    onda: Onda  # mono, 44,1 kHz


@dataclass(frozen=True)
class Efeito:
    inicio_s: float
    onda: Onda
    ganho: float = 0.6


def carregar_mono(caminho: Path, taxa: int = TAXA) -> Onda:
    """Lê um WAV como mono na taxa pedida (reamostra por interpolação se o arquivo veio em outra taxa)."""
    dados, taxa_do_arquivo = sf.read(str(caminho), dtype="float32", always_2d=True)
    mono: Onda = dados.mean(axis=1).astype(np.float32)
    if taxa_do_arquivo != taxa and len(mono) > 1:
        novo = round(len(mono) * taxa / taxa_do_arquivo)
        mono = np.interp(np.linspace(0, len(mono) - 1, novo), np.arange(len(mono)), mono).astype(np.float32)
    return mono


def _colocar(faixa: Onda, som: Onda, inicio_s: float, ganho: float = 1.0) -> None:
    inicio = max(0, round(inicio_s * TAXA))
    if inicio >= len(faixa):
        return
    fim = min(len(faixa), inicio + len(som))
    faixa[inicio:fim] += som[: fim - inicio] * ganho


def ganho_de_ducking(
    voz: Onda, reducao_db: float = -11.0, ataque_s: float = 0.12, soltura_s: float = 0.5, limiar: float = 0.01
) -> Onda:
    """O ganho (por amostra, de ~0,28 a 1) que a música deve ter: cai rápido quando há voz e volta devagar quando ela cala."""
    passo = int(TAXA * QUADRO_S)
    n_quadros = len(voz) // passo + 1
    preenchido = np.zeros(n_quadros * passo, dtype=np.float32)
    preenchido[: len(voz)] = voz
    rms = np.sqrt((preenchido.reshape(n_quadros, passo) ** 2).mean(axis=1))
    reduzido = 10 ** (reducao_db / 20)
    alvo = np.where(rms > limiar, reduzido, 1.0)
    a_ataque, a_soltura = 1 - math.exp(-QUADRO_S / ataque_s), 1 - math.exp(-QUADRO_S / soltura_s)
    quadros = np.empty(n_quadros, dtype=np.float64)
    atual = 1.0
    for i, meta in enumerate(alvo):
        atual += (meta - atual) * (a_ataque if meta < atual else a_soltura)
        quadros[i] = atual
    ganho = np.interp(np.arange(len(voz)), np.arange(n_quadros) * passo, quadros)
    resultado: Onda = ganho.astype(np.float32)
    return resultado


def mixar(
    duracao_s: float,
    falas: list[Fala],
    efeitos: list[Efeito] | None = None,
    musica: Onda | None = None,
    ganho_da_musica: float = 0.22,
    reducao_db: float = -11.0,
) -> npt.NDArray[np.float32]:
    """A trilha estéreo (n, 2) com ``duracao_s`` segundos. Nunca passa de ±0,98 (se passar, o volume geral desce)."""
    n = round(duracao_s * TAXA)
    voz = np.zeros(n, dtype=np.float32)
    for fala in falas:
        _colocar(voz, fala.onda, fala.inicio_s)
    som = np.zeros(n, dtype=np.float32)
    for efeito in efeitos or []:
        _colocar(som, efeito.onda, efeito.inicio_s, efeito.ganho)
    base = voz + som
    if musica is not None and len(musica):
        fundo = np.zeros(n, dtype=np.float32)
        fundo[: min(n, len(musica))] = musica[:n]
        base = base + fundo * ganho_da_musica * ganho_de_ducking(voz, reducao_db)
    pico = float(np.abs(base).max())
    if pico > 0.98:
        base = base * (0.98 / pico)
    return np.stack([base, base], axis=1).astype(np.float32)


def salvar_wav(caminho: Path, trilha: npt.NDArray[np.float32], taxa: int = TAXA) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(caminho), trilha, taxa, subtype="PCM_16")
    return caminho
