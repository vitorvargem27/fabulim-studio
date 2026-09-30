"""Fila noturna (briefing, seção 7.9): renderizar tudo o que já foi aprovado enquanto o usuário dorme.

A noite nunca aprova nada por conta própria. Para cada projeto, ela olha até onde o usuário já aprovou e pede o próximo trabalho
pesado que ainda não foi feito: cenários (roteiro aprovado), animação (storyboard aprovado), áudio (animação aprovada) ou
montagem (áudio aprovado). De manhã, o usuário revisa o resultado e aprova, como sempre. Um trabalho por projeto por noite.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..jobs.models import ATIVOS, Job
from ..jobs.servico import enfileirar
from .cenas import DadosDaCena
from .repositorio import Projeto

if TYPE_CHECKING:
    from ..container import Servicos

MOTORES_DA_ETAPA: dict[str, tuple[str, ...]] = {
    "storyboard": ("image",),
    "animacao": ("voice", "ffmpeg"),
    "audio": ("voice", "ffmpeg"),
    "montagem": ("ffmpeg",),
}
NOME_DA_ETAPA = {
    "storyboard": "cenários (storyboard)",
    "animacao": "animação das cenas",
    "audio": "áudio",
    "montagem": "montagem do vídeo",
}


@dataclass(frozen=True)
class ItemDaNoite:
    projeto_id: str
    titulo: str
    etapa: str
    tipo: str  # tipo do job da fila
    pedido: dict[str, Any]
    bloqueio: str | None = None  # por que não dá para rodar agora (motor faltando ou trabalho já na fila)

    def para_api(self) -> dict[str, Any]:
        return {
            "project_id": self.projeto_id,
            "title": self.titulo,
            "stage": self.etapa,
            "stage_label": NOME_DA_ETAPA[self.etapa],
            "kind": self.tipo,
            "blocked_by": self.bloqueio,
        }


def proximo_trabalho(
    projeto: Projeto, cenas: list[DadosDaCena], configuracoes: dict[str, Any]
) -> tuple[str, str, dict[str, Any]] | None:
    """(etapa, tipo do job, pedido) do próximo trabalho pesado liberado pelas aprovações, ou ``None`` se não há nada a fazer."""
    if not cenas:
        return None
    aprovacoes = projeto.aprovacoes
    if aprovacoes.get("audio") and not configuracoes.get("final_media_id"):
        return "montagem", "projeto.montar", {}
    if aprovacoes.get("animacao") and not (configuracoes.get("audio") or {}).get("mix_media_id"):
        return "audio", "projeto.audio", {}
    if aprovacoes.get("storyboard") and any(d.clip is None for d in cenas):
        return "animacao", "projeto.animar", {"draft": False, "force": False}
    if aprovacoes.get("roteiro") and any(d.background is None for d in cenas):
        return "storyboard", "projeto.storyboard", {"mode": "faltantes", "variations": 1, "quality": "padrao"}
    return None


def _job_ativo(sv: Servicos, tipo: str, projeto_id: str) -> Job | None:
    return next(
        (j for j in sv.store.listar(ATIVOS) if j.kind == tipo and j.params.get("project_id") == projeto_id), None
    )


def plano_da_noite(sv: Servicos, ids: list[str] | None = None) -> list[ItemDaNoite]:
    """O que a fila noturna faria agora (a lista que a interface mostra antes de o usuário confirmar)."""
    plano: list[ItemDaNoite] = []
    for projeto in sv.projetos.listar(limite=300):
        if ids is not None and projeto.id not in ids:
            continue
        cenas = [DadosDaCena.model_validate(c.dados) for c in sv.projetos.cenas(projeto.id)]
        proximo = proximo_trabalho(projeto, cenas, projeto.configuracoes)
        if proximo is None:
            continue
        etapa, tipo, pedido = proximo
        bloqueio = sv.motores.motivo(*MOTORES_DA_ETAPA[etapa])
        if bloqueio is None and _job_ativo(sv, tipo, projeto.id) is not None:
            bloqueio = "Já está na fila."
        plano.append(ItemDaNoite(projeto.id, projeto.titulo, etapa, tipo, pedido, bloqueio))
    return plano


def enfileirar_a_noite(sv: Servicos, ids: list[str] | None = None) -> tuple[list[Job], list[ItemDaNoite]]:
    """Enfileira o plano da noite. Devolve (jobs criados, itens que ficaram de fora com o motivo)."""
    jobs: list[Job] = []
    ignorados: list[ItemDaNoite] = []
    for item in plano_da_noite(sv, ids):
        if item.bloqueio:
            ignorados.append(item)
            continue
        jobs.append(
            enfileirar(
                sv,
                item.tipo,
                {"project_id": item.projeto_id, **item.pedido},
                titulo=f"Fila noturna: {NOME_DA_ETAPA[item.etapa]} de «{item.titulo}»",
            )
        )
    return jobs, ignorados
