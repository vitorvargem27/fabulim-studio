"""Rotas das ferramentas e modelos (tela Modelos): o catálogo com o estado de cada item e a instalação como job.

A instalação só acontece quando o usuário clica em Instalar, e só de itens do catálogo (nunca de um endereço livre).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path

from ..ferramentas.catalogo import por_id
from ..ferramentas.instalador import Instalador
from ..jobs.models import ATIVOS, Job
from ..jobs.servico import enfileirar
from .deps import ServicosDep

router = APIRouter(prefix="/api/tools")

TIPO_DE_JOB = "ferramentas.instalar"


def _ids_em_instalacao(sv: Any) -> dict[str, str]:
    return {str(j.params.get("id")): j.id for j in sv.store.listar(ATIVOS) if j.kind == TIPO_DE_JOB}


@router.get("")
def listar(sv: ServicosDep) -> dict[str, Any]:
    ativos = _ids_em_instalacao(sv)
    itens = Instalador(sv.settings).situacao()
    for item in itens:
        item["job_id"] = ativos.get(item["id"])
    return {"items": itens, "tools_dir": str(sv.settings.tools_dir), "models_dir": str(sv.settings.models_dir)}


@router.post("/{id_}/install", response_model=Job, status_code=202)
def instalar(id_: Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9\-]{0,39}$")], sv: ServicosDep) -> Job:
    try:
        item = por_id(id_)
    except KeyError:
        raise HTTPException(status_code=404, detail="Ferramenta desconhecida") from None
    if Instalador(sv.settings).instalado(item):
        raise HTTPException(status_code=409, detail="Já está instalado")
    for job in sv.store.listar(ATIVOS):
        if job.kind == TIPO_DE_JOB and job.params.get("id") == id_:
            return job
    return enfileirar(sv, TIPO_DE_JOB, {"id": id_}, titulo=f"Instalar {item.nome}")
