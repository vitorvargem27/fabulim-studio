"""Mede a voz (Kokoro) de verdade: carrega o modelo e fala uma frase em português do Brasil.

Roda como processo à parte (``python medidor_voz.py <modelo.onnx> <vozes.bin>``), porque o modelo ocupa memória que deve
voltar ao sistema ao terminar. Não depende do resto do app. A última linha da saída é um JSON com os tempos.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

FRASE = "Olá! Eu sou o Bolinho, o coelho azul. Vamos brincar no campo de girassóis?"
AQUECIMENTO = "Olá, tudo bem?"  # a primeira fala de um processo paga a inicialização das bibliotecas: não conta
VOZ = "pf_dora"


def medir(modelo: str, vozes: str) -> dict[str, Any]:
    inicio = time.monotonic()
    from kokoro_onnx import Kokoro  # import tardio: só existe onde as bibliotecas de IA foram instaladas

    kokoro = Kokoro(modelo, vozes)
    carga = time.monotonic() - inicio
    antes = time.monotonic()
    kokoro.create(AQUECIMENTO, voice=VOZ, speed=1.0, lang="pt-br")
    primeira = time.monotonic() - antes
    antes = time.monotonic()
    amostras, taxa = kokoro.create(FRASE, voice=VOZ, speed=1.0, lang="pt-br")
    sintese = time.monotonic() - antes
    audio = len(amostras) / taxa
    return {
        "load_s": round(carga, 2),
        "warmup_s": round(primeira, 2),
        "synth_s": round(sintese, 2),
        "audio_s": round(audio, 2),
        "rtf": round(sintese / audio, 3) if audio > 0 else None,
        "sample_rate": int(taxa),
        "voice": VOZ,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("uso: medidor_voz.py <modelo.onnx> <vozes.bin>", file=sys.stderr)
        return 2
    print(json.dumps(medir(argv[1], argv[2])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
