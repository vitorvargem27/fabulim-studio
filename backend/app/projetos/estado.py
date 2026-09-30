"""Leitura e gravação do que os jobs fazem nas cenas de um projeto, sem apagar edições feitas enquanto o job rodava."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..erros import ErroParaOUsuario
from ..midias.servico import remover_e_avisar
from .cenas import DadosDaCena
from .repositorio import Cena, Projeto

if TYPE_CHECKING:
    from ..container import Servicos


def carregar_projeto(sv: Servicos, id_: str) -> Projeto:
    projeto = sv.projetos.obter(id_)
    if projeto is None:
        raise ErroParaOUsuario("O projeto não existe mais.")
    return projeto


def cenas_do_projeto(sv: Servicos, projeto: Projeto, ids: list[str] | None = None) -> list[tuple[Cena, DadosDaCena]]:
    cenas = sv.projetos.cenas(projeto.id)
    if ids:
        escolhidas = set(ids)
        cenas = [c for c in cenas if c.id in escolhidas]
    return [(c, DadosDaCena.model_validate(c.dados)) for c in cenas]


def dados_atuais(sv: Servicos, cena_id: str) -> DadosDaCena | None:
    """Os dados da cena agora (o usuário pode ter editado enquanto o job trabalhava): o job parte destes, não dos que leu no início."""
    cena = sv.projetos.cena(cena_id)
    return DadosDaCena.model_validate(cena.dados) if cena else None


def gravar_andamento(sv: Servicos, cena_id: str, mudar: dict[str, Any]) -> None:
    """Grava campos de controle (clipe, linha do tempo...) sem criar versão no histórico da cena."""
    dados = dados_atuais(sv, cena_id)
    if dados is None:
        return
    novos = dados.model_dump()
    novos.update(mudar)
    sv.projetos.atualizar_cena_sem_versao(cena_id, DadosDaCena.model_validate(novos).model_dump())


def limpar_midias_antigas(sv: Servicos, ids: list[str | None], manter: set[str]) -> None:
    for id_ in ids:
        if id_ and id_ not in manter:
            remover_e_avisar(sv, id_)
