"""Gerar imagem avulsa: estimativa de tempo, prompt técnico (visível e editável) e o pedido de geração como job."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..conteudo.filtro import verificar_campos, verificar_texto
from ..imagens.servico import ParametrosDeImagem, estimar, prompt_tecnico_da_ficha
from ..jobs.models import Job
from ..jobs.servico import enfileirar
from ..personagens.servico import PersonagemSemImagem, referencias
from ..prompts.formatos import FichaImagem
from ..prompts.tecnico import NEGATIVO
from .deps import ServicosDep

router = APIRouter(prefix="/api/images")


class PedidoDePromptTecnico(BaseModel):
    form: FichaImagem
    character_ids: list[str] = Field(default_factory=list, max_length=3)
    based_on: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


def _conferir(sv: ServicosDep, pedido: ParametrosDeImagem) -> None:
    """Tudo o que dá para conferir antes de gastar minutos de geração: descrição, conteúdo, motor e personagens."""
    if not pedido.form.description.strip() and not (pedido.technical_prompt or "").strip():
        raise HTTPException(status_code=422, detail="Descreva a imagem que você quer gerar.")
    reprovacao = verificar_campos(pedido.form.model_dump()) or verificar_texto(pedido.technical_prompt or "")
    if reprovacao:
        raise HTTPException(status_code=422, detail=reprovacao.motivo)
    if motivo := sv.motores.imagem.indisponivel():
        raise HTTPException(status_code=503, detail=motivo)
    try:
        referencias(sv, pedido.character_ids)
    except PersonagemSemImagem as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if pedido.based_on and sv.midias.obter(pedido.based_on) is None:
        raise HTTPException(status_code=422, detail="A imagem escolhida como base não está mais na biblioteca.")


@router.get("/estimate")
def estimativa(
    sv: ServicosDep,
    formato: Annotated[Literal["16:9", "9:16", "1:1"], Query(alias="format")] = "16:9",
    quality: Annotated[Literal["rascunho", "padrao", "alta"], Query()] = "padrao",
    count: Annotated[int, Query(ge=1, le=4)] = 1,
    references: Annotated[int, Query(ge=0, le=4)] = 0,
) -> dict[str, Any]:
    return estimar(sv.motores.imagem, formato, quality, count, references > 0).para_api()


@router.post("/technical-prompt")
def prompt_tecnico(pedido: PedidoDePromptTecnico, sv: ServicosDep) -> dict[str, Any]:
    try:
        quem, _ = referencias(sv, pedido.character_ids)
    except PersonagemSemImagem as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    texto = prompt_tecnico_da_ficha(pedido.form, quem, com_referencia=bool(pedido.based_on))
    return {"technical_prompt": texto, "negative_prompt": NEGATIVO}


@router.post("", response_model=Job, status_code=202)
def gerar(pedido: ParametrosDeImagem, sv: ServicosDep) -> Job:
    _conferir(sv, pedido)
    quantidade = f"{pedido.count} imagens" if pedido.count > 1 else "1 imagem"
    return enfileirar(sv, "imagem.gerar", pedido.model_dump(mode="json"), titulo=f"Gerar imagem ({quantidade})")
