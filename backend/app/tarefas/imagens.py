"""Gerar imagem avulsa: cada variação vai para a biblioteca assim que fica pronta (cancelar não perde as que já saíram)."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import ValidationError

from ..conteudo.filtro import verificar_campos, verificar_texto
from ..erros import ErroParaOUsuario
from ..imagens.servico import ParametrosDeImagem, prompt_tecnico_da_ficha, sementes
from ..jobs.handlers import TITULOS, job_handler
from ..jobs.worker import JobContext
from ..midias.servico import adotar_e_avisar
from ..motores.memoria import liberar_llm
from ..motores.tipos import PedidoImagem, dimensoes_da_imagem
from ..personagens import servico as personagens
from ..prompts.tecnico import NEGATIVO

TITULOS["imagem.gerar"] = "Gerar imagem"


@job_handler("imagem.gerar")
def gerar_imagens(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    sv = ctx.servicos
    try:
        pedido = ParametrosDeImagem.model_validate(params)
    except ValidationError as exc:
        raise ErroParaOUsuario("O pedido de imagem está incompleto ou inválido.") from exc
    reprovacao = verificar_campos(pedido.form.model_dump()) or verificar_texto(pedido.technical_prompt or "")
    if reprovacao:
        raise ErroParaOUsuario(reprovacao.motivo)
    quem, referencias = personagens.referencias(sv, pedido.character_ids)
    if pedido.based_on:
        base = sv.midias.obter(pedido.based_on)
        if base is None:
            raise ErroParaOUsuario("A imagem escolhida como base não está mais na biblioteca.")
        referencias = (*referencias, sv.midias.caminho_absoluto(base))
    prompt = (pedido.technical_prompt or "").strip() or prompt_tecnico_da_ficha(
        pedido.form, quem, com_referencia=bool(pedido.based_on)
    )
    largura, altura = dimensoes_da_imagem(pedido.form.format, pedido.quality)
    if liberados := liberar_llm(sv.ollama):
        ctx.log(f"Modelo de texto descarregado da memória para gerar imagem: {', '.join(liberados)}")
    sv.settings.temp_dir.mkdir(parents=True, exist_ok=True)
    total = pedido.count
    grupo = uuid.uuid4().hex
    ids: list[str] = []
    segundos: list[float] = []
    for indice, semente in enumerate(sementes(pedido.seed, total)):
        ctx.ponto_de_controle()
        ctx.progresso(indice / total, f"Gerando a imagem {indice + 1} de {total}")
        saida = sv.settings.temp_dir / f"img-{uuid.uuid4().hex}.png"
        resultado = sv.motores.imagem.gerar(
            ctx,
            PedidoImagem(prompt, largura, altura, semente, referencias=referencias),
            saida,
            faixa=(indice / total, (indice + 1) / total),
        )
        midia = adotar_e_avisar(
            sv,
            saida,
            tipo="imagem",
            papel=pedido.form.kind,
            extensao="png",
            largura=resultado.largura,
            altura=resultado.altura,
            pai_id=pedido.based_on,
            prompt=pedido.form.description,
            prompt_tecnico=prompt,
            negativo=NEGATIVO,
            estilo=pedido.form.style,
            seed=resultado.seed,
            modelo=resultado.modelo,
            job_id=ctx.job_id,
            metadados={
                "group": grupo,
                "index": indice,
                "count": total,
                "quality": pedido.quality,
                "format": pedido.form.format,
                "seconds": resultado.segundos,
                "run_path": resultado.caminho_de_execucao,
                "characters": [{"id": p.id, "name": p.nome} for p in quem],
                "notes": pedido.form.notes,
            },
        )
        ids.append(midia.id)
        segundos.append(resultado.segundos)
        ctx.log(f"Imagem {indice + 1} de {total} pronta em {resultado.segundos:.0f} s (semente {resultado.seed})")
    ctx.progresso(1.0, "Imagens salvas na biblioteca")
    return {"media_ids": ids, "group": grupo, "seconds": segundos, "width": largura, "height": altura}
