"""Projetos: roteiro (modelo local ou modo simples) e storyboard (cenário de cada cena, com os personagens por cima)."""

from __future__ import annotations

import time
from typing import Any

from ..animacao.render import quadro_de_capa
from ..erros import ErroParaOUsuario
from ..imagens.servico import sementes
from ..jobs.handlers import TITULOS, job_handler
from ..jobs.worker import JobContext
from ..midias.servico import adotar_e_avisar
from ..motores.memoria import liberar_llm
from ..motores.tipos import MotorFalhou, MotorIndisponivel, PedidoImagem, dimensoes_da_imagem
from ..personagens.repositorio import Personagem
from ..projetos.cenas import DadosDaCena, ImagemDaCena
from ..projetos.estado import carregar_projeto, cenas_do_projeto, dados_atuais, limpar_midias_antigas
from ..projetos.pedidos import ParametrosDoRoteiro, ParametrosDoStoryboard
from ..projetos.pipeline import (
    cena_para_render,
    descricao_do_cenario,
    escolher_recorte,
    layout_da_cena,
    personagens_do_projeto,
    resolucao,
)
from ..projetos.repositorio import Projeto
from ..projetos.roteiro import ResultadoDoRoteiro, roteiro_por_ia, roteiro_simples
from ..prompts.formatos import FichaEnredo
from ..prompts.tecnico import NEGATIVO, prompt_cenario
from .comum import conferir_conteudo, temporario, validar

TITULOS["projeto.roteiro"] = "Roteiro do vídeo"
TITULOS["projeto.storyboard"] = "Storyboard do vídeo"
ROTEIROS_GUARDADOS = 3


def ficha_do_enredo(projeto: Projeto) -> FichaEnredo:
    return FichaEnredo.model_validate(projeto.enredo)


@job_handler("projeto.roteiro")
def gerar_roteiro(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    sv = ctx.servicos
    pedido = validar(ParametrosDoRoteiro, params, "roteiro")
    projeto = carregar_projeto(sv, pedido.project_id)
    ficha = ficha_do_enredo(projeto)
    conferir_conteudo(ficha.model_dump())
    personagens = personagens_do_projeto(sv, projeto)
    resultado: ResultadoDoRoteiro | None = None
    avisos_do_job: list[str] = []
    ctx.progresso(0.02, "Lendo a história...")
    if pedido.mode == "ia":
        try:
            resultado = roteiro_por_ia(
                ctx, sv.motores.texto, ficha, personagens, projeto.duracao_alvo_s, faixa=(0.03, 0.92)
            )
        except (MotorIndisponivel, MotorFalhou) as exc:
            ctx.log(f"O modelo local não escreveu o roteiro ({exc}); usando o modo simples", "WARNING")
            avisos_do_job.append(f"O modelo local não conseguiu escrever o roteiro ({exc}). Usei o modo simples.")
        else:
            if not resultado.cenas:
                avisos_do_job.append("O modelo local não devolveu nenhuma cena utilizável. Usei o modo simples.")
                resultado = None
    if resultado is None:
        resultado = roteiro_simples(ficha, personagens, projeto.duracao_alvo_s)
    ctx.ponto_de_controle()
    # o roteiro anterior fica guardado (nada é sobrescrito); as cenas antigas e o que foi gerado para elas saem
    antigas = sv.projetos.cenas(projeto.id)
    historico = list(projeto.configuracoes.get("script_history", []))
    if antigas:
        historico.insert(0, {"created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "scenes": [c.dados for c in antigas]})
    for cena in antigas:
        sv.midias.remover_do_dono("cena", cena.id)
    sv.projetos.apagar_todas_as_cenas(projeto.id)
    ligacao = (projeto.configuracoes.get("continuation") or {}).get("junction")
    if ligacao:  # continuação de um vídeo: a primeira cena é igual ao último quadro do original (junção imperceptível)
        sv.projetos.criar_cena(projeto.id, ligacao)
    for dados in resultado.cenas:
        sv.projetos.criar_cena(projeto.id, dados.model_dump())
    aprovacoes = {k: v for k, v in projeto.aprovacoes.items() if k == "enredo"}
    sv.projetos.atualizar(
        projeto.id,
        etapa="roteiro",
        aprovacoes=aprovacoes,
        titulo=projeto.titulo or resultado.titulo or "Meu vídeo",
        configuracoes={**projeto.configuracoes, "script_history": historico[:ROTEIROS_GUARDADOS]},
    )
    avisos = [*avisos_do_job, *resultado.avisos]
    for aviso in avisos:
        ctx.log(aviso, "WARNING")
    ctx.progresso(1.0, f"Roteiro pronto: {len(resultado.cenas)} cenas")
    return {"scenes": len(resultado.cenas), "origin": resultado.origem, "warnings": avisos}


# --- storyboard ------------------------------------------------------------------------------------------------------------
def compor_capa(
    sv: Any,
    projeto: Projeto,
    cena_id: str,
    dados: DadosDaCena,
    personagens: dict[str, Personagem],
    job_id: str | None = None,
) -> str:
    """A imagem da cena (cenário + personagens nas posições do layout) que aparece no storyboard. Devolve o id da mídia."""
    render, _ = cena_para_render(sv, projeto, dados, personagens, max(dados.duration_s, 2.0), 24)
    largura, altura = resolucao(projeto.proporcao, "rascunho")
    quadro = quadro_de_capa(render, largura, altura, t=1.0)
    saida = temporario(sv, "capa", "jpg")
    quadro.convert("RGB").save(saida, "JPEG", quality=88)
    midia = adotar_e_avisar(
        sv,
        saida,
        tipo="imagem",
        papel="quadro",
        extensao="jpg",
        dono_tipo="cena",
        dono_id=cena_id,
        prompt=descricao_do_cenario(dados, list(personagens.values())),
        estilo=projeto.estilo,
        job_id=job_id,
        metadados={"project_id": projeto.id, "kind": "keyframe"},
    )
    return str(midia.id)


def recompor_capa_da_cena(sv: Any, projeto: Projeto, cena_id: str, job_id: str | None = None) -> str:
    """Refaz a imagem da cena com o cenário e o layout de agora (sem gerar cenário novo). Troca a capa antiga pela nova."""
    dados = dados_atuais(sv, cena_id)
    if dados is None:
        raise ErroParaOUsuario("A cena não existe mais.")
    personagens = {p.id: p for p in personagens_do_projeto(sv, projeto)}
    nova = compor_capa(sv, projeto, cena_id, dados, personagens, job_id)
    antiga = dados.keyframe_media_id
    novos = dados.model_dump()
    novos["keyframe_media_id"] = nova
    sv.projetos.atualizar_cena_sem_versao(cena_id, DadosDaCena.model_validate(novos).model_dump())
    limpar_midias_antigas(sv, [antiga], {nova})
    return nova


@job_handler("projeto.storyboard")
def gerar_storyboard(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    sv = ctx.servicos
    pedido = validar(ParametrosDoStoryboard, params, "storyboard")
    projeto = carregar_projeto(sv, pedido.project_id)
    todas = cenas_do_projeto(sv, projeto, pedido.scene_ids)
    if not todas:
        raise ErroParaOUsuario("Este projeto ainda não tem cenas. Gere o roteiro primeiro.")
    personagens = {p.id: p for p in personagens_do_projeto(sv, projeto)}
    lista = list(personagens.values())
    for _, dados in todas:  # antes de gastar minutos de geração: todo personagem da cena precisa ter o PNG transparente
        for item in layout_da_cena(projeto, dados):
            personagem = personagens.get(item.personagem_id)
            if personagem is None:
                raise ErroParaOUsuario("Uma cena usa um personagem que não está mais na biblioteca.")
            escolher_recorte(sv, personagem, dados.emotion, "respirar", item.pose)
    para_gerar = [(c, d) for c, d in todas if pedido.mode != "faltantes" or d.background is None]
    largura, altura = dimensoes_da_imagem(projeto.proporcao, pedido.quality)
    if para_gerar and (liberados := liberar_llm(sv.ollama)):
        ctx.log(f"Modelo de texto descarregado da memória: {', '.join(liberados)}")
    total = max(len(para_gerar) * pedido.variations, 1)
    feitas = 0
    gerados: dict[str, list[str]] = {}
    for cena, dados_lidos in para_gerar:
        conferir_conteudo(dados_lidos.model_dump(include={"visual", "action", "setting", "narration", "title"}))
        descricao = descricao_do_cenario(dados_lidos, lista)
        prompt = prompt_cenario(descricao, projeto.estilo)
        base = pedido.seed if pedido.seed is not None else dados_lidos.seed_hint
        novos: list[str] = []
        primeiro_seed: int | None = None
        for seed in sementes(base, pedido.variations):
            ctx.ponto_de_controle()
            ctx.progresso(feitas / total, f"Cenário da cena {cena.ordem} ({feitas + 1} de {total})")
            saida = temporario(sv, "fundo", "png")
            resultado = sv.motores.imagem.gerar(
                ctx, PedidoImagem(prompt, largura, altura, seed), saida, faixa=(feitas / total, (feitas + 1) / total)
            )
            midia = adotar_e_avisar(
                sv,
                saida,
                tipo="imagem",
                papel="fundo",
                extensao="png",
                largura=resultado.largura,
                altura=resultado.altura,
                dono_tipo="cena",
                dono_id=cena.id,
                prompt=descricao,
                prompt_tecnico=prompt,
                negativo=NEGATIVO,
                estilo=projeto.estilo,
                seed=resultado.seed,
                modelo=resultado.modelo,
                job_id=ctx.job_id,
                metadados={"project_id": projeto.id, "quality": pedido.quality, "seconds": resultado.segundos},
            )
            primeiro_seed = primeiro_seed if primeiro_seed is not None else resultado.seed
            novos.append(midia.id)
            feitas += 1
        gerados[cena.id] = novos
        atual = dados_atuais(sv, cena.id) or dados_lidos
        mudar = atual.model_dump()
        mudar["candidates"] = [*atual.candidates, *novos][-12:]
        if pedido.mode != "variacoes" or atual.background is None:
            mudar["background"] = ImagemDaCena(
                media_id=novos[0], seed=primeiro_seed, prompt=descricao, quality=pedido.quality
            ).model_dump()
            mudar["approved"] = {**atual.approved, "storyboard": False, "animacao": False}
        salvas = sv.projetos.atualizar_cena(cena.id, DadosDaCena.model_validate(mudar).model_dump(), "cenário gerado")
        assert salvas is not None
        recompor_capa_da_cena(sv, projeto, cena.id, ctx.job_id)
        ctx.log(f"Cena {cena.ordem}: {len(novos)} cenário(s) gerado(s)")
    # cenas que já tinham cenário mas ainda não tinham a imagem composta
    for cena, _ in todas:
        depois = dados_atuais(sv, cena.id)
        if depois is not None and depois.background is not None and depois.keyframe_media_id is None:
            recompor_capa_da_cena(sv, projeto, cena.id, ctx.job_id)
    if projeto.etapa in ("enredo", "roteiro"):
        sv.projetos.atualizar(projeto.id, etapa="storyboard")
    ctx.progresso(1.0, "Storyboard pronto")
    return {"generated": gerados, "scenes": len(todas)}
