"""Os formulários dos três prompts que o usuário cola no app (briefing, seção 6): personagem, enredo e imagem avulsa.

As chaves são em inglês (a API), os rótulos em português ficam na interface. Tudo é validado por schema (Pydantic): o texto
colado só preenche campos, nunca vira instrução para o sistema.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Estilo = Literal["2D", "3D"]
FormatoDeImagem = Literal["16:9", "9:16", "1:1"]
TipoDeImagem = Literal["cenario", "objeto", "thumbnail", "livre"]


class FichaPersonagem(BaseModel):
    name: str = Field(default="", max_length=80)
    style: Estilo = "2D"
    species: str = Field(default="", max_length=200)
    apparent_age: str = Field(default="", max_length=120)
    appearance: str = Field(default="", max_length=1500)
    clothing: str = Field(default="", max_length=800)
    palette: str = Field(default="", max_length=400)
    personality: str = Field(default="", max_length=800)
    voice: str = Field(default="", max_length=400)
    expressions: str = Field(default="", max_length=400)
    notes: str = Field(default="", max_length=1500)


class FichaEnredo(BaseModel):
    title: str = Field(default="", max_length=160)
    format: Literal["short", "longo"] = "short"
    target_duration: str = Field(default="", max_length=60)
    language: Literal["pt-BR", "en"] = "pt-BR"
    style: Estilo = "2D"
    characters: list[str] = Field(default_factory=list, max_length=12)
    theme: str = Field(default="", max_length=400)
    settings: str = Field(default="", max_length=600)
    story: str = Field(default="", max_length=12000)
    music: str = Field(default="", max_length=400)
    notes: str = Field(default="", max_length=1500)

    @field_validator("characters")
    @classmethod
    def _nomes_limpos(cls, nomes: list[str]) -> list[str]:
        vistos: list[str] = []
        for nome in nomes:
            limpo = " ".join(nome.split())[:80]
            if limpo and limpo.lower() not in {v.lower() for v in vistos}:
                vistos.append(limpo)
        return vistos


class FichaImagem(BaseModel):
    kind: TipoDeImagem = "livre"
    style: Estilo = "2D"
    format: FormatoDeImagem = "16:9"
    characters: list[str] = Field(default_factory=list, max_length=6)
    description: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=1000)


TIPOS: dict[str, type[BaseModel]] = {"personagem": FichaPersonagem, "enredo": FichaEnredo, "imagem": FichaImagem}
