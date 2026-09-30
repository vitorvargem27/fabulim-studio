"""Volume da voz quadro a quadro: é o que faz o personagem "pulsar" no ritmo da fala."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf

Vetor = npt.NDArray[np.float32]


def envelope_de_audio(caminho: Path, fps: int, quadros: int, inicio_s: float = 0.0) -> Vetor:
    """O volume (0 a 1) de cada quadro de vídeo, com o áudio começando em ``inicio_s``. Suaviza para não tremer."""
    resultado = np.zeros(quadros, dtype=np.float32)
    dados, taxa = sf.read(str(caminho), dtype="float32", always_2d=True)
    mono = dados.mean(axis=1)
    janela = max(int(taxa / fps), 1)
    n = len(mono) // janela
    if n == 0:
        return resultado
    rms = np.sqrt((mono[: n * janela].reshape(n, janela) ** 2).mean(axis=1))
    referencia = float(np.percentile(rms, 95)) or 1.0
    normalizado = np.clip(rms / referencia, 0.0, 1.0)
    normalizado = np.where(normalizado < 0.08, 0.0, normalizado)  # silêncio e chiado não mexem o personagem
    suave = np.zeros_like(normalizado)
    anterior = 0.0
    for i, valor in enumerate(normalizado):  # sobe rápido, desce devagar
        anterior = valor if valor > anterior else anterior * 0.6 + valor * 0.4
        suave[i] = anterior
    inicio = round(inicio_s * fps)
    if inicio >= quadros:
        return resultado
    trecho = suave[: quadros - inicio]
    resultado[inicio : inicio + len(trecho)] = trecho
    return resultado


def combinar_envelopes(envelopes: list[Vetor], quadros: int) -> Vetor:
    resultado = np.zeros(quadros, dtype=np.float32)
    for envelope in envelopes:
        n = min(quadros, len(envelope))
        resultado[:n] = np.maximum(resultado[:n], envelope[:n])
    return resultado
