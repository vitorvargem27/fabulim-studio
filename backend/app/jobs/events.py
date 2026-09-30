"""Barramento de eventos em memória: a fila (thread) publica; as conexões SSE (asyncio) assinam."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from dataclasses import dataclass
from typing import Any

Evento = dict[str, Any]


@dataclass(eq=False)
class Assinatura:
    loop: asyncio.AbstractEventLoop
    fila: asyncio.Queue[Evento]


class EventBus:
    def __init__(self, tamanho_fila: int = 500) -> None:
        self._trava = threading.Lock()
        self._assinaturas: list[Assinatura] = []
        self._tamanho = tamanho_fila

    def assinar(self) -> Assinatura:
        """Deve ser chamado de dentro do loop asyncio que vai consumir os eventos."""
        sub = Assinatura(asyncio.get_running_loop(), asyncio.Queue(maxsize=self._tamanho))
        with self._trava:
            self._assinaturas.append(sub)
        return sub

    def cancelar(self, sub: Assinatura) -> None:
        with self._trava:
            if sub in self._assinaturas:
                self._assinaturas.remove(sub)

    def total_assinantes(self) -> int:
        with self._trava:
            return len(self._assinaturas)

    def publicar(self, tipo: str, dados: dict[str, Any]) -> None:
        """Seguro para chamar de qualquer thread."""
        evento: Evento = {"type": tipo, "data": dados}
        with self._trava:
            assinaturas = list(self._assinaturas)
        for sub in assinaturas:
            try:
                sub.loop.call_soon_threadsafe(self._entregar, sub.fila, evento)
            except RuntimeError:  # loop já fechado: a conexão caiu
                self.cancelar(sub)

    @staticmethod
    def _entregar(fila: asyncio.Queue[Evento], evento: Evento) -> None:
        if fila.full():  # cliente lento: descarta o mais antigo em vez de travar a fila de jobs
            with contextlib.suppress(asyncio.QueueEmpty):
                fila.get_nowait()
        fila.put_nowait(evento)
