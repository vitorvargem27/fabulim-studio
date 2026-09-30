"""Efeitos de cena desenhados por código: brilhos que cintilam e chuva leve. Nada pisca rápido (segurança contra flashes)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PIL import Image, ImageDraw

EFEITOS = ("brilhos", "chuva")
COR_BRILHO = (255, 236, 150)
COR_CHUVA = (170, 200, 235)


@dataclass(frozen=True)
class Brilho:
    x: float
    y: float
    tamanho: float  # fração da largura do quadro
    fase: float
    periodo: float


def brilhos_da_cena(semente: int, quantidade: int = 14) -> list[Brilho]:
    acaso = random.Random(semente * 7919 + 13)
    return [
        Brilho(
            acaso.uniform(0.05, 0.95),
            acaso.uniform(0.06, 0.7),
            acaso.uniform(0.008, 0.02),
            acaso.random(),
            acaso.uniform(2.2, 4.0),
        )
        for _ in range(quantidade)
    ]


def desenhar_brilhos(quadro: Image.Image, brilhos: list[Brilho], t: float) -> None:
    """Estrelas de quatro pontas que crescem e diminuem devagar (períodos de 2 a 4 s: bem abaixo do limite de flashes)."""
    largura, altura = quadro.size
    desenho = ImageDraw.Draw(quadro)
    for b in brilhos:
        pulso = 0.5 + 0.5 * math.sin(2 * math.pi * (t / b.periodo + b.fase))
        raio = b.tamanho * largura * (0.25 + 0.75 * pulso)
        if raio < 1.0:
            continue
        cx, cy = b.x * largura, b.y * altura
        fino = raio * 0.28
        desenho.polygon(
            [
                (cx, cy - raio),
                (cx + fino, cy - fino),
                (cx + raio, cy),
                (cx + fino, cy + fino),
                (cx, cy + raio),
                (cx - fino, cy + fino),
                (cx - raio, cy),
                (cx - fino, cy - fino),
            ],
            fill=COR_BRILHO,
        )


def desenhar_chuva(quadro: Image.Image, semente: int, t: float, densidade: int = 70) -> None:
    """Gotas finas caindo na diagonal, em posições que se repetem de forma previsível a cada quadro."""
    largura, altura = quadro.size
    desenho = ImageDraw.Draw(quadro)
    comprimento = altura * 0.045
    for i in range(densidade):
        acaso = random.Random(semente * 104729 + i)
        x0, velocidade, fase = acaso.random(), acaso.uniform(0.7, 1.1), acaso.random()
        progresso = (t * velocidade * 0.9 + fase) % 1.0
        y = progresso * (altura + comprimento) - comprimento
        x = (x0 * largura + progresso * largura * 0.05) % largura
        desenho.line(
            [(x, y), (x - largura * 0.006, y + comprimento)], fill=COR_CHUVA, width=max(1, round(largura / 640))
        )
