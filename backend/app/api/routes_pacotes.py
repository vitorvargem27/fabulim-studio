"""Pacotes .fabulim: exportar um projeto ou os personagens e importar um pacote (briefing, seção 2.7)."""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ..projetos import pacote, servico
from ..security.caminhos import nome_de_arquivo_seguro
from .deps import ServicosDep

router = APIRouter(prefix="/api/packages")

IdProjeto = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]
ID = r"^[0-9a-f]{32}$"


def _lesma(texto: str, padrao: str) -> str:
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")[:60] or padrao


def _resposta_do_arquivo(destino: Any, nome: str) -> FileResponse:
    return FileResponse(
        destino,
        media_type="application/octet-stream",
        filename=nome_de_arquivo_seguro(nome, padrao="pacote.fabulim"),
        background=BackgroundTask(destino.unlink, missing_ok=True),  # o arquivo temporário some depois de enviado
    )


@router.get("/projects/{id_}")
async def exportar_projeto(
    id_: IdProjeto,
    sv: ServicosDep,
    renders: Annotated[bool, Query(description="levar também clipes, áudio, vídeo final e miniaturas")] = False,
) -> FileResponse:
    """Baixa o projeto como pacote .fabulim (enredo, roteiro, versões, aprovações, personagens e cenários)."""
    projeto = sv.projetos.obter(id_)
    if projeto is None:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    sv.settings.temp_dir.mkdir(parents=True, exist_ok=True)
    destino = sv.settings.temp_dir / f"exportar-{uuid.uuid4().hex}{pacote.EXTENSAO}"
    try:
        await run_in_threadpool(pacote.exportar_projeto, sv, projeto, destino, renders=renders)
    except BaseException:
        destino.unlink(missing_ok=True)
        raise
    return _resposta_do_arquivo(destino, f"{_lesma(projeto.titulo, 'projeto')}{pacote.EXTENSAO}")


@router.get("/characters")
async def exportar_personagens(
    sv: ServicosDep,
    id: Annotated[
        list[str] | None, Query(max_length=200, description="só estes; sem ids leva a biblioteca inteira")
    ] = None,
) -> FileResponse:
    """Baixa os personagens (todos ou os escolhidos) como pacote .fabulim, com todas as imagens e recortes."""
    if id:
        invalidos = [i for i in id if not re.fullmatch(ID, i)]
        if invalidos:
            raise HTTPException(status_code=422, detail="Um dos ids de personagem é inválido.")
        personagens = [p for i in dict.fromkeys(id) if (p := sv.personagens.obter(i)) is not None]
    else:
        personagens = sv.personagens.listar(limite=1000)
    if not personagens:
        raise HTTPException(status_code=404, detail="Não há personagens para exportar.")
    sv.settings.temp_dir.mkdir(parents=True, exist_ok=True)
    destino = sv.settings.temp_dir / f"exportar-{uuid.uuid4().hex}{pacote.EXTENSAO}"
    try:
        await run_in_threadpool(pacote.exportar_personagens, sv, personagens, destino)
    except BaseException:
        destino.unlink(missing_ok=True)
        raise
    nome = _lesma(personagens[0].nome, "personagens") if len(personagens) == 1 else "personagens"
    return _resposta_do_arquivo(destino, f"{nome}{pacote.EXTENSAO}")


@router.post("/import", status_code=201)
async def importar(request: Request, sv: ServicosDep) -> dict[str, Any]:
    """Recebe um pacote .fabulim (corpo cru), confere tudo e importa. Nada que já existe é sobrescrito."""
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > pacote.LIMITE_TOTAL:
        raise HTTPException(status_code=413, detail="Pacote grande demais (limite de 4 GB).")
    sv.settings.temp_dir.mkdir(parents=True, exist_ok=True)
    temporario = sv.settings.temp_dir / f"importar-{uuid.uuid4().hex}.zip"
    total = 0
    try:
        with temporario.open("wb") as arquivo:
            async for pedaco in request.stream():
                total += len(pedaco)
                if total > pacote.LIMITE_TOTAL:
                    raise HTTPException(status_code=413, detail="Pacote grande demais (limite de 4 GB).")
                arquivo.write(pedaco)
        if total == 0:
            raise HTTPException(status_code=422, detail="Arquivo vazio.")
        try:
            relatorio = await run_in_threadpool(pacote.importar_pacote, sv, temporario)
        except pacote.PacoteInvalido as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        temporario.unlink(missing_ok=True)
    resposta = relatorio.para_api()
    projeto = sv.projetos.obter(relatorio.projeto_id) if relatorio.projeto_id else None
    resposta["project"] = servico.resumo(sv, projeto) if projeto else None
    resposta["character_list"] = pacote.resumo_dos_personagens(sv, [str(p["id"]) for p in relatorio.personagens])
    return resposta
