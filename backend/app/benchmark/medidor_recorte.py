"""Mede o recorte de fundo (BiRefNet lite, ONNX) de verdade: carrega o modelo e recorta uma imagem de 1024 px.

Roda como processo à parte (``python medidor_recorte.py <modelo.onnx>``) e não depende do resto do app. A última linha da
saída é um JSON com os tempos. A imagem é ruído aleatório com semente fixa: o tempo do modelo não depende do desenho. O
tempo que vale é o da segunda passada (modelo quente); a primeira, mais lenta, fica registrada em ``first_s``.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

LADO = 1024


def medir(modelo: str) -> dict[str, Any]:
    import numpy as np  # imports tardios: só existem onde as bibliotecas de IA foram instaladas
    import onnxruntime as ort

    inicio = time.monotonic()
    sessao = ort.InferenceSession(modelo, providers=["CPUExecutionProvider"])
    carga = time.monotonic() - inicio
    entrada = sessao.get_inputs()[0]
    imagem = np.random.default_rng(0).random((1, 3, LADO, LADO), dtype=np.float32)
    antes = time.monotonic()
    sessao.run(None, {entrada.name: imagem})  # a primeira passada aloca memória e otimiza: mede à parte
    primeira = time.monotonic() - antes
    antes = time.monotonic()
    saidas = sessao.run(None, {entrada.name: imagem})
    inferencia = time.monotonic() - antes  # com o modelo já quente, como nas imagens seguintes de um mesmo lote
    return {
        "load_s": round(carga, 2),
        "first_s": round(primeira, 2),
        "infer_s": round(inferencia, 2),
        "size": LADO,
        "output_shape": [int(n) for n in saidas[0].shape],
        "provider": "cpu",
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("uso: medidor_recorte.py <modelo.onnx>", file=sys.stderr)
        return 2
    print(json.dumps(medir(argv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
