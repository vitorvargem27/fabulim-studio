"""Prompts colados: ler o formato estruturado na hora, o texto livre pelo modelo local (como job), filtro e histórico.

O texto do usuário é dado, nunca instrução: o parser só extrai campos, o filtro de conteúdo examina, e nada disso muda o
comportamento do sistema. Tudo o que volta é um formulário validado por schema para o usuário revisar antes de gerar.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from ..conteudo.filtro import verificar_texto
from ..jobs.servico import enfileirar
from ..prompts.leitura import resposta_da_leitura
from ..prompts.parser import contar_rotulos, detectar_tipo, interpretar_estruturado
from .deps import ServicosDep

router = APIRouter(prefix="/api/prompts")

TipoDePrompt = Literal["personagem", "enredo", "imagem"]


class PedidoLeitura(BaseModel):
    text: str = Field(min_length=1, max_length=30_000)
    type: TipoDePrompt | None = None


class PedidoVerificacao(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=40)


@router.post("/parse")
def ler(pedido: PedidoLeitura, sv: ServicosDep) -> dict[str, Any]:
    texto = pedido.text.strip()
    if not texto:
        raise HTTPException(status_code=422, detail="Cole ou escreva o prompt primeiro.")
    do_cabecalho = detectar_tipo(texto)
    tipo = do_cabecalho or pedido.type
    if tipo is None:
        raise HTTPException(status_code=422, detail="Diga se é um prompt de personagem, de enredo ou de imagem.")
    sv.historico.registrar(tipo, texto)
    if do_cabecalho is not None or contar_rotulos(texto, tipo) >= 2:
        return resposta_da_leitura(interpretar_estruturado(texto, tipo), texto)
    # texto livre: antes de gastar minutos do modelo local, o filtro já barra marca de terceiros e temas proibidos
    if reprovacao := verificar_texto(texto):
        return {"status": "blocked", "detected_type": tipo, "result": None, "blocked": reprovacao.para_api()}
    if motivo := sv.motores.texto.indisponivel():
        raise HTTPException(status_code=503, detail=motivo)
    job = enfileirar(sv, "prompt.interpretar", {"text": texto, "type": tipo}, titulo="Ler o prompt com o modelo local")
    return {"status": "queued", "detected_type": tipo, "job": job.model_dump(mode="json")}


@router.post("/check")
def verificar(pedido: PedidoVerificacao) -> dict[str, Any]:
    for texto in pedido.texts:
        if reprovacao := verificar_texto(texto):
            return {"ok": False, "blocked": reprovacao.para_api()}
    return {"ok": True, "blocked": None}


@router.get("/history")
def historico(
    sv: ServicosDep,
    tipo: Annotated[TipoDePrompt | None, Query(alias="type")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> list[dict[str, Any]]:
    return sv.historico.listar(tipo, limit)


@router.delete("/history/{id_}")
def apagar_do_historico(id_: Annotated[int, Path(ge=1)], sv: ServicosDep) -> dict[str, bool]:
    return {"deleted": sv.historico.remover(id_)}


@router.delete("/history")
def limpar_historico(
    sv: ServicosDep, tipo: Annotated[TipoDePrompt | None, Query(alias="type")] = None
) -> dict[str, int]:
    return {"removed": sv.historico.limpar(tipo)}
