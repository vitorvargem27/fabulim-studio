"""Onde cada personagem fica na cena (posição, tamanho, lado para onde olha) e qual pose usar."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from ..prompts.parser import normalizar

FORMATOS = ("16:9", "9:16")
ENQUADRAMENTOS = ("aberto", "medio", "proximo")
ALTURA_16_9 = {1: 0.58, 2: 0.52, 3: 0.44}  # fração da altura do quadro; 4 ou mais: 0.38
ALTURA_9_16 = {1: 0.40, 2: 0.30, 3: 0.24}
FATOR_DO_ENQUADRAMENTO = {"aberto": 0.82, "medio": 1.0, "proximo": 1.22}
POSICOES = {
    1: (0.5,),
    2: (0.32, 0.68),
    3: (0.22, 0.5, 0.78),
    4: (0.16, 0.39, 0.61, 0.84),
}
BASE_Y = {"16:9": 0.92, "9:16": 0.88}
EMOCAO_PARA_POSE = {"feliz": "feliz", "triste": "triste", "surpreso": "surpreso", "sono": "sono", "bravo": "bravo"}


@dataclass
class ItemDeLayout:
    personagem_id: str
    x: float
    base_y: float
    altura: float
    espelhar: bool = False
    pose: str | None = None  # None: a pose é escolhida pela emoção e pela ação
    acao: str | None = None  # None: a ação é escolhida pelo texto da cena
    entrada: str | None = None

    def para_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def de_dict(dados: dict[str, Any]) -> ItemDeLayout:
        return ItemDeLayout(
            personagem_id=str(dados["personagem_id"]),
            x=min(max(float(dados.get("x", 0.5)), 0.0), 1.0),
            base_y=min(max(float(dados.get("base_y", 0.9)), 0.3), 1.05),
            altura=min(max(float(dados.get("altura", 0.5)), 0.08), 1.2),
            espelhar=bool(dados.get("espelhar", False)),
            pose=dados.get("pose") or None,
            acao=dados.get("acao") or None,
            entrada=dados.get("entrada") or None,
        )


def _posicoes(n: int) -> tuple[float, ...]:
    if n in POSICOES:
        return POSICOES[n]
    passo = 0.76 / max(n - 1, 1)
    return tuple(round(0.12 + passo * i, 3) for i in range(n))


def altura_do_personagem(n: int, formato: str, enquadramento: str) -> float:
    tabela = ALTURA_9_16 if formato == "9:16" else ALTURA_16_9
    base = tabela.get(n, 0.2 if formato == "9:16" else 0.38)
    return min(base * FATOR_DO_ENQUADRAMENTO.get(enquadramento, 1.0), 0.9)


def compor_layout(personagem_ids: list[str], formato: str, enquadramento: str = "medio") -> list[ItemDeLayout]:
    """Distribui os personagens lado a lado; quem fica do lado direito olha para o centro."""
    n = len(personagem_ids)
    if n == 0:
        return []
    altura = altura_do_personagem(n, formato, enquadramento)
    formato = formato if formato in FORMATOS else "16:9"
    return [
        ItemDeLayout(pid, x, BASE_Y[formato], altura, espelhar=n > 1 and x > 0.55)
        for pid, x in zip(personagem_ids, _posicoes(n), strict=True)
    ]


def escolher_pose(disponiveis: set[str], emocao: str, acao: str) -> str:
    """A pose (recorte) que combina com o momento: expressão da emoção, de lado para andar e pular, senão de frente."""
    pedida = EMOCAO_PARA_POSE.get(emocao)
    if pedida and pedida in disponiveis:
        return pedida
    if acao in ("andar", "pular", "dancar"):
        for lado in ("lado", "tres_quartos"):
            if lado in disponiveis:
                return lado
    for padrao in ("frente", "principal", "tres_quartos", "lado"):
        if padrao in disponiveis:
            return padrao
    return sorted(disponiveis)[0] if disponiveis else "principal"


# Padrões (começo de palavra, sem acento) do que uma cena diz que o personagem faz. A ordem manda: quem "vai dormir" dorme.
PADROES_DE_ACAO = (
    ("dormir", re.compile(r"\b(dorm\w*|sono\b|sonec\w*|ninar|ronc\w*)")),
    ("pular", re.compile(r"\b(pul[aeoi]\w*|salt\w*|quic\w*)")),
    ("dancar", re.compile(r"\b(danc\w*|sambar|rebol\w*|bailar|bailo)")),
    (
        "andar",
        re.compile(
            r"\b(and[aeoi]\w*|camin\w*|corr[aeoi]\w*|passe[ai]\w*|cheg\w*|vai\b|vao\b|segue\w*|seguir|explor\w*)"
        ),
    ),
    ("flutuar", re.compile(r"\b(voa\w*|voar|voando|flut\w*)")),
    ("saudar", re.compile(r"\b(acen\w*|cumpriment\w*|ola\b|oi\b|tchau|salud\w*)")),
    ("tremer", re.compile(r"\b(trem[aeoi]\w*|empolg\w*)")),
    ("balancar", re.compile(r"\b(cant[aeoi]\w*|balanc\w*|embal\w*|sorri[aeoi]\w*)")),
)
PADROES_DE_EFEITO = (
    ("chuva", re.compile(r"\b(chuv\w*|chov\w*|gotas?\b|goteir\w*)")),
    ("brilhos", re.compile(r"\b(estrel\w*|magi[ac]\w*|brilh\w*|encant\w*|fada\w*|surpres\w*)")),
)


def acao_do_texto(texto: str) -> str:
    """A ação de animação que combina com o que a cena diz que o personagem faz (palavras-chave; padrão: respirar)."""
    n = normalizar(texto)
    for acao, padrao in PADROES_DE_ACAO:
        if padrao.search(n):
            return acao
    return "respirar"


def efeitos_do_texto(texto: str) -> tuple[str, ...]:
    n = normalizar(texto)
    return tuple(efeito for efeito, padrao in PADROES_DE_EFEITO if padrao.search(n))
