"""Biblioteca de clipes: clipe rápido, enviar vídeo, unir, gerar em outra resolução e continuar a partir de um vídeo."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.concurrency import run_in_threadpool

from ..clipes import servico
from ..clipes.pedidos import (
    ParametrosDeReenquadramento,
    PedidoDeContinuacao,
    PedidoDeReenquadramento,
    PedidoDeUniao,
    PedidoDoClipeRapido,
)
from ..conteudo.filtro import verificar_campos, verificar_texto
from ..erros import ErroParaOUsuario
from ..jobs.models import Job
from ..jobs.servico import enfileirar
from ..midias.repositorio import Midia
from ..midias.servico import adotar_e_avisar, remover_e_avisar
from ..personagens import fluxos
from ..projetos.roteiro import achar_personagem
from ..security.caminhos import nome_de_arquivo_seguro
from .deps import ServicosDep

router = APIRouter(prefix="/api/clips")

IdClipe = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


def _clipe(sv: ServicosDep, id_: str) -> Midia:
    midia = sv.midias.obter(id_)
    if midia is None or midia.tipo != "video" or midia.papel not in servico.PAPEIS_DA_BIBLIOTECA:
        raise HTTPException(status_code=404, detail="Clipe não encontrado")
    return midia


def _exigir(sv: ServicosDep, *motores: str) -> None:
    if motivo := sv.motores.motivo(*motores):
        raise HTTPException(status_code=503, detail=motivo)


def _com_origem(sv: ServicosDep, midia: Midia) -> dict[str, Any]:
    api = midia.para_api()
    origem = sv.projetos.obter(str(midia.metadados.get("project_id"))) if midia.metadados.get("project_id") else None
    api["project_title"] = origem.titulo if origem else None
    api["variants"] = [m.id for m in sv.midias.listar(tipo="video", pai_id=midia.id, limite=50)]
    return api


@router.get("")
def listar(
    sv: ServicosDep,
    role: Annotated[list[str] | None, Query(max_length=6)] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    papeis = tuple(r for r in (role or list(servico.PAPEIS_DA_BIBLIOTECA)) if r in servico.PAPEIS_DA_BIBLIOTECA)
    if role and not papeis:
        return {"items": [], "total": 0}  # só pediu papéis que não são da biblioteca de clipes
    filtros: dict[str, Any] = {"tipo": "video", "papeis": papeis, "busca": q}
    itens = sv.midias.listar(**filtros, limite=limit, deslocamento=offset)
    return {"items": [_com_origem(sv, m) for m in itens], "total": sv.midias.contar(**filtros)}


@router.post("/quick", response_model=Job, status_code=202)
def clipe_rapido(pedido: PedidoDoClipeRapido, sv: ServicosDep) -> Job:
    """Um personagem + uma frase de ação viram um clipe (cenário gerado por IA, personagem animado por código)."""
    personagem = sv.personagens.obter(pedido.character_id)
    if personagem is None:
        raise HTTPException(status_code=404, detail="Personagem não encontrado")
    if not fluxos.recortes_por_slot(sv, personagem.id):
        raise HTTPException(
            status_code=409,
            detail=f"«{personagem.nome}» ainda não tem o PNG transparente. Escolha uma variação na página Personagens.",
        )
    if reprovacao := verificar_texto(pedido.prompt):
        raise HTTPException(status_code=422, detail=reprovacao.motivo)
    _exigir(sv, "image", "ffmpeg")
    return enfileirar(sv, "clipe.rapido", pedido.model_dump(mode="json"), titulo=f"Clipe rápido de {personagem.nome}")


@router.post("/upload", status_code=201)
async def enviar_clipe(
    request: Request,
    sv: ServicosDep,
    name: Annotated[str, Query(min_length=1, max_length=120)],
    rights: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    """Recebe um vídeo (corpo cru): confere com o ffprobe que é um vídeo de verdade e guarda na biblioteca."""
    if not rights:
        raise HTTPException(status_code=422, detail="Confirme que você tem o direito de usar este vídeo.")
    _exigir(sv, "ffmpeg")
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > servico.MAXIMO_DE_BYTES:
        raise HTTPException(status_code=413, detail="Vídeo grande demais (limite de 1 GB)")
    sv.settings.temp_dir.mkdir(parents=True, exist_ok=True)
    temporario = sv.settings.temp_dir / f"envio-{uuid.uuid4().hex}.bin"
    total = 0
    try:
        with temporario.open("wb") as arquivo:
            async for pedaco in request.stream():
                total += len(pedaco)
                if total > servico.MAXIMO_DE_BYTES:
                    raise HTTPException(status_code=413, detail="Vídeo grande demais (limite de 1 GB)")
                arquivo.write(pedaco)
        if total == 0:
            raise HTTPException(status_code=422, detail="Arquivo vazio.")
        try:
            sonda, extensao = await run_in_threadpool(servico.validar_video_enviado, sv, temporario)
        except ErroParaOUsuario as exc:
            raise HTTPException(status_code=422, detail=f"Vídeo recusado: {exc}") from exc
        capa = sv.settings.temp_dir / f"capa-{uuid.uuid4().hex}.jpg"
        await run_in_threadpool(servico.quadro_do_video, sv, temporario, capa, em_s=min(1.0, sonda.duracao_s / 2))
    except BaseException:
        temporario.unlink(missing_ok=True)
        raise
    nome = nome_de_arquivo_seguro(name, padrao="clipe.mp4")
    midia = adotar_e_avisar(
        sv,
        temporario,
        tipo="video",
        papel="clipe_enviado",
        extensao=extensao,
        largura=sonda.largura,
        altura=sonda.altura,
        duracao_s=sonda.duracao_s,
        miniatura_de=capa if capa.is_file() else None,
        metadados={
            "original_name": nome,
            "rights_confirmed": True,
            "fps": sonda.fps,
            "codec": sonda.codec_de_video,
            "has_audio": sonda.tem_audio,
        },
    )
    capa.unlink(missing_ok=True)
    return _com_origem(sv, midia)


@router.post("/join", response_model=Job, status_code=202)
def unir(pedido: PedidoDeUniao, sv: ServicosDep) -> Job:
    """Une os clipes, na ordem pedida, com a transição escolhida (formatos diferentes são ajustados e o volume normalizado)."""
    for id_ in pedido.clip_ids:
        _clipe(sv, id_)
    _exigir(sv, "ffmpeg")
    return enfileirar(sv, "clipe.unir", pedido.model_dump(mode="json"), titulo=f"Unir {len(pedido.clip_ids)} vídeos")


@router.get("/{id_}")
def detalhes(id_: IdClipe, sv: ServicosDep) -> dict[str, Any]:
    return _com_origem(sv, _clipe(sv, id_))


@router.delete("/{id_}")
def apagar(id_: IdClipe, sv: ServicosDep) -> dict[str, bool]:
    midia = _clipe(sv, id_)
    if midia.dono_tipo in ("projeto", "cena"):
        raise HTTPException(status_code=409, detail="Este vídeo faz parte de um projeto: apague pelo projeto.")
    return {"deleted": remover_e_avisar(sv, midia.id)}


@router.post("/{id_}/reframe", response_model=Job, status_code=202)
def reenquadrar(id_: IdClipe, pedido: PedidoDeReenquadramento, sv: ServicosDep) -> Job:
    """Gera o clipe em outro formato (9:16, 16:9, 1:1 ou 720p) sem cortar o que importa. O resultado fica ligado ao original."""
    _clipe(sv, id_)
    _exigir(sv, "ffmpeg")
    parametros = ParametrosDeReenquadramento(clip_id=id_, **pedido.model_dump())
    return enfileirar(sv, "clipe.reenquadrar", parametros.model_dump(mode="json"), titulo=f"Gerar em {pedido.preset}")


@router.post("/{id_}/continue", status_code=201)
def continuar(id_: IdClipe, pedido: PedidoDeContinuacao, sv: ServicosDep) -> dict[str, Any]:
    """Cria um projeto que continua o vídeo: começa igual ao último quadro e segue com o novo enredo (o roteiro vem depois)."""
    _exigir(sv, "ffmpeg")
    midia = _clipe(sv, id_)
    arquivo = sv.midias.caminho_absoluto(midia)
    sonda = sv.motores.ffmpeg.sondar(arquivo)
    if reprovacao := verificar_texto(pedido.prompt) or verificar_campos(
        {"last_scene": pedido.last_scene, "title": pedido.title}
    ):
        raise HTTPException(status_code=422, detail=reprovacao.motivo)
    sv.settings.temp_dir.mkdir(parents=True, exist_ok=True)
    ultimo = sv.settings.temp_dir / f"ultimo-{uuid.uuid4().hex}.jpg"
    if servico.quadro_do_video(sv, arquivo, ultimo, do_fim=True) is None:
        raise HTTPException(status_code=409, detail="Não consegui tirar o último quadro deste vídeo.")
    origem = servico._projeto_de_origem(sv, midia)
    formato = origem.formato if origem else servico.formato_pelo_video(sonda)
    idioma = origem.idioma if origem else "pt-BR"
    todos = sv.personagens.listar(limite=1000)
    ids = [p.id for p in (sv.personagens.obter(i) for i in pedido.character_ids) if p is not None]
    if len(ids) != len(set(pedido.character_ids)):
        raise HTTPException(status_code=422, detail="Um dos personagens escolhidos não existe mais na biblioteca.")
    ids += [i for i in (origem.personagens if origem else []) if i not in ids]
    if not ids and midia.metadados.get("character_id"):
        ids = [str(midia.metadados["character_id"])]
    estilo = origem.estilo if origem else "2D"
    if origem is None and ids and (primeiro := sv.personagens.obter(ids[0])) is not None:
        estilo = primeiro.estilo
    try:
        ficha = servico.ficha_da_continuacao(
            pedido.prompt,
            pedido.title or (f"Continuação de {origem.titulo}" if origem else "Continuação"),
            formato,
            idioma,
            estilo,
            [],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    for nome in ficha.characters:
        achado = achar_personagem(nome, todos)
        if achado and achado.id not in ids:
            ids.append(achado.id)
    if reprovacao := verificar_campos(ficha.model_dump()):
        raise HTTPException(status_code=422, detail=reprovacao.motivo)
    projeto = sv.projetos.criar(
        ficha.title.strip() or "Continuação",
        ficha.format,
        ficha.language,
        ficha.style,
        servico.duracao_padrao_da_continuacao(ficha.format),
        {**ficha.model_dump(), "original_prompt": pedido.prompt},
        ids,
        musica=dict(origem.musica) if origem else {},
        configuracoes={
            k: v
            for k, v in (origem.configuracoes if origem else {}).items()
            if k in ("fps", "transition", "narrator", "voices")
        },
    )
    quadro = adotar_e_avisar(
        sv,
        ultimo,
        tipo="imagem",
        papel="quadro_final",
        extensao="jpg",
        dono_tipo="projeto",
        dono_id=projeto.id,
        prompt="último quadro do vídeo original",
        metadados={"source_media_id": midia.id, "project_id": projeto.id},
    )
    ligacao = servico.preparar_ligacao(sv, midia, projeto, sv.midias.caminho_absoluto(quadro), pedido.last_scene)
    atualizado = sv.projetos.atualizar(
        projeto.id,
        configuracoes={
            **projeto.configuracoes,
            "continuation": {"source_media_id": midia.id, "junction": ligacao, "last_frame_media_id": quadro.id},
        },
    )
    assert atualizado is not None
    return {"project": atualizado.para_api(), "last_frame": quadro.para_api(), "source": _com_origem(sv, midia)}
