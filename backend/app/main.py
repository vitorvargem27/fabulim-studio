"""Aplicação FastAPI do Fabulim Studio (só 127.0.0.1)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .api import (
    routes_clipes,
    routes_ferramentas,
    routes_imagens,
    routes_jobs,
    routes_media,
    routes_pacotes,
    routes_personagens,
    routes_projetos,
    routes_prompts,
    routes_system,
)
from .config import NOME_APP, VERSAO, Settings, carregar_configuracao
from .container import Servicos, criar_servicos
from .erros import ErroParaOUsuario
from .jobs.servico import enfileirar, job_ativo_do_tipo
from .logging_setup import configurar_logging, logger_do_servico

CABECALHOS_SEGURANCA = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: blob:; media-src 'self'; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    ),
}


class CabecalhosSeguranca:
    """Middleware ASGI puro (não bufferiza o stream SSE, ao contrário do BaseHTTPMiddleware)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def enviar(mensagem: Message) -> None:
            if mensagem["type"] == "http.response.start":
                cabecalhos = MutableHeaders(scope=mensagem)
                for chave, valor in CABECALHOS_SEGURANCA.items():
                    cabecalhos.setdefault(chave, valor)
            await send(mensagem)

        await self.app(scope, receive, enviar)


class ProtecaoDeOrigem:
    """Contra CSRF: o CORS só impede *ler* a resposta; um site qualquer ainda poderia *disparar* um POST simples para
    127.0.0.1. Requisições que alteram estado só passam se a origem for a do próprio app (ou não vierem de navegador)."""

    METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS"})

    def __init__(self, app: ASGIApp, origens_permitidas: tuple[str, ...]) -> None:
        self.app = app
        self.origens = frozenset(origens_permitidas)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in self.METODOS_SEGUROS:
            cabecalhos = Headers(scope=scope)
            origem = cabecalhos.get("origin")
            if (origem is not None and origem not in self.origens) or cabecalhos.get("sec-fetch-site") == "cross-site":
                resposta = JSONResponse({"detail": "Origem não permitida"}, status_code=403)
                await resposta(scope, receive, send)
                return
        await self.app(scope, receive, send)


class SpaStaticFiles(StaticFiles):
    """Serve o build do Angular; rotas do app (ex.: /status) caem no index.html. /api nunca cai."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        # No Windows o Starlette entrega o caminho com barra invertida (api\nao-existe): normaliza antes de comparar.
        eh_api = path.replace("\\", "/").split("/", 1)[0] == "api"
        try:
            resposta = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or eh_api:
                raise
            return await super().get_response("index.html", scope)
        if resposta.status_code == 404 and not eh_api:
            return await super().get_response("index.html", scope)
        return resposta


def criar_app(
    settings: Settings | None = None, *, servicos: Servicos | None = None, iniciar_worker: bool = True
) -> FastAPI:
    config = settings or (servicos.settings if servicos else carregar_configuracao())

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
        configurar_logging(config.log_dir)
        log = logger_do_servico("app")
        sv = servicos or criar_servicos(config)
        app.state.servicos = sv
        retomados = sv.store.recuperar_interrompidos()
        if retomados:
            log.info("%d job(s) interrompido(s) voltaram para a fila", retomados)
        if iniciar_worker and sv.worker is not None:
            sv.worker.iniciar()
        sv.hardware.salvar_capacidades()
        if config.auto_diagnostico and job_ativo_do_tipo(sv, "system.diagnostico") is None:
            leve = sv.hardware.carregar() is not None  # sem coleta anterior, faz a completa
            enfileirar(
                sv,
                "system.diagnostico",
                {"leve": leve},
                titulo="Diagnóstico da máquina (leve)" if leve else "Diagnóstico da máquina",
            )
        log.info("%s %s pronto em http://%s:%d", NOME_APP, VERSAO, config.host, config.port)
        try:
            yield
        finally:
            if sv.worker is not None:
                sv.worker.parar()
            sv.ollama.fechar()
            log.info("servidor encerrado")

    app = FastAPI(
        title=NOME_APP,
        version=VERSAO,
        lifespan=ciclo_de_vida,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    @app.exception_handler(ErroParaOUsuario)
    async def erro_para_o_usuario(request: Request, exc: ErroParaOUsuario) -> JSONResponse:
        """A mensagem já é em português e diz o que fazer: 409 (o pedido é válido, mas o estado atual não deixa)."""
        return JSONResponse({"detail": str(exc)}, status_code=409)

    app.add_middleware(CabecalhosSeguranca)
    app.add_middleware(ProtecaoDeOrigem, origens_permitidas=config.cors_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(config.allowed_hosts))
    app.include_router(routes_system.router)
    app.include_router(routes_jobs.router)
    app.include_router(routes_ferramentas.router)
    app.include_router(routes_media.router)
    app.include_router(routes_prompts.router)
    app.include_router(routes_imagens.router)
    app.include_router(routes_personagens.router)
    app.include_router(routes_projetos.router)
    app.include_router(routes_clipes.router)
    app.include_router(routes_pacotes.router)
    if (config.frontend_dist / "index.html").is_file():
        app.mount("/", SpaStaticFiles(directory=config.frontend_dist, html=True), name="frontend")
    return app
