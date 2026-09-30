"""Rotas de sistema: saúde, status dos serviços, máquina, capacidades, logs e benchmark."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from ..config import NOME_APP, VERSAO
from ..jobs.models import Job
from ..jobs.servico import enfileirar, job_ativo_do_tipo
from ..logging_setup import ler_logs
from ..services.status import RelatorioStatus, coletar_status
from .deps import ServicosDep

router = APIRouter(prefix="/api")


@router.get("/health")
def saude() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/meta")
def meta(sv: ServicosDep) -> dict[str, Any]:
    return {
        "name": NOME_APP,
        "version": VERSAO,
        "host": sv.settings.host,
        "port": sv.settings.port,
        "data_dir": str(sv.settings.data_dir),
        "models_dir": str(sv.settings.models_dir),
        "tools_dir": str(sv.settings.tools_dir),
    }


@router.get("/status", response_model=RelatorioStatus)
def status(sv: ServicosDep) -> RelatorioStatus:
    return coletar_status(sv)


@router.get("/machine")
def maquina(sv: ServicosDep) -> dict[str, Any]:
    return sv.hardware.snapshot()


@router.get("/capabilities")
def capacidades(sv: ServicosDep) -> list[dict[str, Any]]:
    caps: list[dict[str, Any]] = sv.hardware.snapshot()["capabilities"]
    return caps


@router.post("/machine/diagnostic", response_model=Job, status_code=202)
def refazer_diagnostico(sv: ServicosDep, light: bool = False) -> Job:
    existente = job_ativo_do_tipo(sv, "system.diagnostico")
    if existente is not None:
        return existente
    titulo = "Diagnóstico da máquina (leve)" if light else "Diagnóstico da máquina"
    return enfileirar(sv, "system.diagnostico", {"leve": light}, titulo=titulo)


@router.get("/logs")
def logs(
    sv: ServicosDep,
    service: Annotated[str | None, Query(pattern=r"^[A-Za-z0-9_.\-]{1,60}$")] = None,
    level: Annotated[str | None, Query(pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")] = None,
    job_id: Annotated[str | None, Query(pattern=r"^[0-9a-f]{32}$")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[dict[str, Any]]:
    return ler_logs(sv.settings.log_dir, servico=service, nivel=level, job_id=job_id, limite=limit)


@router.get("/benchmark")
def benchmark(sv: ServicosDep) -> dict[str, Any]:
    return {"results": sv.benchmarks.ultimos(), "measurements": sv.benchmarks.medicoes()}


@router.post("/benchmark/run", response_model=Job, status_code=202)
def rodar_benchmark(sv: ServicosDep) -> Job:
    existente = job_ativo_do_tipo(sv, "benchmark.calibracao")
    return existente if existente is not None else enfileirar(sv, "benchmark.calibracao")
