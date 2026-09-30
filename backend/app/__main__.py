"""Sobe o servidor: ``python -m app`` (com PYTHONPATH=backend) ou ``python scripts/servidor.py``.

``--porta`` só imprime a porta em que o servidor vai escutar (vale o ``.env``); o ``iniciar`` usa isso para saber onde
perguntar se o servidor está no ar.
"""

from __future__ import annotations

import sys

import uvicorn

from .config import ConfiguracaoInvalida, carregar_configuracao


def main(argv: list[str] | None = None) -> int:
    so_porta = "--porta" in (sys.argv[1:] if argv is None else argv)
    try:
        config = carregar_configuracao()
    except ConfiguracaoInvalida as exc:
        print(f"Configuração inválida: {exc}", file=sys.stderr if so_porta else sys.stdout)
        return 2
    if so_porta:
        print(config.port)
        return 0
    uvicorn.run(
        "app.main:criar_app",
        factory=True,
        host=config.host,
        port=config.port,
        log_level="info",
        access_log=False,
        server_header=False,  # não anuncia a versão do servidor
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
