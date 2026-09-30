"""Os pedidos (API e jobs) das ferramentas de personagem. O job guarda exatamente estes campos e valida de novo ao rodar."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from ..imagens.servico import SEMENTE_MAXIMA
from ..prompts.formatos import FichaPersonagem
from ..prompts.tecnico import EXPRESSOES, POSES

ID_DE_MIDIA = r"^[0-9a-f]{32}$"
SLOTS_DA_FOLHA = (*POSES, *EXPRESSOES)  # frente, três quartos, lado, feliz, triste, surpreso, sono, bravo
QualidadeDePersonagem = Literal["rascunho", "padrao"]


class PedidoDeCriacao(BaseModel):
    form: FichaPersonagem
    original_prompt: str = Field(default="", max_length=30_000)


class PedidoDeEdicao(BaseModel):
    form: FichaPersonagem | None = None
    technical_prompt: str | None = Field(default=None, max_length=4000)


class ParametrosDeVariacoes(BaseModel):
    character_id: str = Field(pattern=ID_DE_MIDIA)
    count: int = Field(default=4, ge=1, le=4)
    quality: QualidadeDePersonagem = "rascunho"
    seed: int | None = Field(default=None, ge=0, lt=SEMENTE_MAXIMA)
    technical_prompt: str | None = Field(default=None, max_length=4000)
    reference_media_id: str | None = Field(default=None, pattern=ID_DE_MIDIA)  # conversão 2D↔3D


class PedidoDeVariacoes(BaseModel):
    count: int = Field(default=4, ge=1, le=4)
    quality: QualidadeDePersonagem = "rascunho"
    seed: int | None = Field(default=None, ge=0, lt=SEMENTE_MAXIMA)
    technical_prompt: str | None = Field(default=None, max_length=4000)


class PedidoDeFolha(BaseModel):
    slots: list[str] = Field(default_factory=lambda: list(POSES), min_length=1, max_length=len(SLOTS_DA_FOLHA))
    quality: QualidadeDePersonagem = "rascunho"
    seed: int | None = Field(default=None, ge=0, lt=SEMENTE_MAXIMA)

    @field_validator("slots")
    @classmethod
    def _so_poses_e_expressoes_conhecidas(cls, slots: list[str]) -> list[str]:
        desconhecidos = [s for s in slots if s not in SLOTS_DA_FOLHA]
        if desconhecidos:
            raise ValueError(f"pose ou expressão desconhecida: {', '.join(desconhecidos)}")
        return list(dict.fromkeys(slots))


class PedidoDeEscolha(BaseModel):
    media_id: str = Field(pattern=ID_DE_MIDIA)


class ParametrosDeRecorte(BaseModel):
    character_id: str = Field(pattern=ID_DE_MIDIA)
    media_id: str = Field(pattern=ID_DE_MIDIA)
    slot: str = Field(default="principal", pattern=r"^[a-z_]{1,20}$")


class ParametrosDeFolha(BaseModel):
    character_id: str = Field(pattern=ID_DE_MIDIA)
    slots: list[str] = Field(default_factory=lambda: list(POSES), min_length=1, max_length=len(SLOTS_DA_FOLHA))
    quality: QualidadeDePersonagem = "rascunho"
    seed: int | None = Field(default=None, ge=0, lt=SEMENTE_MAXIMA)

    @field_validator("slots")
    @classmethod
    def _so_poses_e_expressoes_conhecidas(cls, slots: list[str]) -> list[str]:
        desconhecidos = [s for s in slots if s not in SLOTS_DA_FOLHA]
        if desconhecidos:
            raise ValueError(f"pose ou expressão desconhecida: {', '.join(desconhecidos)}")
        return list(dict.fromkeys(slots))  # sem repetir


class PedidoDeVoz(BaseModel):
    id: str = Field(max_length=20)
    speed: float = 1.0
    pitch: float = 1.0

    def para_dict(self) -> dict[str, Any]:
        return {"id": self.id, "speed": self.speed, "pitch": self.pitch}


class ParametrosDeVozDeTeste(BaseModel):
    character_id: str = Field(pattern=ID_DE_MIDIA)
    text: str = Field(min_length=1, max_length=300)
    voice: dict[str, Any] | None = None


class PedidoDeVozDeTeste(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    voice: PedidoDeVoz | None = None


class PedidoDeConversao(BaseModel):
    count: int = Field(default=2, ge=1, le=4)
    quality: QualidadeDePersonagem = "rascunho"
