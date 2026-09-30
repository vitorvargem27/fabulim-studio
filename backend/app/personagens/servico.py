"""Regras da biblioteca de personagens que várias ferramentas usam (imagem avulsa, vídeo): fichas, referências e vozes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from ..erros import ErroParaOUsuario
from ..motores.voz import VOZES, lingua_da_voz
from ..prompts.formatos import FichaPersonagem
from ..prompts.parser import normalizar
from .repositorio import Personagem

if TYPE_CHECKING:
    from ..container import Servicos

VOZ_PADRAO_POR_IDIOMA = {"pt-BR": "pf_dora", "en": "af_heart"}
TOM_MINIMO = 0.7
TOM_MAXIMO = 1.4


class PersonagemSemImagem(ErroParaOUsuario):
    """O personagem ainda não tem uma imagem escolhida: não dá para usá-lo como referência."""


def ficha_do_personagem(personagem: Personagem) -> FichaPersonagem:
    try:
        return FichaPersonagem.model_validate({**personagem.ficha, "name": personagem.nome, "style": personagem.estilo})
    except ValidationError:  # ficha antiga ou editada à mão no banco: usa só o que é seguro
        return FichaPersonagem(name=personagem.nome, style="3D" if personagem.estilo == "3D" else "2D")


def imagem_principal(sv: Servicos, personagem: Personagem) -> Path:
    """O arquivo da imagem escolhida (fundo branco), usado como referência para manter o personagem igual."""
    if not personagem.imagem_principal_id:
        raise PersonagemSemImagem(
            f"«{personagem.nome}» ainda não tem uma imagem escolhida. Gere as variações e escolha uma."
        )
    midia = sv.midias.obter(personagem.imagem_principal_id)
    if midia is None:
        raise PersonagemSemImagem(f"A imagem principal de «{personagem.nome}» não está mais na biblioteca.")
    caminho = sv.midias.caminho_absoluto(midia)
    if not caminho.is_file():
        raise PersonagemSemImagem(f"O arquivo da imagem principal de «{personagem.nome}» sumiu do disco.")
    return caminho


def referencias(sv: Servicos, ids: list[str]) -> tuple[list[Personagem], tuple[Path, ...]]:
    """Os personagens pedidos e as imagens deles (na ordem). Personagem que não existe ou sem imagem é um erro claro."""
    personagens: list[Personagem] = []
    caminhos: list[Path] = []
    for id_ in ids:
        personagem = sv.personagens.obter(id_)
        if personagem is None:
            raise PersonagemSemImagem("Um dos personagens escolhidos não existe mais na biblioteca.")
        personagens.append(personagem)
        caminhos.append(imagem_principal(sv, personagem))
    return personagens, tuple(caminhos)


def voz_valida(voz: dict[str, Any]) -> dict[str, Any]:
    """Confere e normaliza a voz de um personagem: só vozes conhecidas e tom e velocidade dentro de limites seguros."""
    ids = {v["id"] for vozes in VOZES.values() for v in vozes}
    identificador = str(voz.get("id") or "")
    if identificador not in ids:
        raise ValueError("Voz desconhecida. Escolha uma da lista.")
    try:
        velocidade = float(voz.get("speed", 1.0))
        tom = float(voz.get("pitch", 1.0))
    except (TypeError, ValueError) as exc:
        raise ValueError("Velocidade e tom precisam ser números.") from exc
    if not 0.6 <= velocidade <= 1.4:
        raise ValueError("A velocidade da voz fica entre 0,6 e 1,4.")
    if not TOM_MINIMO <= tom <= TOM_MAXIMO:
        raise ValueError("O tom da voz fica entre 0,7 e 1,4.")
    idioma = "en" if identificador in {v["id"] for v in VOZES["en"]} else "pt-BR"
    return {
        "id": identificador,
        "speed": round(velocidade, 2),
        "pitch": round(tom, 2),
        "language": idioma,
        "lang_code": lingua_da_voz(identificador),
    }


_FEMININO = re.compile(
    r"\b(feminin\w*|menina|garota|mulher|princesa|mamae|coelha|gata|leoa|ursa|ovelha|galinha|vaca|cachorra|macaca|fada)\b"
)
_MASCULINO = re.compile(
    r"\b(masculin\w*|menino|garoto|homem|rapaz|principe|papai|coelho|gato|leao|urso|cachorro|macaco)\b"
)
_AGUDA = re.compile(r"\b(agud\w*|fina|infantil)\b")
_GRAVE = re.compile(r"\b(grave|grossa|profunda|rouca)\b")
_LENTA = re.compile(r"\b(lent\w*|calm\w*|devagar|pausad\w*|suave)\b")
_RAPIDA = re.compile(r"\b(rapid\w*|animad\w*|agitad\w*|energetic\w*)\b")
_INGLES = re.compile(r"\b(en|ingles|english|en-us)\b")
# (fala em inglês?, voz masculina?) → voz do Kokoro
_VOZ_INICIAL = {(False, False): "pf_dora", (False, True): "pm_alex", (True, False): "af_heart", (True, True): "am_adam"}


def voz_sugerida(ficha: FichaPersonagem) -> dict[str, Any]:
    """Uma voz inicial a partir do que a ficha diz (tom, velocidade, idioma, gênero). O usuário ajusta e ouve depois."""
    texto = normalizar(" ".join([ficha.voice, ficha.species, ficha.name, ficha.appearance]))
    ingles = _INGLES.search(normalizar(ficha.voice)) is not None
    masculina = _MASCULINO.search(texto) is not None and _FEMININO.search(texto) is None
    identificador = _VOZ_INICIAL[(ingles, masculina)]
    tom = 1.15 if _AGUDA.search(texto) else 0.88 if _GRAVE.search(texto) else 1.0
    velocidade = 0.9 if _LENTA.search(texto) else 1.1 if _RAPIDA.search(texto) else 1.0
    return voz_valida({"id": identificador, "speed": velocidade, "pitch": tom})
