"""Como um projeto e as cenas dele aparecem para a interface, e as regras de criação (duração alvo, personagens, avisos de estilo)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ..animacao.layout import ItemDeLayout
from ..jobs.models import ATIVOS
from ..personagens import fluxos
from ..personagens.repositorio import Personagem
from ..prompts.parser import normalizar
from .cenas import DadosDaCena
from .etapas import situacao_das_etapas
from .pipeline import layout_da_cena, personagens_do_projeto
from .qualidade import DURACAO_MAXIMA_DO_LONGO_S, DURACAO_MAXIMA_DO_SHORT_S
from .repositorio import Cena, Projeto

if TYPE_CHECKING:
    from ..container import Servicos

DURACAO_PADRAO_S = {"short": 45, "longo": 120}
DURACAO_MINIMA_S = 15


def duracao_alvo_em_segundos(texto: str, formato: str) -> int:
    """«60 s», «3 min», «1:30» ou só «45»: a duração alvo em segundos, dentro do limite do formato (Short até 60 s)."""
    limite = DURACAO_MAXIMA_DO_SHORT_S if formato == "short" else DURACAO_MAXIMA_DO_LONGO_S
    n = normalizar(texto)
    segundos: float | None = None
    if m := re.search(r"(\d+):(\d{2})", n):
        segundos = int(m.group(1)) * 60 + int(m.group(2))
    elif m := re.search(r"(\d+(?:[.,]\d+)?)\s*(?:min|minutos?|m\b)", n):
        segundos = float(m.group(1).replace(",", ".")) * 60
    elif m := re.search(r"(\d+(?:[.,]\d+)?)", n):
        valor = float(m.group(1).replace(",", "."))
        segundos = valor  # sem unidade: segundos
    if segundos is None or segundos <= 0:
        return int(min(DURACAO_PADRAO_S[formato], limite))
    return int(min(max(segundos, DURACAO_MINIMA_S), limite))


def midia_api(sv: Servicos, id_: str | None) -> dict[str, Any] | None:
    if not id_:
        return None
    midia = sv.midias.obter(id_)
    return midia.para_api() if midia else None


def avisos_de_estilo(projeto: Projeto, personagens: list[Personagem]) -> list[dict[str, str]]:
    """Personagem 2D num vídeo 3D (ou o contrário): avisa e oferece a conversão (briefing, seção 7.3)."""
    return [
        {
            "character_id": p.id,
            "name": p.nome,
            "character_style": p.estilo,
            "project_style": projeto.estilo,
            "message": f"«{p.nome}» é {p.estilo} e o vídeo é {projeto.estilo}. Crie a versão {projeto.estilo} dele na página Personagens.",
        }
        for p in personagens
        if p.estilo != projeto.estilo
    ]


def cena_para_api(sv: Servicos, projeto: Projeto, cena: Cena, nomes: dict[str, str]) -> dict[str, Any]:
    dados = DadosDaCena.model_validate(cena.dados)
    api = cena.para_api()
    api["data"] = dados.model_dump()
    api["keyframe"] = midia_api(sv, dados.keyframe_media_id)
    api["background_media"] = midia_api(sv, dados.background.media_id if dados.background else None)
    api["candidate_media"] = [m for m in (midia_api(sv, i) for i in dados.candidates) if m]
    api["clip_media"] = midia_api(sv, dados.clip.media_id if dados.clip else None)
    api["character_names"] = [nomes.get(i, "?") for i in dados.characters]
    api["layout"] = [item.para_dict() for item in layout_da_cena(projeto, dados)] if dados.characters else []
    api["effective_duration_s"] = float((dados.timeline or {}).get("duration_s", dados.duration_s))
    return api


def resumo(sv: Servicos, projeto: Projeto) -> dict[str, Any]:
    cenas = sv.projetos.cenas(projeto.id)
    miniatura = None
    final = projeto.configuracoes.get("final_media_id")
    if final and (midia := sv.midias.obter(final)) and midia.miniatura:
        miniatura = f"/api/media/{midia.id}/thumb"
    if miniatura is None:
        for cena in cenas:
            capa = DadosDaCena.model_validate(cena.dados).keyframe_media_id
            if capa and (midia := sv.midias.obter(capa)) and midia.miniatura:
                miniatura = f"/api/media/{midia.id}/thumb"
                break
    api = projeto.para_api()
    api.pop("story", None)
    api.update(
        {
            "scene_count": len(cenas),
            "thumb_url": miniatura,
            "has_final": bool(final),
            "characters": [p.nome for p in personagens_do_projeto(sv, projeto)],
        }
    )
    return api


def detalhes(sv: Servicos, projeto: Projeto) -> dict[str, Any]:
    cenas = sv.projetos.cenas(projeto.id)
    personagens = personagens_do_projeto(sv, projeto)
    nomes = {p.id: p.nome for p in personagens}
    audio = projeto.configuracoes.get("audio") or {}
    ativos = [
        j.model_dump(mode="json")
        for j in sv.store.listar(ATIVOS)
        if str(j.params.get("project_id") or "") == projeto.id
    ]
    return {
        "project": projeto.para_api(),
        "scenes": [cena_para_api(sv, projeto, c, nomes) for c in cenas],
        "characters": [fluxos.resumo(sv, p) for p in personagens],
        "missing_character_ids": [i for i in projeto.personagens if i not in nomes],
        "style_warnings": avisos_de_estilo(projeto, personagens),
        "stages": situacao_das_etapas(projeto, cenas),
        "files": {
            "final": midia_api(sv, projeto.configuracoes.get("final_media_id")),
            "subtitles": midia_api(sv, audio.get("srt_media_id")),
            "mix": midia_api(sv, audio.get("mix_media_id")),
            "music": midia_api(sv, audio.get("music_media_id")),
            "thumbnails": [
                m.para_api()
                for m in sv.midias.listar(papeis=("thumbnail",), dono_tipo="projeto", dono_id=projeto.id, limite=12)
            ],
        },
        "metadata": projeto.configuracoes.get("metadata"),
        "quality": projeto.configuracoes.get("quality"),
        "active_jobs": ativos,
        "variants": [
            {"id": v.id, "title": v.titulo, "language": v.idioma, "format": v.formato, "stage": v.etapa}
            for v in sv.projetos.variantes_de(projeto.id)
        ],
    }


def layout_padrao(projeto: Projeto, dados: DadosDaCena) -> list[ItemDeLayout]:
    return layout_da_cena(projeto, dados)
