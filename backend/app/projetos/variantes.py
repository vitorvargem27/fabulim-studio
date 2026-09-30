"""Projetos derivados: a versão em outro formato (Short ↔ vídeo longo) e a versão em outro idioma (português ↔ inglês).

Os dois reaproveitam o que dá do original (roteiro, personagens, música, ajustes e, na troca de idioma, os cenários) e deixam
para o usuário aprovar o que mudou. O original nunca é alterado. Cada projeto derivado guarda ``origem_id``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..erros import ErroParaOUsuario
from ..midias.servico import adotar_e_avisar
from .cenas import DadosDaCena
from .qualidade import DURACAO_MAXIMA_DO_LONGO_S, DURACAO_MAXIMA_DO_SHORT_S
from .repositorio import Projeto

if TYPE_CHECKING:
    from ..container import Servicos

AJUSTES_QUE_ACOMPANHAM = ("fps", "transition", "narrator", "voices")
NOME_DO_FORMATO = {"short": "Short", "longo": "vídeo longo"}
NOME_DO_IDIOMA = {"pt-BR": "PT-BR", "en": "EN"}


def ajustes_herdados(origem: Projeto) -> dict[str, Any]:
    return {k: origem.configuracoes[k] for k in AJUSTES_QUE_ACOMPANHAM if k in origem.configuracoes}


def _sem_o_visual(dados: DadosDaCena, *, guardar_semente: bool) -> dict[str, Any]:
    """A cena sem cenário, imagem, clipe e posições (dependem do formato): fica só o que foi escrito e aprovado no roteiro."""
    novo = dados.model_dump()
    semente = dados.background.seed if dados.background else dados.seed_hint
    novo.update(
        {
            "background": None,
            "candidates": [],
            "keyframe_media_id": None,
            "clip": None,
            "timeline": None,
            "layout": None,
            "seed_hint": semente if guardar_semente else None,
            "approved": {k: v for k, v in dados.approved.items() if k == "roteiro"},
        }
    )
    return novo


def criar_variante_de_formato(sv: Servicos, origem: Projeto, formato: str) -> tuple[Projeto, list[str]]:
    """O mesmo vídeo em Short ou em vídeo longo: roteiro e personagens iguais, cenários e posições refeitos no novo formato.

    A semente de cada cenário vai junto como dica (``seed_hint``): o cenário novo sai com o estilo e as cores do original.
    Devolve o projeto novo e os avisos (por exemplo, roteiro maior que o limite do Short).
    """
    if formato == origem.formato:
        raise ErroParaOUsuario("O projeto já está nesse formato.")
    cenas = sv.projetos.cenas(origem.id)
    if not cenas:
        raise ErroParaOUsuario("Gere o roteiro antes de criar a versão em outro formato: ela reaproveita as cenas.")
    limite = DURACAO_MAXIMA_DO_SHORT_S if formato == "short" else DURACAO_MAXIMA_DO_LONGO_S
    duracao = int(min(origem.duracao_alvo_s, limite))
    avisos: list[str] = []
    total = sum(DadosDaCena.model_validate(c.dados).duration_s for c in cenas)
    if formato == "short" and total > DURACAO_MAXIMA_DO_SHORT_S:
        avisos.append(
            f"O roteiro tem cerca de {total:.0f} s e o Short vai até {DURACAO_MAXIMA_DO_SHORT_S:.0f} s: "
            "tire ou encurte cenas na etapa do roteiro."
        )
    enredo = {**origem.enredo, "format": formato}
    novo = sv.projetos.criar(
        f"{origem.titulo} ({NOME_DO_FORMATO[formato]})",
        formato,
        origem.idioma,
        origem.estilo,
        duracao,
        enredo,
        list(origem.personagens),
        musica=dict(origem.musica),
        configuracoes=ajustes_herdados(origem),
        origem_id=origem.id,
    )
    for cena in cenas:
        sv.projetos.criar_cena(
            novo.id, _sem_o_visual(DadosDaCena.model_validate(cena.dados), guardar_semente=True), cena.ordem
        )
    aprovacoes: dict[str, bool] = {}
    if origem.aprovacoes.get("enredo"):  # o texto é o mesmo: o que estava aprovado continua aprovado
        aprovacoes["enredo"] = True
        if origem.aprovacoes.get("roteiro"):
            aprovacoes["roteiro"] = True
    etapa = "storyboard" if aprovacoes.get("roteiro") else ("roteiro" if aprovacoes else "enredo")
    atualizado = sv.projetos.atualizar(novo.id, aprovacoes=aprovacoes, etapa=etapa)
    assert atualizado is not None
    if not aprovacoes.get("roteiro"):
        avisos.append("O roteiro do original ainda não foi aprovado: aprove-o aqui para gerar os cenários.")
    return atualizado, avisos


def copiar_midia_para_a_cena(sv: Servicos, midia_id: str | None, cena_id: str, projeto_id: str) -> str | None:
    """Uma cópia independente da mídia (imagem) na cena nova: apagar o projeto original não estraga o derivado."""
    if not midia_id:
        return None
    original = sv.midias.obter(midia_id)
    if original is None:
        return None
    try:
        caminho = sv.midias.caminho_absoluto(original)
    except ValueError:
        return None
    if not caminho.is_file():
        return None
    copia = adotar_e_avisar(
        sv,
        caminho,
        tipo=original.tipo,
        papel=original.papel,
        extensao=original.formato or caminho.suffix.lstrip(".") or "png",
        mover=False,
        dono_tipo="cena",
        dono_id=cena_id,
        prompt=original.prompt,
        prompt_tecnico=original.prompt_tecnico,
        negativo=original.negativo,
        estilo=original.estilo,
        seed=original.seed,
        modelo=original.modelo,
        metadados={**original.metadados, "copied_from": original.id, "project_id": projeto_id},
    )
    return str(copia.id)


def dados_da_cena_no_outro_idioma(
    sv: Servicos, dados: DadosDaCena, traduzida: DadosDaCena, cena_id: str, projeto_id: str
) -> dict[str, Any]:
    """A cena traduzida com o mesmo visual: os cenários e a imagem-chave são copiados; o clipe não (a fala muda a duração)."""
    novo = traduzida.model_dump()
    fundo = dados.background
    copia_do_fundo = copiar_midia_para_a_cena(sv, fundo.media_id if fundo else None, cena_id, projeto_id)
    if fundo and copia_do_fundo:
        novo["background"] = {**fundo.model_dump(), "media_id": copia_do_fundo}
    else:
        novo["background"] = None
    candidatas = [
        copiar_midia_para_a_cena(sv, m, cena_id, projeto_id)
        for m in dados.candidates
        if m != (fundo.media_id if fundo else "")
    ]
    novo["candidates"] = [c for c in [copia_do_fundo, *candidatas] if c]
    novo["keyframe_media_id"] = copiar_midia_para_a_cena(sv, dados.keyframe_media_id, cena_id, projeto_id)
    novo.update({"clip": None, "timeline": None})
    aprovadas = {k: v for k, v in dados.approved.items() if k == "storyboard" and novo["background"]}
    novo["approved"] = aprovadas  # o roteiro traduzido precisa ser revisado; o cenário, se estava aprovado, continua
    return novo
