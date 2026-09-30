"""Servidor do E2E das ferramentas de criação (Personagens, Gerar imagem, Clipes, Projetos e a Fila noturna).

É o app de verdade (API, fila, banco de dados, segurança e o ffmpeg real), só que com a imagem, o recorte e a voz trocados
por versões falsas e rápidas, e sem o modelo de texto (como num computador sem o Ollama). Assim o teste percorre o caminho
inteiro em segundos, em vez de esperar minutos por imagem. Só o E2E usa este arquivo: o app que o usuário abre nunca troca os
motores por falsos.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "backend"))

import uvicorn  # noqa: E402

from app.config import carregar_configuracao  # noqa: E402
from app.container import criar_servicos  # noqa: E402
from app.main import criar_app  # noqa: E402
from app.motores.fabrica import Motores  # noqa: E402
from app.motores.ffmpeg import Ffmpeg  # noqa: E402


def _falsos() -> Any:
    """Os motores falsos da suíte de testes do backend (o arquivo só depende do pacote ``app``)."""
    spec = importlib.util.spec_from_file_location("fakes_motores", RAIZ / "backend" / "tests" / "fakes_motores.py")
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["fakes_motores"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def main() -> int:
    config = carregar_configuracao()
    falsos = _falsos()
    motores = Motores(
        imagem=falsos.ImagemFalsa(),
        recorte=falsos.RecorteFalso(),
        voz=falsos.VozFalsa(),
        texto=falsos.TextoFalso(indisponivel="O modelo de texto local não está ligado neste teste."),
        ffmpeg=Ffmpeg(config),
    )
    servicos = criar_servicos(config, motores=motores)
    app = criar_app(config, servicos=servicos)
    uvicorn.run(app, host=config.host, port=config.port, log_level="warning", access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
