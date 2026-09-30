"""Personagens: variações, recorte de fundo (PNG transparente), folha de referência e voz de teste.

Cada imagem entra na biblioteca de mídias assim que fica pronta, ligada ao personagem (``dono_tipo='personagem'``) e à
versão da ficha (``character_version``): editar o personagem nunca apaga o que já foi gerado.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from ..erros import ErroParaOUsuario
from ..imagens.servico import sementes
from ..jobs.handlers import TITULOS, job_handler
from ..jobs.worker import JobContext
from ..midias.repositorio import Midia
from ..midias.servico import adotar_e_avisar
from ..motores.audio import alterar_tom
from ..motores.memoria import liberar_llm
from ..motores.tipos import ItemDeVoz, PedidoImagem, dimensoes_da_imagem
from ..personagens.pedidos import (
    ParametrosDeFolha,
    ParametrosDeRecorte,
    ParametrosDeVariacoes,
    ParametrosDeVozDeTeste,
)
from ..personagens.repositorio import Personagem
from ..personagens.servico import ficha_do_personagem, imagem_principal, voz_sugerida, voz_valida
from ..prompts.tecnico import NEGATIVO, direcao_do_slot, prompt_personagem, prompt_pose
from .comum import carregar_personagem, conferir_conteudo, temporario, validar

TITULOS["personagem.variacoes"] = "Variações do personagem"
TITULOS["personagem.recortar"] = "Recortar o fundo do personagem"
TITULOS["personagem.folha"] = "Folha de referência do personagem"
TITULOS["personagem.voz_teste"] = "Voz de teste do personagem"

PARTE_DA_IMAGEM = 0.8  # na folha, cada pose gasta ~80% do tempo gerando e ~20% recortando o fundo


def recortes_da_imagem(sv: Any, midia_id: str) -> list[Midia]:
    """Os recortes (PNG transparente) que já saíram de uma imagem."""
    lista: list[Midia] = sv.midias.listar(papeis=("recorte",), pai_id=midia_id, limite=20)
    return lista


def _recortar_e_guardar(
    ctx: JobContext, personagem: Personagem, origem: Midia, slot: str, faixa: tuple[float, float]
) -> Midia:
    sv = ctx.servicos
    saida = temporario(sv, "recorte", "png")
    dados = sv.motores.recorte.recortar(ctx, sv.midias.caminho_absoluto(origem), saida, caixa=True, faixa=faixa)
    return adotar_e_avisar(
        sv,
        saida,
        tipo="imagem",
        papel="recorte",
        extensao="png",
        pai_id=origem.id,
        dono_tipo="personagem",
        dono_id=personagem.id,
        estilo=personagem.estilo,
        prompt=origem.prompt,
        modelo="BiRefNet lite",
        job_id=ctx.job_id,
        metadados={
            "slot": slot,
            "facing": direcao_do_slot(slot),
            "character_version": personagem.versao,
            "cutout_seconds": dados.get("wall_s"),
        },
    )


@job_handler("personagem.variacoes")
def gerar_variacoes(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    sv = ctx.servicos
    pedido = validar(ParametrosDeVariacoes, params, "variações")
    personagem = carregar_personagem(sv, pedido.character_id)
    ficha = ficha_do_personagem(personagem)
    prompt = (pedido.technical_prompt or personagem.prompt_tecnico or prompt_personagem(ficha)).strip()
    conferir_conteudo(ficha.model_dump(), prompt)
    referencias: tuple[Path, ...] = ()
    if pedido.reference_media_id:
        base = sv.midias.obter(pedido.reference_media_id)
        if base is None:
            raise ErroParaOUsuario("A imagem de referência não está mais na biblioteca.")
        referencias = (sv.midias.caminho_absoluto(base),)
    largura, altura = dimensoes_da_imagem("1:1", pedido.quality)
    if liberados := liberar_llm(sv.ollama):
        ctx.log(f"Modelo de texto descarregado da memória: {', '.join(liberados)}")
    grupo = uuid.uuid4().hex
    total = pedido.count
    ids: list[str] = []
    for indice, semente in enumerate(sementes(pedido.seed, total)):
        ctx.ponto_de_controle()
        ctx.progresso(indice / total, f"Desenhando a variação {indice + 1} de {total}")
        saida = temporario(sv, "variacao", "png")
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
            papel="variacao",
            extensao="png",
            largura=resultado.largura,
            altura=resultado.altura,
            dono_tipo="personagem",
            dono_id=personagem.id,
            pai_id=pedido.reference_media_id,
            prompt=personagem.prompt_original or ficha.appearance,
            prompt_tecnico=prompt,
            negativo=NEGATIVO,
            estilo=personagem.estilo,
            seed=resultado.seed,
            modelo=resultado.modelo,
            job_id=ctx.job_id,
            metadados={
                "group": grupo,
                "index": indice,
                "quality": pedido.quality,
                "character_version": personagem.versao,
                "seconds": resultado.segundos,
                "run_path": resultado.caminho_de_execucao,
                "from_reference": bool(referencias),
            },
        )
        ids.append(midia.id)
        ctx.log(f"Variação {indice + 1} de {total} pronta em {resultado.segundos:.0f} s (semente {resultado.seed})")
    if personagem.estado == "rascunho":
        sv.personagens.definir_estado(personagem.id, "variacoes")
    ctx.progresso(1.0, "Variações prontas")
    return {"media_ids": ids, "group": grupo}


@job_handler("personagem.recortar")
def recortar_personagem(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    sv = ctx.servicos
    pedido = validar(ParametrosDeRecorte, params, "recorte")
    personagem = carregar_personagem(sv, pedido.character_id)
    origem = sv.midias.obter(pedido.media_id)
    if origem is None or origem.dono_id != personagem.id:
        raise ErroParaOUsuario("A imagem para recortar não pertence a este personagem.")
    ctx.progresso(0.02, "Recortando o fundo...")
    recorte = _recortar_e_guardar(ctx, personagem, origem, pedido.slot, (0.02, 0.98))
    ctx.progresso(1.0, "Personagem recortado")
    return {"media_id": recorte.id, "slot": pedido.slot}


@job_handler("personagem.folha")
def gerar_folha(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    sv = ctx.servicos
    pedido = validar(ParametrosDeFolha, params, "folha de referência")
    personagem = carregar_personagem(sv, pedido.character_id)
    ficha = ficha_do_personagem(personagem)
    principal = imagem_principal(sv, personagem)
    conferir_conteudo(ficha.model_dump())
    midia_principal = sv.midias.obter(personagem.imagem_principal_id or "")
    if midia_principal is None:
        raise ErroParaOUsuario("A imagem principal do personagem não está mais na biblioteca.")
    largura, altura = dimensoes_da_imagem("1:1", pedido.quality)
    if liberados := liberar_llm(sv.ollama):
        ctx.log(f"Modelo de texto descarregado da memória: {', '.join(liberados)}")
    precisa_principal = not recortes_da_imagem(sv, midia_principal.id)
    unidades = len(pedido.slots) + (1 if precisa_principal else 0)
    feitos = 0
    ids: list[str] = []
    if precisa_principal:
        ctx.ponto_de_controle()
        ctx.progresso(0.0, "Recortando o fundo da imagem principal")
        recorte = _recortar_e_guardar(ctx, personagem, midia_principal, "principal", (0.0, 1 / unidades))
        ids.append(recorte.id)
        feitos = 1
    base = pedido.seed
    for slot, semente in zip(pedido.slots, sementes(base, len(pedido.slots)), strict=True):
        ctx.ponto_de_controle()
        ini, fim = feitos / unidades, (feitos + 1) / unidades
        corte = ini + (fim - ini) * PARTE_DA_IMAGEM
        ctx.progresso(ini, f"Desenhando «{slot}» ({feitos + 1 - int(precisa_principal)} de {len(pedido.slots)})")
        saida = temporario(sv, "pose", "png")
        prompt = prompt_pose(ficha, slot)
        resultado = sv.motores.imagem.gerar(
            ctx, PedidoImagem(prompt, largura, altura, semente, referencias=(principal,)), saida, faixa=(ini, corte)
        )
        pose = adotar_e_avisar(
            sv,
            saida,
            tipo="imagem",
            papel="pose",
            extensao="png",
            largura=resultado.largura,
            altura=resultado.altura,
            dono_tipo="personagem",
            dono_id=personagem.id,
            pai_id=midia_principal.id,
            prompt=personagem.prompt_original or ficha.appearance,
            prompt_tecnico=prompt,
            negativo=NEGATIVO,
            estilo=personagem.estilo,
            seed=resultado.seed,
            modelo=resultado.modelo,
            job_id=ctx.job_id,
            metadados={
                "slot": slot,
                "facing": direcao_do_slot(slot),
                "quality": pedido.quality,
                "character_version": personagem.versao,
                "seconds": resultado.segundos,
            },
        )
        ids.append(pose.id)
        ctx.progresso(corte, f"Recortando o fundo de «{slot}»")
        recorte = _recortar_e_guardar(ctx, personagem, pose, slot, (corte, fim))
        ids.append(recorte.id)
        feitos += 1
        ctx.log(f"«{slot}» pronta: imagem em {resultado.segundos:.0f} s e recorte salvo")
    sv.personagens.definir_estado(personagem.id, "pronto")
    ctx.progresso(1.0, "Folha de referência pronta")
    return {"media_ids": ids, "slots": pedido.slots}


@job_handler("personagem.voz_teste")
def falar_frase_de_teste(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    sv = ctx.servicos
    pedido = validar(ParametrosDeVozDeTeste, params, "voz de teste")
    personagem = carregar_personagem(sv, pedido.character_id)
    conferir_conteudo({"text": pedido.text})
    try:
        voz = voz_valida(pedido.voice or personagem.voz or voz_sugerida(ficha_do_personagem(personagem)))
    except ValueError as exc:
        raise ErroParaOUsuario(str(exc)) from exc
    if liberados := liberar_llm(sv.ollama):
        ctx.log(f"Modelo de texto descarregado da memória: {', '.join(liberados)}")
    ctx.progresso(0.03, "Preparando a voz...")
    bruto = temporario(sv, "fala", "wav")
    final = temporario(sv, "voz", "wav")
    try:
        [fala] = sv.motores.voz.falar(
            ctx, [ItemDeVoz(pedido.text, voz["id"], voz["speed"], voz["lang_code"], bruto)], faixa=(0.03, 0.85)
        )
        ctx.progresso(0.88, "Ajustando o tom da voz...")
        alterar_tom(sv.motores.ffmpeg, ctx, bruto, final, voz["pitch"])
    finally:
        bruto.unlink(missing_ok=True)
    midia = adotar_e_avisar(
        sv,
        final,
        tipo="audio",
        papel="voz_teste",
        extensao="wav",
        duracao_s=fala.duracao_s,
        dono_tipo="personagem",
        dono_id=personagem.id,
        prompt=pedido.text,
        modelo="Kokoro 82M",
        job_id=ctx.job_id,
        metadados={"voice": voz, "character_version": personagem.versao},
    )
    ctx.progresso(1.0, "Voz pronta para ouvir")
    return {"media_id": midia.id, "duration_s": fala.duracao_s, "voice": voz}
