"""O que as tarefas da fila têm em comum: validar os parâmetros, achar o personagem e conferir o conteúdo de novo."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError

from ..conteudo.filtro import verificar_campos, verificar_texto
from ..erros import ErroParaOUsuario
from ..personagens.repositorio import Personagem

if TYPE_CHECKING:
    from ..container import Servicos


def validar[M: BaseModel](modelo: type[M], params: dict[str, Any], o_que: str) -> M:
    """Os parâmetros do job vêm do banco: valida de novo (defesa em profundidade) e explica em português."""
    try:
        return modelo.model_validate(params)
    except ValidationError as exc:
        raise ErroParaOUsuario(f"O pedido de {o_que} está incompleto ou inválido.") from exc


def carregar_personagem(sv: Servicos, id_: str) -> Personagem:
    personagem = sv.personagens.obter(id_)
    if personagem is None:
        raise ErroParaOUsuario("O personagem não existe mais na biblioteca.")
    return personagem


def conferir_conteudo(campos: dict[str, Any] | None = None, *textos: str) -> None:
    """Filtro de conteúdo para 2 a 5 anos: o job confere de novo, mesmo que o pedido não tenha vindo pela API."""
    reprovacao = verificar_campos(campos or {})
    for texto in textos:
        reprovacao = reprovacao or verificar_texto(texto)
    if reprovacao:
        raise ErroParaOUsuario(reprovacao.motivo)


def temporario(sv: Servicos, prefixo: str, extensao: str) -> Path:
    """Um caminho novo dentro da pasta temporária do projeto (o motor escreve ali; depois a mídia é movida para a biblioteca)."""
    sv.settings.temp_dir.mkdir(parents=True, exist_ok=True)
    return sv.settings.temp_dir / f"{prefixo}-{uuid.uuid4().hex}.{extensao}"
