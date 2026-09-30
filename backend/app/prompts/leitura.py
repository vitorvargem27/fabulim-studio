"""O resultado da leitura de um prompt, do jeito que a interface recebe: formulário, avisos e bloqueio do filtro de conteúdo."""

from __future__ import annotations

from typing import Any

from ..conteudo.filtro import Reprovacao, tem_tentativa_de_injecao, verificar_campos
from .parser import Interpretacao

AVISO_DE_INJECAO = (
    "O texto tem um trecho que parece uma ordem para o sistema. "
    "Ele foi tratado só como texto do prompt e não muda nenhuma regra."
)


def bloqueio(interpretacao: Interpretacao) -> Reprovacao | None:
    """O filtro de conteúdo examina todos os campos de texto do formulário já preenchido."""
    return verificar_campos(interpretacao.ficha.model_dump())


def resposta_da_leitura(interpretacao: Interpretacao, texto: str) -> dict[str, Any]:
    api = interpretacao.para_api()
    if tem_tentativa_de_injecao(texto):
        api["warnings"] = [*api["warnings"], AVISO_DE_INJECAO]
    reprovacao = bloqueio(interpretacao)
    return {
        "status": "done",
        "detected_type": interpretacao.tipo,
        "result": api,
        "blocked": reprovacao.para_api() if reprovacao else None,
    }
