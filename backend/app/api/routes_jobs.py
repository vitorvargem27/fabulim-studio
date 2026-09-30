"""Rotas da fila de jobs e do stream de eventos."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import StreamingResponse

from ..jobs.models import Job, JobCreate, JobLog, JobStatus, ReordenarPedido
from ..jobs.servico import TipoDeJobDesconhecido, enfileirar
from .deps import ServicosDep
from .sse import gerar_eventos

router = APIRouter(prefix="/api")

IdJob = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


def _publicar(sv: ServicosDep, job: Job | None) -> Job:
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    sv.bus.publicar("job.updated", job.model_dump(mode="json"))
    return job


def _publicar_retrato(sv: ServicosDep) -> None:
    sv.bus.publicar("snapshot", {"jobs": [j.model_dump(mode="json") for j in sv.store.listar()]})


@router.get("/jobs", response_model=list[Job])
def listar_jobs(
    sv: ServicosDep,
    status: Annotated[list[JobStatus] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[Job]:
    return sv.store.listar(status, limit)


# Só a demonstração é criada por aqui. Os demais tipos nascem nas rotas das próprias ferramentas, que validam os
# parâmetros e passam o filtro de conteúdo: um POST direto aqui não pode driblar essas conferências.
TIPOS_PUBLICOS = frozenset({"demo.sleep"})


@router.post("/jobs", response_model=Job, status_code=201)
def criar_job(pedido: JobCreate, sv: ServicosDep) -> Job:
    if pedido.kind not in TIPOS_PUBLICOS:
        raise HTTPException(
            status_code=422, detail=f"tipo de job desconhecido ou criado só pela ferramenta: {pedido.kind}"
        )
    try:
        return enfileirar(sv, pedido.kind, pedido.params, titulo=pedido.title, prioridade=pedido.priority)
    except TipoDeJobDesconhecido as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/jobs/reorder", response_model=list[Job])
def reordenar(pedido: ReordenarPedido, sv: ServicosDep) -> list[Job]:
    jobs = sv.store.reordenar(pedido.ids)
    _publicar_retrato(sv)
    return jobs


@router.delete("/jobs/finished")
def limpar_finalizados(sv: ServicosDep) -> dict[str, int]:
    removidos = sv.store.limpar_finalizados()
    _publicar_retrato(sv)
    return {"removed": removidos}


@router.get("/jobs/{job_id}", response_model=Job)
def obter_job(job_id: IdJob, sv: ServicosDep) -> Job:
    job = sv.store.obter(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return job


@router.get("/jobs/{job_id}/logs", response_model=list[JobLog])
def logs_do_job(job_id: IdJob, sv: ServicosDep, limit: Annotated[int, Query(ge=1, le=2000)] = 500) -> list[JobLog]:
    if sv.store.obter(job_id) is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return sv.store.logs(job_id, limit)


@router.post("/jobs/{job_id}/cancel", response_model=Job)
def cancelar(job_id: IdJob, sv: ServicosDep) -> Job:
    return _publicar(sv, sv.store.cancelar(job_id))


@router.post("/jobs/{job_id}/pause", response_model=Job)
def pausar(job_id: IdJob, sv: ServicosDep) -> Job:
    return _publicar(sv, sv.store.pausar(job_id))


@router.post("/jobs/{job_id}/resume", response_model=Job)
def retomar(job_id: IdJob, sv: ServicosDep) -> Job:
    job = _publicar(sv, sv.store.retomar(job_id))
    if sv.worker is not None:
        sv.worker.acordar()
    return job


@router.get("/events")
async def eventos(request: Request, sv: ServicosDep) -> StreamingResponse:
    return StreamingResponse(
        gerar_eventos(sv, request.is_disconnected),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
