"""Biblioteca de personagens: criar a partir de prompt ou de imagem, variações, escolher, folha de referência, voz e 2D↔3D."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..conteudo.filtro import verificar_campos, verificar_texto
from ..jobs.models import Job
from ..jobs.servico import enfileirar
from ..midias.servico import adotar_e_avisar
from ..motores.recorte import ESTIMATIVA_SEGUNDOS as SEGUNDOS_DO_RECORTE
from ..motores.tipos import dimensoes_da_imagem
from ..motores.util import formatar_duracao
from ..motores.voz import VOZES
from ..personagens import fluxos
from ..personagens.pedidos import (
    ParametrosDeFolha,
    ParametrosDeRecorte,
    ParametrosDeVariacoes,
    ParametrosDeVozDeTeste,
    PedidoDeConversao,
    PedidoDeCriacao,
    PedidoDeEdicao,
    PedidoDeEscolha,
    PedidoDeFolha,
    PedidoDeVariacoes,
    PedidoDeVoz,
    PedidoDeVozDeTeste,
)
from ..personagens.repositorio import NomeEmUso, Personagem
from ..personagens.servico import ficha_do_personagem, voz_sugerida, voz_valida
from ..projetos.roteiro import achar_personagem
from ..prompts.formatos import FichaPersonagem
from ..prompts.parser import normalizar
from ..prompts.tecnico import prompt_outro_estilo, prompt_personagem
from ..security.caminhos import nome_de_arquivo_seguro
from ..security.uploads import MAX_IMAGEM_BYTES, UploadInvalido, sanitizar_imagem
from .deps import ServicosDep

router = APIRouter(prefix="/api/characters")

IdPersonagem = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


def _achar(sv: ServicosDep, id_: str) -> Personagem:
    personagem = sv.personagens.obter(id_)
    if personagem is None:
        raise HTTPException(status_code=404, detail="Personagem não encontrado")
    return personagem


def _exigir(sv: ServicosDep, *motores: str) -> None:
    if motivo := sv.motores.motivo(*motores):
        raise HTTPException(status_code=503, detail=motivo)


def _conferir_ficha(ficha: FichaPersonagem, original: str = "", *, exigir_aparencia: bool = True) -> None:
    if not ficha.name.strip():
        raise HTTPException(status_code=422, detail="Dê um nome ao personagem.")
    if exigir_aparencia and not ficha.appearance.strip():
        raise HTTPException(
            status_code=422, detail="Descreva a aparência do personagem (corpo, rosto, olhos, pelo...)."
        )
    reprovacao = verificar_campos(ficha.model_dump()) or verificar_texto(original)
    if reprovacao:
        raise HTTPException(status_code=422, detail=reprovacao.motivo)


def _conflito(sv: ServicosDep, mensagem: str, nome: str, estilo: str) -> JSONResponse:
    existente = sv.personagens.obter_por_nome(nome, estilo)
    corpo: dict[str, Any] = {"detail": mensagem}
    if existente is not None and existente.estilo == estilo:
        corpo["existing_id"] = existente.id
    return JSONResponse(corpo, status_code=409)


def _com_job(sv: ServicosDep, personagem: Personagem, job: Job | None) -> dict[str, Any]:
    return {"character": fluxos.resumo(sv, personagem), "job": job.model_dump(mode="json") if job else None}


class PedidoDeResolucao(BaseModel):
    names: list[str] = Field(min_length=1, max_length=12)
    style: Literal["2D", "3D"] | None = None


@router.post("/resolve")
def resolver_nomes(pedido: PedidoDeResolucao, sv: ServicosDep) -> dict[str, Any]:
    """Os nomes citados num enredo: quais já estão na biblioteca (no estilo do vídeo), quais só existem no outro estilo e
    quais faltam ("Criar este personagem agora")."""
    todos = sv.personagens.listar(limite=1000)
    achados: list[dict[str, Any]] = []
    faltando: list[str] = []
    outro_estilo: list[dict[str, Any]] = []
    unicos: dict[str, str] = {}
    for citado in pedido.names:
        if citado.strip():
            unicos.setdefault(
                normalizar(citado), citado.strip()
            )  # o mesmo nome com outra caixa ou acento conta uma vez só
    for nome in unicos.values():
        no_estilo = [p for p in todos if pedido.style is None or p.estilo == pedido.style]
        encontrado = achar_personagem(nome, no_estilo)
        if encontrado is not None:
            achados.append(fluxos.resumo(sv, encontrado))
            continue
        em_outro = achar_personagem(nome, todos)
        if em_outro is None:
            faltando.append(nome)
        else:
            outro_estilo.append(
                {"name": nome, "available_style": em_outro.estilo, "character": fluxos.resumo(sv, em_outro)}
            )
    return {"found": achados, "missing": faltando, "other_style": outro_estilo}


@router.get("/voices")
def vozes() -> dict[str, Any]:
    return {"voices": VOZES}


@router.get("/estimate")
def estimativa(
    sv: ServicosDep,
    kind: Annotated[Literal["variations", "conversion", "sheet", "cutout"], Query()] = "variations",
    count: Annotated[int, Query(ge=1, le=8)] = 4,
    quality: Annotated[Literal["rascunho", "padrao"], Query()] = "rascunho",
) -> dict[str, Any]:
    largura, altura = dimensoes_da_imagem("1:1", quality)
    motor = sv.motores.imagem
    if kind == "cutout":
        total, por_imagem = SEGUNDOS_DO_RECORTE, SEGUNDOS_DO_RECORTE
    elif kind == "sheet":
        por_imagem = motor.estimativa(largura, altura, True) + SEGUNDOS_DO_RECORTE
        total = por_imagem * count
    else:
        por_imagem = motor.estimativa(largura, altura, kind == "conversion")
        total = por_imagem * count
    return {
        "width": largura,
        "height": altura,
        "per_item_seconds": round(por_imagem, 1),
        "total_seconds": round(total, 1),
        "total_label": formatar_duracao(total),
    }


@router.get("")
def listar(
    sv: ServicosDep,
    q: Annotated[str | None, Query(max_length=80)] = None,
    style: Annotated[Literal["2D", "3D"] | None, Query()] = None,
) -> dict[str, Any]:
    personagens = sv.personagens.listar(busca=q, estilo=style)
    return {"items": [fluxos.resumo(sv, p) for p in personagens], "total": len(personagens)}


@router.post("", status_code=201)
def criar(pedido: PedidoDeCriacao, sv: ServicosDep) -> Any:
    ficha = pedido.form.model_copy(update={"name": pedido.form.name.strip()})
    _conferir_ficha(ficha, pedido.original_prompt)
    try:
        personagem = sv.personagens.criar(
            ficha.name,
            ficha.style,
            ficha.model_dump(),
            prompt_original=pedido.original_prompt,
            prompt_tecnico=prompt_personagem(ficha),
            voz=voz_sugerida(ficha),
        )
    except NomeEmUso as exc:
        return _conflito(sv, str(exc), ficha.name, ficha.style)
    return fluxos.resumo(sv, personagem)


@router.post("/upload", status_code=201)
async def enviar_imagem_de_personagem(
    request: Request,
    sv: ServicosDep,
    name: Annotated[str, Query(min_length=1, max_length=80)],
    style: Annotated[Literal["2D", "3D"], Query()] = "2D",
    rights: Annotated[bool, Query()] = False,
    file_name: Annotated[str, Query(min_length=1, max_length=120)] = "personagem.png",
) -> Any:
    """Cadastra um personagem a partir de uma imagem que o usuário já tem (com confirmação do direito de uso)."""
    if not rights:
        raise HTTPException(status_code=422, detail="Confirme que você tem o direito de usar esta imagem.")
    ficha = FichaPersonagem(name=name.strip(), style=style)
    _conferir_ficha(ficha, exigir_aparencia=False)
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > MAX_IMAGEM_BYTES:
        raise HTTPException(status_code=413, detail="Imagem grande demais (limite de 15 MB)")
    dados = await request.body()
    sv.settings.temp_dir.mkdir(parents=True, exist_ok=True)
    temporario = sv.settings.temp_dir / f"envio-{uuid.uuid4().hex}.png"
    nome_do_arquivo = nome_de_arquivo_seguro(file_name, padrao="personagem.png")

    def gravar() -> tuple[int, int]:
        return sanitizar_imagem(dados, nome_do_arquivo, temporario)

    try:
        largura, altura = await run_in_threadpool(gravar)
    except UploadInvalido as exc:
        temporario.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Imagem recusada: {exc}.") from exc
    try:
        personagem = sv.personagens.criar(
            ficha.name,
            style,
            ficha.model_dump(),
            prompt_tecnico="",
            voz=voz_sugerida(ficha),
            origem="upload",
        )
    except NomeEmUso as exc:
        temporario.unlink(missing_ok=True)
        return _conflito(sv, str(exc), ficha.name, style)
    midia = adotar_e_avisar(
        sv,
        temporario,
        tipo="imagem",
        papel="upload",
        extensao="png",
        largura=largura,
        altura=altura,
        dono_tipo="personagem",
        dono_id=personagem.id,
        estilo=style,
        metadados={"original_name": nome_do_arquivo, "rights_confirmed": True, "character_version": personagem.versao},
    )
    sv.personagens.definir_imagem_principal(personagem.id, midia.id)
    sv.personagens.definir_estado(personagem.id, "escolhido")
    job = None
    if sv.motores.motivo("cutout") is None:
        parametros = ParametrosDeRecorte(character_id=personagem.id, media_id=midia.id, slot="principal")
        job = enfileirar(
            sv,
            "personagem.recortar",
            parametros.model_dump(mode="json"),
            titulo=f"Recortar o fundo de {personagem.nome}",
        )
    atual = sv.personagens.obter(personagem.id)
    assert atual is not None
    return _com_job(sv, atual, job)


@router.get("/{id_}")
def detalhes(id_: IdPersonagem, sv: ServicosDep) -> dict[str, Any]:
    return fluxos.detalhes(sv, _achar(sv, id_))


@router.patch("/{id_}")
def editar(id_: IdPersonagem, pedido: PedidoDeEdicao, sv: ServicosDep) -> Any:
    personagem = _achar(sv, id_)
    if pedido.form is not None:
        ficha = pedido.form.model_copy(update={"name": pedido.form.name.strip()})
        if ficha.style != personagem.estilo:
            raise HTTPException(
                status_code=422,
                detail=f"Para mudar o estilo, use «Criar versão {'3D' if personagem.estilo == '2D' else '2D'}»: "
                "as imagens de um personagem seguem o estilo dele.",
            )
        _conferir_ficha(ficha)
        tecnico = pedido.technical_prompt if pedido.technical_prompt is not None else prompt_personagem(ficha)
        if reprovacao := verificar_texto(tecnico):
            raise HTTPException(status_code=422, detail=reprovacao.motivo)
        try:
            novo = sv.personagens.atualizar_ficha(id_, ficha.model_dump(), nome=ficha.name, prompt_tecnico=tecnico)
        except NomeEmUso as exc:
            return _conflito(sv, str(exc), ficha.name, personagem.estilo)
        assert novo is not None
        return fluxos.resumo(sv, novo)
    if pedido.technical_prompt is not None:
        if reprovacao := verificar_texto(pedido.technical_prompt):
            raise HTTPException(status_code=422, detail=reprovacao.motivo)
        sv.personagens.definir_prompt_tecnico(id_, pedido.technical_prompt.strip())
        return fluxos.resumo(sv, _achar(sv, id_))
    raise HTTPException(status_code=422, detail="Nada para alterar.")


@router.delete("/{id_}")
def apagar(id_: IdPersonagem, sv: ServicosDep) -> dict[str, Any]:
    personagem = _achar(sv, id_)
    removidas = sv.midias.remover_do_dono("personagem", personagem.id)
    sv.personagens.remover(personagem.id)
    return {"deleted": True, "media_removed": removidas}


@router.post("/{id_}/variations", response_model=Job, status_code=202)
def gerar_variacoes(id_: IdPersonagem, pedido: PedidoDeVariacoes, sv: ServicosDep) -> Job:
    personagem = _achar(sv, id_)
    _exigir(sv, "image")
    ficha = ficha_do_personagem(personagem)
    prompt = (pedido.technical_prompt or personagem.prompt_tecnico or prompt_personagem(ficha)).strip()
    if reprovacao := verificar_texto(prompt):
        raise HTTPException(status_code=422, detail=reprovacao.motivo)
    if pedido.technical_prompt is not None and prompt != personagem.prompt_tecnico:
        sv.personagens.definir_prompt_tecnico(personagem.id, prompt)
    parametros = ParametrosDeVariacoes(
        character_id=personagem.id,
        count=pedido.count,
        quality=pedido.quality,
        seed=pedido.seed,
        technical_prompt=prompt,
    )
    return enfileirar(
        sv,
        "personagem.variacoes",
        parametros.model_dump(mode="json"),
        titulo=f"Variações de {personagem.nome} ({pedido.count})",
    )


@router.post("/{id_}/choose")
def escolher(id_: IdPersonagem, pedido: PedidoDeEscolha, sv: ServicosDep) -> dict[str, Any]:
    personagem = _achar(sv, id_)
    midia = sv.midias.obter(pedido.media_id)
    if (
        midia is None
        or midia.dono_id != personagem.id
        or midia.tipo != "imagem"
        or midia.papel not in ("variacao", "upload")
    ):
        raise HTTPException(status_code=422, detail="Escolha uma das variações ou a imagem enviada deste personagem.")
    sv.personagens.definir_imagem_principal(personagem.id, midia.id)
    sv.personagens.definir_estado(personagem.id, "escolhido")
    job = None
    ja_recortada = bool(sv.midias.listar(papeis=("recorte",), pai_id=midia.id, limite=1))
    if not ja_recortada and sv.motores.motivo("cutout") is None:
        parametros = ParametrosDeRecorte(character_id=personagem.id, media_id=midia.id, slot="principal")
        job = enfileirar(
            sv,
            "personagem.recortar",
            parametros.model_dump(mode="json"),
            titulo=f"Recortar o fundo de {personagem.nome}",
        )
    atual = sv.personagens.obter(personagem.id)
    assert atual is not None
    return _com_job(sv, atual, job)


@router.post("/{id_}/sheet", response_model=Job, status_code=202)
def gerar_folha(id_: IdPersonagem, pedido: PedidoDeFolha, sv: ServicosDep) -> Job:
    personagem = _achar(sv, id_)
    if not personagem.imagem_principal_id:
        raise HTTPException(status_code=422, detail="Escolha uma das variações antes de gerar a folha de referência.")
    _exigir(sv, "image", "cutout")
    parametros = ParametrosDeFolha(
        character_id=personagem.id, slots=pedido.slots, quality=pedido.quality, seed=pedido.seed
    )
    return enfileirar(
        sv,
        "personagem.folha",
        parametros.model_dump(mode="json"),
        titulo=f"Folha de referência de {personagem.nome} ({len(pedido.slots)})",
    )


@router.put("/{id_}/voice")
def definir_voz(id_: IdPersonagem, pedido: PedidoDeVoz, sv: ServicosDep) -> dict[str, Any]:
    personagem = _achar(sv, id_)
    try:
        voz = voz_valida(pedido.para_dict())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    sv.personagens.definir_voz(personagem.id, voz)
    return fluxos.resumo(sv, _achar(sv, id_))


class PedidoDeDirecao(BaseModel):
    facing: Literal["front", "left", "right"]


@router.put("/{id_}/cutouts/{media_id}/facing")
def definir_direcao_do_recorte(
    id_: IdPersonagem,
    media_id: Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")],
    pedido: PedidoDeDirecao,
    sv: ServicosDep,
) -> dict[str, Any]:
    """Para onde o recorte olha (de frente, esquerda ou direita). A animação usa isso para virar o personagem para o centro."""
    personagem = _achar(sv, id_)
    recorte = sv.midias.obter(media_id)
    if recorte is None or recorte.dono_id != personagem.id or recorte.papel != "recorte":
        raise HTTPException(status_code=404, detail="Recorte não encontrado neste personagem")
    sv.midias.atualizar_metadados(recorte.id, facing=pedido.facing)
    atualizado = sv.midias.obter(recorte.id)
    assert atualizado is not None
    return atualizado.para_api()


@router.post("/{id_}/voice-test", response_model=Job, status_code=202)
def testar_voz(id_: IdPersonagem, pedido: PedidoDeVozDeTeste, sv: ServicosDep) -> Job:
    personagem = _achar(sv, id_)
    _exigir(sv, "voice", "ffmpeg")
    if reprovacao := verificar_texto(pedido.text):
        raise HTTPException(status_code=422, detail=reprovacao.motivo)
    voz = None
    if pedido.voice is not None:
        try:
            voz = voz_valida(pedido.voice.para_dict())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    parametros = ParametrosDeVozDeTeste(character_id=personagem.id, text=pedido.text.strip(), voice=voz)
    return enfileirar(
        sv, "personagem.voz_teste", parametros.model_dump(mode="json"), titulo=f"Voz de {personagem.nome}"
    )


@router.post("/{id_}/convert", status_code=201)
def converter(id_: IdPersonagem, pedido: PedidoDeConversao, sv: ServicosDep) -> Any:
    """Cria a versão do mesmo personagem no outro estilo (2D↔3D), partindo da imagem principal como referência."""
    personagem = _achar(sv, id_)
    if not personagem.imagem_principal_id:
        raise HTTPException(status_code=422, detail="Escolha uma das variações antes de criar a outra versão.")
    _exigir(sv, "image")
    novo_estilo: Literal["2D", "3D"] = "3D" if personagem.estilo == "2D" else "2D"
    ficha = ficha_do_personagem(personagem).model_copy(update={"style": novo_estilo})
    prompt = prompt_outro_estilo(ficha, novo_estilo)
    try:
        novo = sv.personagens.criar(
            personagem.nome,
            novo_estilo,
            ficha.model_dump(),
            prompt_original=personagem.prompt_original,
            prompt_tecnico=prompt,
            voz=personagem.voz,
            origem="conversao",
            origem_id=personagem.id,
        )
    except NomeEmUso:
        return _conflito(sv, f"«{personagem.nome}» já existe em {novo_estilo}.", personagem.nome, novo_estilo)
    parametros = ParametrosDeVariacoes(
        character_id=novo.id,
        count=pedido.count,
        quality=pedido.quality,
        technical_prompt=prompt,
        reference_media_id=personagem.imagem_principal_id,
    )
    job = enfileirar(
        sv,
        "personagem.variacoes",
        parametros.model_dump(mode="json"),
        titulo=f"Versão {novo_estilo} de {personagem.nome}",
    )
    return _com_job(sv, novo, job)
