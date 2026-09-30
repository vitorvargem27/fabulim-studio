"""Biblioteca de mídias: listar, servir (imagem, vídeo, áudio), miniaturas, enviar imagem e apagar.

Só vale o que está na biblioteca: a rota nunca recebe um caminho, só o id da mídia. O arquivo é servido de dentro da pasta
de mídias (o caminho gravado no banco é conferido de novo a cada leitura) e a interface nunca vê o caminho no disco.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from ..midias.repositorio import Midia
from ..midias.servico import adotar_e_avisar, remover_e_avisar
from ..security.caminhos import CaminhoInseguro, nome_de_arquivo_seguro
from ..security.uploads import MAX_IMAGEM_BYTES, UploadInvalido, sanitizar_imagem
from .deps import ServicosDep

router = APIRouter(prefix="/api/media")

IdMidia = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]
IMUTAVEL = {"Cache-Control": "private, max-age=31536000, immutable"}  # cada mídia tem id próprio e nunca é sobrescrita
MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "mp4": "video/mp4",
    "webm": "video/webm",
    "mov": "video/quicktime",
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "srt": "text/plain; charset=utf-8",
    "json": "application/json",
}
PAPEIS_QUE_O_DONO_CUIDA = ("projeto", "cena")


def _achar(sv: ServicosDep, id_: str) -> Midia:
    midia = sv.midias.obter(id_)
    if midia is None:
        raise HTTPException(status_code=404, detail="Mídia não encontrada")
    return midia


def _arquivo(sv: ServicosDep, midia: Midia, *, miniatura: bool, baixar: bool, nome: str | None) -> FileResponse:
    try:
        caminho = sv.midias.caminho_da_miniatura(midia) if miniatura else sv.midias.caminho_absoluto(midia)
    except CaminhoInseguro:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado") from None
    if caminho is None or not caminho.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    extensao = "webp" if miniatura else (midia.formato or caminho.suffix.lstrip(".")).lower()
    tipo = MIME.get(extensao, "application/octet-stream")
    if baixar or tipo == "application/octet-stream":
        sugerido = nome_de_arquivo_seguro(nome or f"fabulim-{midia.id[:8]}.{extensao}", padrao=f"fabulim.{extensao}")
        return FileResponse(caminho, media_type=tipo, filename=sugerido, headers=IMUTAVEL)
    return FileResponse(caminho, media_type=tipo, content_disposition_type="inline", headers=IMUTAVEL)


@router.get("")
def listar(
    sv: ServicosDep,
    kind: Annotated[Literal["imagem", "video", "audio", "legenda"] | None, Query()] = None,
    role: Annotated[list[str] | None, Query(max_length=12)] = None,
    owner_type: Annotated[str | None, Query(pattern=r"^[a-z_]{1,20}$", description="«nenhum»: só as avulsas")] = None,
    owner_id: Annotated[str | None, Query(pattern=r"^[0-9a-f]{32}$")] = None,
    parent_id: Annotated[str | None, Query(pattern=r"^[0-9a-f]{32}$")] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    papeis = tuple(r for r in (role or []) if r.replace("_", "").isalnum() and len(r) <= 30)
    filtros: dict[str, Any] = {
        "tipo": kind,
        "papeis": papeis,
        "dono_tipo": owner_type,
        "dono_id": owner_id,
        "pai_id": parent_id,
        "busca": q,
    }
    itens = sv.midias.listar(**filtros, limite=limit, deslocamento=offset)
    return {"items": [m.para_api() for m in itens], "total": sv.midias.contar(**filtros)}


@router.post("/upload", status_code=201)
async def enviar_imagem(
    request: Request,
    sv: ServicosDep,
    name: Annotated[str, Query(min_length=1, max_length=120)],
    role: Annotated[str, Query(pattern=r"^[a-z_]{1,30}$")] = "upload",
) -> dict[str, Any]:
    """Recebe uma imagem (corpo cru). Confere o tipo real, decodifica de verdade e guarda um PNG sem metadados."""
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > MAX_IMAGEM_BYTES:
        raise HTTPException(status_code=413, detail="Imagem grande demais (limite de 15 MB)")
    dados = await request.body()
    nome = nome_de_arquivo_seguro(name, padrao="imagem.png")
    sv.settings.temp_dir.mkdir(parents=True, exist_ok=True)
    temporario = sv.settings.temp_dir / f"envio-{uuid.uuid4().hex}.png"

    def gravar() -> tuple[int, int]:
        return sanitizar_imagem(dados, nome, temporario)

    try:
        largura, altura = await run_in_threadpool(gravar)
    except UploadInvalido as exc:
        temporario.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Imagem recusada: {exc}.") from exc
    midia = adotar_e_avisar(
        sv,
        temporario,
        tipo="imagem",
        papel=role,
        extensao="png",
        largura=largura,
        altura=altura,
        metadados={"original_name": nome},
    )
    return midia.para_api()


@router.get("/{id_}/info")
def informacoes(id_: IdMidia, sv: ServicosDep) -> dict[str, Any]:
    return _achar(sv, id_).para_api()


@router.get("/{id_}/thumb")
def miniatura(id_: IdMidia, sv: ServicosDep) -> FileResponse:
    return _arquivo(sv, _achar(sv, id_), miniatura=True, baixar=False, nome=None)


@router.get("/{id_}")
def arquivo(
    id_: IdMidia,
    sv: ServicosDep,
    download: bool = False,
    name: Annotated[str | None, Query(max_length=120)] = None,
) -> FileResponse:
    return _arquivo(sv, _achar(sv, id_), miniatura=False, baixar=download, nome=name)


@router.delete("/{id_}")
def apagar(id_: IdMidia, sv: ServicosDep) -> dict[str, bool]:
    midia = _achar(sv, id_)
    if midia.dono_tipo in PAPEIS_QUE_O_DONO_CUIDA:
        raise HTTPException(status_code=409, detail="Esta mídia faz parte de um projeto: apague pelo projeto.")
    for personagem in sv.personagens.listar(limite=1000):
        if personagem.imagem_principal_id == midia.id:
            raise HTTPException(status_code=409, detail="Esta é a imagem principal de um personagem.")
    return {"deleted": remover_e_avisar(sv, id_)}
