"""Ajustes de áudio com o ffmpeg: tom da voz (sem mudar a duração), normalização e mixagem."""

from __future__ import annotations

from pathlib import Path

from .interfaces import MotorFfmpeg
from .tipos import Contexto

TAXA_DA_VOZ = 24_000  # o Kokoro fala a 24 kHz, em mono


def alterar_tom(ffmpeg: MotorFfmpeg, ctx: Contexto, origem: Path, saida: Path, tom: float) -> Path:
    """Deixa a voz mais aguda (tom > 1) ou mais grave (tom < 1) sem mudar a duração (filtro rubberband)."""
    saida.parent.mkdir(parents=True, exist_ok=True)
    if abs(tom - 1.0) < 0.01:
        saida.write_bytes(origem.read_bytes())
        return saida
    ffmpeg.rodar(
        ctx,
        [
            "-i",
            origem.resolve(),
            "-af",
            f"rubberband=pitch={tom:.4f}",
            "-ar",
            str(TAXA_DA_VOZ),
            "-ac",
            "1",
            saida.resolve(),
        ],
        timeout=300,
    )
    return saida


def preparar_voz(ffmpeg: MotorFfmpeg, ctx: Contexto, origem: Path, saida: Path, tom: float, taxa: int = 44_100) -> Path:
    """A fala do Kokoro (24 kHz) pronta para a mixagem: no tom do personagem, em mono e na taxa da trilha final."""
    saida.parent.mkdir(parents=True, exist_ok=True)
    filtros = [] if abs(tom - 1.0) < 0.01 else [f"rubberband=pitch={tom:.4f}"]
    argumentos: list[str | Path] = ["-i", origem.resolve()]
    if filtros:
        argumentos += ["-af", ",".join(filtros)]
    ffmpeg.rodar(ctx, [*argumentos, "-ar", str(taxa), "-ac", "1", saida.resolve()], timeout=300)
    return saida
