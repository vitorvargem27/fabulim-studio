"""Construtores de personagens prontos (com recortes) e de projetos com cenas, para os testes do pipeline de vídeo."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from app.container import Servicos
from app.personagens.repositorio import Personagem
from app.projetos.cenas import DadosDaCena
from app.projetos.repositorio import Cena, Projeto

SLOTS_PADRAO = ("principal", "frente", "lado", "feliz")


def png_de_personagem(caminho: Path, cor: tuple[int, int, int] = (230, 20, 20)) -> Path:
    imagem = Image.new("RGBA", (100, 160), (0, 0, 0, 0))
    ImageDraw.Draw(imagem).ellipse((8, 4, 92, 156), fill=(*cor, 255))
    imagem.save(caminho)
    return caminho


def png_de_fundo(caminho: Path, tamanho: tuple[int, int] = (320, 180)) -> Path:
    Image.new("RGB", tamanho, (120, 190, 240)).save(caminho)
    return caminho


def personagem_pronto(
    sv: Servicos,
    pasta: Path,
    nome: str = "Lila",
    estilo: str = "2D",
    slots: tuple[str, ...] = SLOTS_PADRAO,
    voz: dict[str, Any] | None = None,
    **ficha: Any,
) -> Personagem:
    """Um personagem com imagem principal e os recortes (PNG transparente) das poses pedidas."""
    personagem = sv.personagens.criar(
        nome,
        estilo,
        {"name": nome, "style": estilo, "species": "coelha", "appearance": "pelo lilás", **ficha},
        voz=voz,
    )
    principal = sv.midias.adotar(
        png_de_fundo(pasta / f"{nome}-principal.png", (64, 64)),
        tipo="imagem",
        papel="variacao",
        dono_tipo="personagem",
        dono_id=personagem.id,
        metadados={"character_version": 1},
    )
    sv.personagens.definir_imagem_principal(personagem.id, principal.id)
    for slot in slots:
        sv.midias.adotar(
            png_de_personagem(pasta / f"{nome}-{slot}.png"),
            tipo="imagem",
            papel="recorte",
            dono_tipo="personagem",
            dono_id=personagem.id,
            pai_id=principal.id,
            metadados={"slot": slot, "character_version": 1},
        )
    sv.personagens.definir_estado(personagem.id, "pronto")
    atual = sv.personagens.obter(personagem.id)
    assert atual is not None
    return atual


def projeto_com_cenas(
    sv: Servicos,
    personagens: list[Personagem],
    cenas: list[dict[str, Any]] | None = None,
    *,
    formato: str = "short",
    idioma: str = "pt-BR",
    duracao_alvo_s: int = 12,
    **configuracoes: Any,
) -> tuple[Projeto, list[Cena]]:
    projeto = sv.projetos.criar(
        "A chuva do jardim",
        formato,
        idioma,
        "2D",
        duracao_alvo_s,
        {"title": "A chuva do jardim", "story": "Lila brinca no jardim. Começa a chover.", "language": idioma},
        [p.id for p in personagens],
        configuracoes=configuracoes,
    )
    padrao = [
        {
            "title": "O jardim",
            "duration_s": 5.0,
            "visual": "um jardim florido de manhã",
            "action": "brinca e pula",
            "characters": [p.id for p in personagens],
            "narration": "Era uma vez um jardim.",
            "dialogue": [{"character_id": personagens[0].id, "text": "Que dia lindo!"}] if personagens else [],
            "sfx": ["boing"],
        },
        {
            "title": "A chuva",
            "duration_s": 5.0,
            "visual": "um céu nublado com gotas de chuva",
            "action": "corre para se abrigar",
            "characters": [p.id for p in personagens][:1],
            "narration": "Começou a chover.",
        },
    ]
    criadas = [
        sv.projetos.criar_cena(projeto.id, DadosDaCena.model_validate(d).model_dump())
        for d in (padrao if cenas is None else cenas)
    ]
    return projeto, criadas


def dar_cenario(sv: Servicos, pasta: Path, cena: Cena, nome: str = "fundo") -> str:
    """Dá a uma cena um cenário (imagem 16:9 simples) e devolve o id da mídia."""
    midia = sv.midias.adotar(
        png_de_fundo(pasta / f"{nome}-{cena.id[:6]}.png"),
        tipo="imagem",
        papel="fundo",
        dono_tipo="cena",
        dono_id=cena.id,
        seed=5,
    )
    dados = DadosDaCena.model_validate(cena.dados).model_dump()
    dados["background"] = {"media_id": midia.id, "seed": 5, "prompt": "x", "quality": "padrao"}
    dados["candidates"] = [midia.id]
    sv.projetos.atualizar_cena_sem_versao(cena.id, dados)
    return midia.id
