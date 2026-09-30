"""Recorta o fundo de uma imagem (BiRefNet lite, ONNX) e grava um PNG transparente.

Roda como processo à parte: ``python recortar_imagem.py <modelo.onnx> <entrada> <saida.png> [--caixa]``. Não depende do
resto do app. Com ``--caixa`` o PNG é cortado rente ao personagem (com uma pequena margem). A última linha da saída é
um JSON com o resultado.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

import numpy as np
from PIL import Image

LADO = 1024
MEDIA = np.array([0.485, 0.456, 0.406], dtype=np.float32)
DESVIO = np.array([0.229, 0.224, 0.225], dtype=np.float32)
LIMIAR_DA_CAIXA = 24  # opacidade (0 a 255) a partir da qual um pixel conta como parte do personagem
MARGEM_DA_CAIXA = 0.03


def recortar(modelo: str, entrada: str, saida: str, caixa: bool) -> dict[str, Any]:
    import onnxruntime as ort  # import tardio: só existe onde as bibliotecas de IA foram instaladas

    inicio = time.monotonic()
    imagem = Image.open(entrada).convert("RGB")
    original = imagem.size
    pequena = imagem.resize((LADO, LADO), Image.Resampling.BILINEAR)
    x = (np.asarray(pequena, dtype=np.float32) / 255.0 - MEDIA) / DESVIO
    x = x.transpose(2, 0, 1)[None].astype(np.float32)
    sessao = ort.InferenceSession(modelo, providers=["CPUExecutionProvider"])
    bruto = sessao.run(None, {sessao.get_inputs()[0].name: x})[0][0, 0]
    mascara = 1.0 / (1.0 + np.exp(-np.clip(bruto, -30.0, 30.0)))  # sigmoide estável
    alfa = Image.fromarray((mascara * 255.0).astype(np.uint8)).resize(original, Image.Resampling.BILINEAR)
    resultado = imagem.copy()
    resultado.putalpha(alfa)
    limites = None
    if caixa:
        limites = alfa.point(lambda v: 255 if v > LIMIAR_DA_CAIXA else 0).getbbox()
        if limites:
            esq, topo, dir_, base = limites
            folga_x = round((dir_ - esq) * MARGEM_DA_CAIXA)
            folga_y = round((base - topo) * MARGEM_DA_CAIXA)
            resultado = resultado.crop(
                (
                    max(0, esq - folga_x),
                    max(0, topo - folga_y),
                    min(original[0], dir_ + folga_x),
                    min(original[1], base + folga_y),
                )
            )
    resultado.save(saida, "PNG")
    opacos = float((np.asarray(alfa) > LIMIAR_DA_CAIXA).mean())
    return {
        "seconds": round(time.monotonic() - inicio, 2),
        "width": resultado.size[0],
        "height": resultado.size[1],
        "original_width": original[0],
        "original_height": original[1],
        "foreground_ratio": round(opacos, 4),
        "cropped": bool(caixa and limites),
    }


def main(argv: list[str]) -> int:
    argumentos = [a for a in argv[1:] if a != "--caixa"]
    if len(argumentos) != 3:
        print("uso: recortar_imagem.py <modelo.onnx> <entrada> <saida.png> [--caixa]", file=sys.stderr)
        return 2
    print(json.dumps(recortar(argumentos[0], argumentos[1], argumentos[2], "--caixa" in argv)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
