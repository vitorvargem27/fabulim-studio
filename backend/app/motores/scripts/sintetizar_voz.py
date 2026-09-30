"""Fala vários textos de uma vez (Kokoro, ONNX), gravando um WAV para cada um.

Roda como processo à parte: ``python sintetizar_voz.py <modelo.onnx> <vozes.bin> <pedidos.json>``. O arquivo de pedidos é
uma lista de ``{"texto", "voz", "velocidade", "lingua", "saida"}``. Carregar o modelo uma vez só para todas as falas
poupa vários segundos por fala. Não depende do resto do app. A última linha da saída é um JSON com as durações.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any


def sintetizar(modelo: str, vozes: str, pedidos: list[dict[str, Any]]) -> dict[str, Any]:
    import soundfile as sf  # imports tardios: só existem onde as bibliotecas de IA foram instaladas
    from kokoro_onnx import Kokoro

    inicio = time.monotonic()
    kokoro = Kokoro(modelo, vozes)
    carga = time.monotonic() - inicio
    itens: list[dict[str, Any]] = []
    for pedido in pedidos:
        antes = time.monotonic()
        amostras, taxa = kokoro.create(
            str(pedido["texto"]),
            voice=str(pedido["voz"]),
            speed=float(pedido.get("velocidade", 1.0)),
            lang=str(pedido.get("lingua", "pt-br")),
        )
        Path(str(pedido["saida"])).parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(pedido["saida"]), amostras, int(taxa))
        itens.append(
            {
                "saida": str(pedido["saida"]),
                "duration_s": round(len(amostras) / taxa, 3),
                "synth_s": round(time.monotonic() - antes, 2),
            }
        )
    return {"load_s": round(carga, 2), "items": itens}


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("uso: sintetizar_voz.py <modelo.onnx> <vozes.bin> <pedidos.json>", file=sys.stderr)
        return 2
    pedidos = json.loads(Path(argv[3]).read_text(encoding="utf-8"))
    print(json.dumps(sintetizar(argv[1], argv[2], pedidos)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
