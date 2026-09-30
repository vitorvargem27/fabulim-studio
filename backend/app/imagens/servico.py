"""Gerar imagem avulsa: os parâmetros do pedido, o prompt técnico e a estimativa de tempo antes de gerar."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..motores.interfaces import MotorDeImagem
from ..motores.tipos import dimensoes_da_imagem
from ..motores.util import formatar_duracao
from ..personagens.repositorio import Personagem
from ..prompts.formatos import FichaImagem
from ..prompts.tecnico import prompt_imagem

MAXIMO_DE_VARIACOES = 4
MAXIMO_DE_REFERENCIAS = 3  # o modelo aceita várias, mas o tempo cresce a cada uma
SEMENTE_MAXIMA = 2**31 - 1


class ParametrosDeImagem(BaseModel):
    """O que a página Gerar imagem manda; o job guarda exatamente isto (e o handler valida de novo)."""

    form: FichaImagem
    technical_prompt: str | None = Field(default=None, max_length=4000)
    quality: Literal["rascunho", "padrao", "alta"] = "padrao"
    count: int = Field(default=1, ge=1, le=MAXIMO_DE_VARIACOES)
    seed: int | None = Field(default=None, ge=0, lt=SEMENTE_MAXIMA)
    character_ids: list[str] = Field(default_factory=list, max_length=MAXIMO_DE_REFERENCIAS)
    based_on: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")  # "parecida com esta imagem"


@dataclass(frozen=True)
class Estimativa:
    largura: int
    altura: int
    por_imagem_s: float
    total_s: float

    def para_api(self) -> dict[str, Any]:
        return {
            "width": self.largura,
            "height": self.altura,
            "per_image_seconds": round(self.por_imagem_s, 1),
            "total_seconds": round(self.total_s, 1),
            "total_label": formatar_duracao(self.total_s),
        }


def estimar(motor: MotorDeImagem, formato: str, qualidade: str, quantidade: int, com_referencia: bool) -> Estimativa:
    largura, altura = dimensoes_da_imagem(formato, qualidade)
    por_imagem = motor.estimativa(largura, altura, com_referencia)
    return Estimativa(largura, altura, por_imagem, por_imagem * quantidade)


def prompt_tecnico_da_ficha(ficha: FichaImagem, personagens: list[Personagem], *, com_referencia: bool = False) -> str:
    """O prompt que vai de fato para o modelo (o usuário vê e pode editar). Com personagens, o modelo parte deles."""
    prompt = prompt_imagem(ficha, tem_referencias=bool(personagens) or com_referencia)
    if personagens:
        nomes = ", ".join(p.nome for p in personagens)
        prompt += f" Characters in the scene: {nomes}."
    return prompt


def sementes(base: int | None, quantidade: int) -> list[int]:
    """Uma semente por variação. Com semente informada, as variações seguem dela (dá para reproduzir); sem, sorteia."""
    inicio = base if base is not None else random.SystemRandom().randrange(1, SEMENTE_MAXIMA)
    return [(inicio + i * 7919) % SEMENTE_MAXIMA or 1 for i in range(quantidade)]
