"""As etapas do fluxo de criação (briefing, seção 7.4) e a aprovação de cada uma.

Enredo e personagens → Roteiro → Storyboard → Animação → Áudio → Montagem → Revisão e exportação. Cada etapa só avança com a
aprovação do usuário. Aprovar as cenas de uma etapa uma a uma ou todas de uma vez ("Aprovar todas") é o que libera a etapa.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..erros import ErroParaOUsuario
from .cenas import ETAPAS_DA_CENA, DadosDaCena
from .repositorio import ETAPAS, Cena, Projeto

if TYPE_CHECKING:
    from ..container import Servicos

NOME_DAS_ETAPAS = {
    "enredo": "Enredo e personagens",
    "roteiro": "Roteiro",
    "storyboard": "Storyboard",
    "animacao": "Animação",
    "audio": "Áudio",
    "montagem": "Montagem",
    "revisao": "Revisão e exportação",
}


def proxima_etapa(etapa: str) -> str:
    i = ETAPAS.index(etapa)
    return ETAPAS[min(i + 1, len(ETAPAS) - 1)]


def _cenas_com_dados(cenas: list[Cena]) -> list[tuple[Cena, DadosDaCena]]:
    return [(c, DadosDaCena.model_validate(c.dados)) for c in cenas]


def pronta_para_aprovar(projeto: Projeto, cenas: list[Cena], etapa: str) -> tuple[bool, str]:
    """Se a etapa tem o que precisa para ser aprovada (e, se não tem, o que falta, em linguagem simples)."""
    dados = _cenas_com_dados(cenas)
    if etapa == "enredo":
        historia = str(projeto.enredo.get("story") or "").strip()
        return (bool(historia), "" if historia else "Escreva a história antes de aprovar o enredo.")
    if etapa == "roteiro":
        return (bool(dados), "" if dados else "Ainda não há cenas: gere o roteiro.")
    if etapa == "storyboard":
        sem = [c.ordem for c, d in dados if d.background is None]
        return (not sem and bool(dados), "" if not sem else f"Faltam cenários nas cenas {', '.join(map(str, sem))}.")
    if etapa == "animacao":
        sem = [c.ordem for c, d in dados if d.clip is None]
        return (not sem and bool(dados), "" if not sem else f"Faltam clipes nas cenas {', '.join(map(str, sem))}.")
    if etapa == "audio":
        pronto = bool((projeto.configuracoes.get("audio") or {}).get("mix_media_id"))
        return (pronto, "" if pronto else "Ainda não há áudio: gere o áudio.")
    if etapa == "montagem":
        pronto = bool(projeto.configuracoes.get("final_media_id"))
        return (pronto, "" if pronto else "Ainda não há vídeo montado.")
    return (True, "")


def situacao_das_etapas(projeto: Projeto, cenas: list[Cena]) -> dict[str, Any]:
    """Para a barra de etapas: cada etapa com o estado, quantas cenas foram aprovadas e o que impede de avançar."""
    dados = _cenas_com_dados(cenas)
    itens: list[dict[str, Any]] = []
    atual: str | None = None
    for etapa in ETAPAS:
        aprovada = bool(projeto.aprovacoes.get(etapa))
        anterior_ok = etapa == ETAPAS[0] or bool(projeto.aprovacoes.get(ETAPAS[ETAPAS.index(etapa) - 1]))
        pronta, falta = pronta_para_aprovar(projeto, cenas, etapa)
        if atual is None and not aprovada:
            atual = etapa
        item: dict[str, Any] = {
            "id": etapa,
            "name": NOME_DAS_ETAPAS[etapa],
            "approved": aprovada,
            "available": anterior_ok,
            "ready": pronta,
            "missing": falta,
        }
        if etapa in ETAPAS_DA_CENA:
            item["scenes_approved"] = sum(1 for _, d in dados if d.approved.get(etapa))
            item["scenes_total"] = len(dados)
        itens.append(item)
    return {"stages": itens, "current": atual or ETAPAS[-1]}


def exigir_etapa_aprovada(projeto: Projeto, etapa: str, para: str) -> None:
    """Bloqueia o avanço sem aprovação: o usuário vê o que falta em vez de um erro técnico."""
    if not projeto.aprovacoes.get(etapa):
        raise ErroParaOUsuario(f"Aprove a etapa «{NOME_DAS_ETAPAS[etapa]}» antes de {para}.")


def aprovar_etapa(sv: Servicos, projeto: Projeto, etapa: str, aprovar_todas: bool = False) -> Projeto:
    if etapa not in ETAPAS:
        raise ErroParaOUsuario("Etapa desconhecida.")
    indice = ETAPAS.index(etapa)
    if indice > 0:
        exigir_etapa_aprovada(projeto, ETAPAS[indice - 1], f"aprovar «{NOME_DAS_ETAPAS[etapa]}»")
    cenas = sv.projetos.cenas(projeto.id)
    pronta, falta = pronta_para_aprovar(projeto, cenas, etapa)
    if not pronta:
        raise ErroParaOUsuario(falta)
    if etapa in ETAPAS_DA_CENA:
        pendentes = [c for c, d in _cenas_com_dados(cenas) if not d.approved.get(etapa)]
        if pendentes and not aprovar_todas:
            raise ErroParaOUsuario(f"Aprove todas as cenas antes (faltam {len(pendentes)}), ou use «Aprovar todas».")
        for cena in pendentes:
            dados = DadosDaCena.model_validate(cena.dados).model_dump()
            dados["approved"] = {**dados["approved"], etapa: True}
            sv.projetos.atualizar_cena_sem_versao(cena.id, dados)
    aprovacoes = {**projeto.aprovacoes, etapa: True}
    novo = sv.projetos.atualizar(projeto.id, aprovacoes=aprovacoes, etapa=proxima_etapa(etapa))
    assert novo is not None
    return novo


def reabrir_a_partir(sv: Servicos, projeto: Projeto, etapa: str) -> Projeto:
    """Volta a etapa (e as seguintes) para «não aprovada»: o que foi gerado continua, só volta a pedir aprovação."""
    indice = ETAPAS.index(etapa)
    depois = set(ETAPAS[indice:])
    aprovacoes = {k: v for k, v in projeto.aprovacoes.items() if k not in depois}
    novo = sv.projetos.atualizar(projeto.id, aprovacoes=aprovacoes, etapa=etapa)
    assert novo is not None
    return novo


def cascata_da_edicao(sv: Servicos, projeto: Projeto, mudou: set[str]) -> Projeto:
    """Uma edição numa cena reabre as etapas que ela afeta: cenário refaz o storyboard, texto ou movimento refaz a animação."""
    from .cenas import CAMPOS_DO_CENARIO, CAMPOS_DO_MOVIMENTO

    if mudou & CAMPOS_DO_CENARIO:
        primeira = "storyboard"
    elif mudou & CAMPOS_DO_MOVIMENTO:
        primeira = "animacao"
    else:
        return projeto
    if not any(projeto.aprovacoes.get(e) for e in ETAPAS[ETAPAS.index(primeira) :]):
        return projeto
    return reabrir_a_partir(sv, projeto, primeira)
