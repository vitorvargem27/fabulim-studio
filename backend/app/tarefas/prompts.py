"""Ler um prompt em texto livre com o modelo local: o resultado é um formulário para o usuário revisar."""

from __future__ import annotations

from typing import Any

from ..jobs.handlers import TITULOS, job_handler
from ..jobs.worker import JobContext
from ..prompts.formatos import TIPOS
from ..prompts.leitura import resposta_da_leitura
from ..prompts.livre import interpretar_livre

TITULOS["prompt.interpretar"] = "Ler o prompt com o modelo local"


@job_handler("prompt.interpretar")
def interpretar_prompt(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    texto = str(params.get("text") or "").strip()[:30_000]
    tipo = str(params.get("type"))
    if tipo not in TIPOS or not texto:
        raise RuntimeError("pedido de leitura inválido")
    ctx.progresso(0.03, "Lendo o texto com o modelo local...")
    interpretacao = interpretar_livre(ctx, ctx.servicos.motores.texto, texto, tipo)
    ctx.log(f"Formulário de {tipo} preenchido pelo modelo local ({len(interpretacao.faltando)} campo(s) faltando)")
    ctx.progresso(1.0, "Formulário preenchido")
    return resposta_da_leitura(interpretacao, texto)
