"""Os pedidos (API e jobs) das ferramentas de projeto. O job guarda exatamente estes campos e valida de novo ao rodar."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..imagens.servico import SEMENTE_MAXIMA
from ..prompts.formatos import FichaEnredo

ID = r"^[0-9a-f]{32}$"
QualidadeDoCenario = Literal["rascunho", "padrao", "alta"]
Transicao = Literal["corte", "fade", "suave"]
MAXIMO_DE_ESCOLHIDAS = 60


class PedidoDeProjeto(BaseModel):
    form: FichaEnredo
    original_prompt: str = Field(default="", max_length=30_000)
    character_ids: list[str] = Field(default_factory=list, max_length=8)
    target_duration_s: int | None = Field(default=None, ge=15, le=300)


class PedidoDeEdicaoDoProjeto(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    target_duration_s: int | None = Field(default=None, ge=15, le=300)
    character_ids: list[str] | None = Field(default=None, max_length=8)
    music: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None
    story: dict[str, Any] | None = None


class PedidoDoRoteiro(BaseModel):
    mode: Literal["ia", "simples"] = "ia"


class ParametrosDoRoteiro(PedidoDoRoteiro):
    project_id: str = Field(pattern=ID)


class PedidoDoStoryboard(BaseModel):
    scene_ids: list[str] | None = Field(default=None, max_length=MAXIMO_DE_ESCOLHIDAS)
    mode: Literal["faltantes", "regerar", "variacoes"] = "faltantes"
    variations: int = Field(default=1, ge=1, le=4)
    quality: QualidadeDoCenario = "padrao"
    seed: int | None = Field(default=None, ge=0, lt=SEMENTE_MAXIMA)


class ParametrosDoStoryboard(PedidoDoStoryboard):
    project_id: str = Field(pattern=ID)


class PedidoDeAnimacao(BaseModel):
    scene_ids: list[str] | None = Field(default=None, max_length=MAXIMO_DE_ESCOLHIDAS)
    draft: bool = False
    force: bool = False


class ParametrosDeAnimacao(PedidoDeAnimacao):
    project_id: str = Field(pattern=ID)


class PedidoDeAudio(BaseModel):
    transition: Transicao | None = None


class ParametrosDeAudio(PedidoDeAudio):
    project_id: str = Field(pattern=ID)


class PedidoDeMontagem(BaseModel):
    transition: Transicao | None = None


class ParametrosDeMontagem(PedidoDeMontagem):
    project_id: str = Field(pattern=ID)


class PedidoDeMiniaturas(BaseModel):
    count: int = Field(default=3, ge=1, le=6)
    text: str | None = Field(default=None, max_length=80)
    scene_ids: list[str] | None = Field(default=None, max_length=MAXIMO_DE_ESCOLHIDAS)


class ParametrosDeMiniaturas(PedidoDeMiniaturas):
    project_id: str = Field(pattern=ID)


class PedidoDeMetadados(BaseModel):
    mode: Literal["ia", "simples"] = "ia"


class ParametrosDeMetadados(PedidoDeMetadados):
    project_id: str = Field(pattern=ID)


class PedidoDeMetadadosEditados(BaseModel):
    """Os textos que o usuário ajustou à mão, por idioma («pt-BR» e «en»). Só os idiomas enviados mudam."""

    texts: dict[str, Any] = Field(min_length=1, max_length=2)


class PedidoDeVersaoEmOutroIdioma(BaseModel):
    language: Literal["pt-BR", "en"] | None = None  # sem informar: o idioma oposto ao do projeto
    mode: Literal["ia", "simples"] = "ia"


class ParametrosDeVersaoEmOutroIdioma(PedidoDeVersaoEmOutroIdioma):
    project_id: str = Field(pattern=ID)


class PedidoDeVariante(BaseModel):
    format: Literal["short", "longo"]


class PedidoDaNoite(BaseModel):
    project_ids: list[str] | None = Field(default=None, max_length=50)


class PedidoDeEdicaoDeCena(BaseModel):
    changes: dict[str, Any] = Field(min_length=1)


class PedidoDeNovaCena(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    position: int | None = Field(default=None, ge=1, le=500)


class PedidoDeAprovacao(BaseModel):
    stage: Literal["roteiro", "storyboard", "animacao"]
    approved: bool = True


class PedidoDeAprovacaoDaEtapa(BaseModel):
    approve_all: bool = False


class PedidoDeReordenacao(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)


class PedidoDeEscolhaDeCenario(BaseModel):
    media_id: str = Field(pattern=ID)


class PedidoDeVersao(BaseModel):
    version: int = Field(ge=1)
