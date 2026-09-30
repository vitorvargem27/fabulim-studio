"""Movimentos dos personagens: presets de repouso, de ação e de entrada, todos funções puras do tempo.

Uma ``Transformacao`` diz como o personagem está num instante: deslocamento (em alturas do personagem e em larguras do
quadro), escala em x e y (squash and stretch), rotação em torno dos pés e transparência. Os movimentos se combinam:
repouso ou ação + entrada + pulso da fala.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Transformacao:
    dx: float = 0.0  # em alturas do personagem (+ direita)
    dy: float = 0.0  # em alturas do personagem (+ para baixo)
    dxf: float = 0.0  # em larguras do quadro (caminhadas atravessam a cena)
    sx: float = 1.0
    sy: float = 1.0
    rot: float = 0.0  # graus, sentido anti-horário, em torno dos pés
    alfa: float = 1.0


def ease_out_cubic(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 3


def ease_in_out(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return p * p * (3 - 2 * p)


def ease_out_back(p: float) -> float:
    """Passa um pouco do ponto final e volta (a entrada "com molinha" de desenho animado)."""
    p = min(max(p, 0.0), 1.0)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


def _onda(t: float, periodo: float, fase: float = 0.0) -> float:
    return math.sin(2 * math.pi * (t / periodo + fase))


# --- repouso e ações (repetem enquanto a cena dura) -------------------------------------------------------------------
Movimento = Callable[[float, float, float], Transformacao]  # (t, duração da cena, fase do personagem) → transformação


def respirar(t: float, dur: float, fase: float) -> Transformacao:
    o = _onda(t, 2.6, fase)
    return Transformacao(sx=1 - 0.012 * o, sy=1 + 0.02 * o)


def dormir(t: float, dur: float, fase: float) -> Transformacao:
    o = _onda(t, 3.8, fase)
    return Transformacao(sx=1 - 0.018 * o, sy=1 + 0.03 * o, rot=-2.0)


def balancar(t: float, dur: float, fase: float) -> Transformacao:
    return Transformacao(rot=4.0 * _onda(t, 1.5, fase), sy=1 + 0.008 * _onda(t, 0.75, fase))


def flutuar(t: float, dur: float, fase: float) -> Transformacao:
    return Transformacao(dy=-0.04 * _onda(t, 2.4, fase), rot=2.0 * _onda(t, 3.1, fase))


def tremer(t: float, dur: float, fase: float) -> Transformacao:
    return Transformacao(rot=2.5 * _onda(t, 0.16, fase), dy=-0.006 * abs(_onda(t, 0.16, fase)))


def pular(t: float, dur: float, fase: float) -> Transformacao:
    """Saltos repetidos: agacha antes de sair do chão, estica no ar e amassa ao pousar."""
    periodo = 1.1
    u = ((t / periodo) + fase) % 1.0
    if u < 0.14:  # agachando para o salto
        k = u / 0.14
        return Transformacao(sy=1 - 0.10 * math.sin(math.pi * k), sx=1 + 0.08 * math.sin(math.pi * k))
    ar = (u - 0.14) / 0.72
    if ar <= 1.0:  # no ar
        return Transformacao(
            dy=-0.22 * 4 * ar * (1 - ar), sy=1 + 0.06 * math.sin(math.pi * ar), sx=1 - 0.04 * math.sin(math.pi * ar)
        )
    k = (u - 0.86) / 0.14  # pousando
    return Transformacao(sy=1 - 0.10 * math.sin(math.pi * k), sx=1 + 0.08 * math.sin(math.pi * k))


def dancar(t: float, dur: float, fase: float) -> Transformacao:
    o = _onda(t, 1.2, fase)
    quique = abs(_onda(t, 1.2, fase + 0.25))
    return Transformacao(rot=6.0 * o, dy=-0.05 * quique, sy=1 + 0.03 * (1 - quique), sx=1 - 0.02 * (1 - quique))


def andar(t: float, dur: float, fase: float) -> Transformacao:
    """Atravessa a cena de um lado ao outro, com o balanço dos passos."""
    p = t / max(dur, 0.1)
    passo = abs(_onda(t, 0.9, 0.0))
    return Transformacao(dxf=-0.18 + 0.36 * p, dy=-0.03 * passo, rot=2.5 * _onda(t, 0.9, 0.0), sy=1 + 0.012 * passo)


def saudar(t: float, dur: float, fase: float) -> Transformacao:
    """Acena no começo da cena e depois só respira."""
    if t < 1.8:
        return Transformacao(rot=8.0 * _onda(t, 0.5, fase) * (1 - t / 1.8), sy=1 + 0.01 * _onda(t, 0.5, fase))
    return respirar(t, dur, fase)


ACOES: dict[str, Movimento] = {
    "respirar": respirar,
    "dormir": dormir,
    "balancar": balancar,
    "flutuar": flutuar,
    "tremer": tremer,
    "pular": pular,
    "dancar": dancar,
    "andar": andar,
    "saudar": saudar,
}
DESCRICAO_DAS_ACOES = {
    "respirar": "Parado, respirando",
    "dormir": "Dormindo",
    "balancar": "Balançando",
    "flutuar": "Flutuando",
    "tremer": "Tremendo de empolgação",
    "pular": "Pulando",
    "dancar": "Dançando",
    "andar": "Andando pela cena",
    "saudar": "Acenando",
}


# --- entradas (só nos primeiros instantes) -----------------------------------------------------------------------------
DURACAO_DA_ENTRADA = 0.7


def _entrada(nome: str, t: float) -> Transformacao:
    p = t / DURACAO_DA_ENTRADA
    if nome == "deslizar_esq":
        return Transformacao(dxf=-0.7 * (1 - ease_out_cubic(p)))
    if nome == "deslizar_dir":
        return Transformacao(dxf=0.7 * (1 - ease_out_cubic(p)))
    if nome == "pular_entrada":
        return Transformacao(dxf=-0.35 * (1 - ease_out_cubic(p)), dy=-0.35 * 4 * p * (1 - p) * (1 - p * 0.3))
    if nome == "crescer":
        e = ease_out_back(p)
        return Transformacao(sx=0.3 + 0.7 * e, sy=0.3 + 0.7 * e, alfa=min(1.0, p * 2.5))
    if nome == "aparecer":
        return Transformacao(alfa=ease_in_out(min(1.0, p * 1.4)))
    return Transformacao()


ENTRADAS = ("nenhuma", "deslizar_esq", "deslizar_dir", "pular_entrada", "crescer", "aparecer")


def pulso_da_fala(transformacao: Transformacao, volume: float) -> Transformacao:
    """Enquanto o personagem fala, o corpo pulsa no ritmo da voz (volume de 0 a 1): a "boca" de quem não tem boca animada."""
    v = min(max(volume, 0.0), 1.0)
    return replace(
        transformacao,
        sy=transformacao.sy * (1 + 0.05 * v),
        sx=transformacao.sx * (1 - 0.028 * v),
        dy=transformacao.dy - 0.012 * v,
    )


def combinar(a: Transformacao, b: Transformacao) -> Transformacao:
    return Transformacao(
        dx=a.dx + b.dx,
        dy=a.dy + b.dy,
        dxf=a.dxf + b.dxf,
        sx=a.sx * b.sx,
        sy=a.sy * b.sy,
        rot=a.rot + b.rot,
        alfa=a.alfa * b.alfa,
    )


def transformacao_em(
    acao: str, entrada: str, t: float, duracao: float, fase: float, volume: float = 0.0
) -> Transformacao:
    """Como o personagem está no instante ``t`` da cena: ação + entrada + pulso da fala."""
    movimento = ACOES.get(acao, respirar)
    atual = movimento(t, duracao, fase)
    if entrada != "nenhuma" and t < DURACAO_DA_ENTRADA:
        atual = combinar(atual, _entrada(entrada, t))
    if volume > 0:
        atual = pulso_da_fala(atual, volume)
    return atual
