"""Fixtures compartilhadas: configuração em pasta temporária, Ollama falso e clientes da API."""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi.testclient import TestClient

from app.benchmark.medidores import Faixa
from app.benchmark.resultado import ResultadoBench
from app.config import Settings, carregar_configuracao
from app.container import Servicos, criar_servicos
from app.ferramentas.catalogo import ITENS
from app.main import criar_app
from app.motores.ffmpeg import Ffmpeg
from app.services.ollama import OllamaClient

from .builders import FIXTURES
from .fakes_motores import motores_falsos

if TYPE_CHECKING:
    from app.jobs.worker import JobContext

RAIZ = Path(__file__).resolve().parents[2]


def esperar(condicao: Callable[[], bool], timeout: float = 90.0, passo: float = 0.02) -> bool:
    """Espera (com tempo limite) por uma condição que outra thread vai tornar verdadeira.

    O limite é largo de propósito: retorna assim que a condição vale, então só pesa quando algo está errado, e no notebook
    carregado (agentes de inventário e antivírus do Windows) um job de 1 s chegou a levar 18 s e derrubou um teste de 15 s.
    """
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if condicao():
            return True
        time.sleep(passo)
    return condicao()


def ollama_falso(
    modelos: list[tuple[str, int]] | None = None, *, online: bool = True, gpu: bool = False
) -> tuple[OllamaClient, list[str]]:
    """Cliente real do Ollama sobre um transporte falso; devolve também a lista de chamadas feitas."""
    catalogo = [("qwen3:4b", 2_500_000_000)] if modelos is None else modelos
    chamadas: list[str] = []

    def tratar(req: httpx.Request) -> httpx.Response:
        chamadas.append(f"{req.method} {req.url.path}")
        if not online:
            raise httpx.ConnectError("conexão recusada", request=req)
        caminho = req.url.path
        if caminho == "/api/version":
            return httpx.Response(200, json={"version": "0.33.3"})
        if caminho == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": n, "size": s} for n, s in catalogo]})
        if caminho == "/api/ps":
            carregados = [{"name": catalogo[0][0], "size_vram": 2_000_000_000 if gpu else 0}] if catalogo else []
            return httpx.Response(200, json={"models": carregados})
        if caminho == "/api/generate":
            corpo = json.loads(req.content)
            if corpo.get("keep_alive") == 0:
                return httpx.Response(200, json={})
            n = corpo["options"]["num_predict"]
            return httpx.Response(
                200,
                json={
                    "response": "{}",
                    "eval_count": n,
                    "eval_duration": int(n / 10.0 * 1e9),  # 10 tok/s
                    "prompt_eval_count": 1046 if n < 50 else 60,
                    "prompt_eval_duration": int((1046 if n < 50 else 60) / 40.0 * 1e9),  # 40 tok/s
                },
            )
        return httpx.Response(404)

    cliente = OllamaClient("http://127.0.0.1:11434", transport=httpx.MockTransport(tratar))
    return cliente, chamadas


class MedidoresFalsos:
    """Medidores que não rodam motor nenhum (os testes normais não gastam minutos gerando imagem de verdade)."""

    def __init__(self) -> None:
        self.chamadas: list[str] = []

    def voz(self, ctx: JobContext, faixa: Faixa) -> ResultadoBench:
        self.chamadas.append("voz")
        return ResultadoBench(
            "tts", "ok", "Kokoro 82M", 8.0, {"rtf": 0.5, "audio_s": 5.0, "synth_s": 2.5}, "Falou 5 s de áudio em 2,5 s."
        )

    def recorte(self, ctx: JobContext, faixa: Faixa) -> ResultadoBench:
        self.chamadas.append("recorte")
        return ResultadoBench(
            "cutout", "ok", "BiRefNet lite", 30.0, {"infer_s": 12.0, "size": 1024}, "≈ 12 s por imagem."
        )

    def imagem(self, ctx: JobContext, faixa: Faixa) -> ResultadoBench:
        self.chamadas.append("imagem")
        metricas = {"wall_s": 100.0, "size": 512, "steps": 4, "backend": "vulkan"}
        return ResultadoBench("image", "ok", "FLUX.2 klein 4B (Q4_0)", 100.0, metricas, "≈ 1,7 min por imagem.")


def instalar_falso(settings: Settings, ids: list[str] | None = None) -> None:
    """Cria os arquivos-marcador do catálogo (vazios) para simular ferramentas e modelos instalados."""
    for item in ITENS:
        if ids is not None and item.id not in ids:
            continue
        base = settings.tools_dir if item.base == "tools" else settings.models_dir
        marcador = base / item.marcador
        marcador.parent.mkdir(parents=True, exist_ok=True)
        marcador.write_bytes(b"x")


@pytest.fixture(autouse=True)
def _bibliotecas_de_ia_presentes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Os testes não dependem das bibliotecas de IA do .venv: por padrão elas "existem" (um teste pode desfazer isso)."""
    monkeypatch.setattr("app.ferramentas.detectar.tem_modulo", lambda nome: True)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    hardware = tmp_path / "config" / "hardware.json"
    hardware.parent.mkdir(parents=True)
    shutil.copy(FIXTURES / "thinkpad_t14_gen2i.json", hardware)
    env = {
        "FABULIM_DATA_DIR": str(tmp_path / "data"),
        "FABULIM_MODELS_DIR": str(tmp_path / "models"),
        "FABULIM_TOOLS_DIR": str(tmp_path / "tools"),
        "FABULIM_HARDWARE_JSON": str(hardware),
        "FABULIM_FRONTEND_DIST": str(tmp_path / "dist"),
        "FABULIM_AUTO_DIAGNOSTICO": "0",
    }
    config = carregar_configuracao(env, root=RAIZ)
    instalar_falso(config)  # o padrão é "tudo instalado"; testes de ausência apagam ou usam `ids`
    return config


@pytest.fixture
def servicos(settings: Settings) -> Iterator[Servicos]:
    cliente, _ = ollama_falso()
    sv = criar_servicos(settings, ollama=cliente, medidores=MedidoresFalsos(), motores=motores_falsos())
    yield sv
    if sv.worker is not None:
        sv.worker.parar()


@pytest.fixture
def client(servicos: Servicos) -> Iterator[TestClient]:
    """API sem worker (os jobs ficam na fila), no endereço permitido pelo TrustedHost."""
    app = criar_app(servicos.settings, servicos=servicos, iniciar_worker=False)
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


@pytest.fixture
def client_com_worker(servicos: Servicos) -> Iterator[TestClient]:
    app = criar_app(servicos.settings, servicos=servicos, iniciar_worker=True)
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


@pytest.fixture(scope="session")
def ffmpeg_real() -> Ffmpeg:
    """O ffmpeg de verdade (o instalado em tools/ ou o do sistema); os testes que dependem dele pulam se não houver."""
    ffmpeg = Ffmpeg(carregar_configuracao({}, root=RAIZ))
    if ffmpeg.indisponivel():
        pytest.skip("ffmpeg não instalado neste computador")
    return ffmpeg


@pytest.fixture
def resolucoes_pequenas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Os quadros são desenhados de verdade, então nos testes as resoluções viram miniaturas (a lógica é a mesma)."""
    from app.projetos.pipeline import RESOLUCOES

    pequenas = {chave: ((160, 90) if chave[0] == "16:9" else (90, 160)) for chave in RESOLUCOES}
    pequenas.update({("1:1", "rascunho"): (96, 96), ("1:1", "final"): (96, 96)})
    monkeypatch.setattr("app.projetos.pipeline.RESOLUCOES", pequenas)
