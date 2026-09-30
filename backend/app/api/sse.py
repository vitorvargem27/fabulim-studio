"""Eventos em tempo real (Server-Sent Events): o cliente recebe um retrato da fila e depois cada mudança."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from ..container import Servicos

HEARTBEAT_SEGUNDOS = 15.0


def formatar_evento(tipo: str, dados: dict[str, Any]) -> str:
    return f"event: {tipo}\ndata: {json.dumps(dados, ensure_ascii=False)}\n\n"


async def gerar_eventos(
    sv: Servicos,
    desconectado: Callable[[], Awaitable[bool]],
    *,
    heartbeat: float = HEARTBEAT_SEGUNDOS,
    max_eventos: int | None = None,
) -> AsyncIterator[str]:
    """Gerador do stream SSE. ``max_eventos`` existe para os testes (o stream real é infinito)."""
    sub = sv.bus.assinar()
    enviados = 0
    try:
        jobs = await asyncio.to_thread(sv.store.listar)
        yield ": conectado\n\n"
        yield formatar_evento("snapshot", {"jobs": [j.model_dump(mode="json") for j in jobs]})
        enviados += 1
        while max_eventos is None or enviados < max_eventos:
            if await desconectado():
                break
            try:
                evento = await asyncio.wait_for(sub.fila.get(), timeout=heartbeat)
            except TimeoutError:
                yield ": ping\n\n"  # mantém a conexão viva através de proxies
                continue
            yield formatar_evento(str(evento["type"]), evento["data"])
            enviados += 1
    finally:
        sv.bus.cancelar(sub)
