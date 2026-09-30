"""Pedidos (API e jobs) dos clipes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..imagens.servico import SEMENTE_MAXIMA

ID = r"^[0-9a-f]{32}$"
PresetDeTamanho = Literal["9:16", "16:9", "1:1", "720p"]


class PedidoDoClipeRapido(BaseModel):
    character_id: str = Field(pattern=ID)
    prompt: str = Field(min_length=3, max_length=300)
    duration_s: float = Field(default=5.0, ge=3.0, le=10.0)
    format: Literal["16:9", "9:16"] = "9:16"
    quality: Literal["rascunho", "padrao"] = "rascunho"
    seed: int | None = Field(default=None, ge=0, lt=SEMENTE_MAXIMA)


class PedidoDeUniao(BaseModel):
    clip_ids: list[str] = Field(min_length=2, max_length=12)
    transition: Literal["corte", "fade", "suave"] = "corte"
    size: Literal["auto", "9:16", "16:9", "1:1", "720p"] = "auto"


class PedidoDeReenquadramento(BaseModel):
    preset: PresetDeTamanho
    mode: Literal["fit", "crop"] = "fit"


class ParametrosDeReenquadramento(PedidoDeReenquadramento):
    clip_id: str = Field(pattern=ID)


class PedidoDeContinuacao(BaseModel):
    prompt: str = Field(min_length=3, max_length=12_000)
    character_ids: list[str] = Field(default_factory=list, max_length=8)
    title: str = Field(default="", max_length=160)
    last_scene: str = Field(
        default="", max_length=400
    )  # o que aparece no final do clipe (não há modelo de visão local)
