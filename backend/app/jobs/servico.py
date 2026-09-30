"""Enfileirar jobs: um só lugar para criar, avisar a interface e acordar o worker."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .handlers import REGISTRO, TITULOS
from .models import ATIVOS, Job

if TYPE_CHECKING:
    from ..container import Servicos


class TipoDeJobDesconhecido(ValueError):
    pass


def enfileirar(
    sv: Servicos, kind: str, params: dict[str, Any] | None = None, *, titulo: str | None = None, prioridade: int = 0
) -> Job:
    if kind not in REGISTRO:
        raise TipoDeJobDesconhecido(f"tipo de job desconhecido: {kind}")
    job = sv.store.criar(kind, titulo or TITULOS.get(kind, kind), params or {}, priority=prioridade)
    sv.bus.publicar("job.updated", job.model_dump(mode="json"))
    if sv.worker is not None:
        sv.worker.acordar()
    return job


def job_ativo_do_tipo(sv: Servicos, kind: str) -> Job | None:
    """Evita enfileirar o mesmo job de sistema duas vezes (ex.: diagnóstico)."""
    return next((j for j in sv.store.listar(ATIVOS) if j.kind == kind), None)
