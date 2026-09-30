"""Câmera de cena: zoom lento e panorâmicas (o "Ken Burns" que dá vida a um cenário parado)."""

from __future__ import annotations

from dataclasses import dataclass

from .presets import ease_in_out

MOVIMENTOS_DE_CAMERA = ("parada", "zoom_in", "zoom_out", "panoramica_esq", "panoramica_dir")
DESCRICAO_DA_CAMERA = {
    "parada": "Câmera parada",
    "zoom_in": "Aproxima devagar",
    "zoom_out": "Afasta devagar",
    "panoramica_esq": "Desliza para a esquerda",
    "panoramica_dir": "Desliza para a direita",
}
ZOOM_MAXIMO = 1.10


@dataclass(frozen=True)
class Camera:
    zoom: float = 1.0
    px: float = 0.0  # deslocamento do centro da janela, em larguras do quadro
    py: float = 0.0  # em alturas do quadro


def folga(zoom: float) -> float:
    """O quanto o centro da janela pode andar sem sair do cenário (em frações do quadro)."""
    return max(0.0, (1 - 1 / zoom) / 2)


def camera_em(nome: str, t: float, duracao: float) -> Camera:
    p = min(max(t / max(duracao, 0.1), 0.0), 1.0)
    e = ease_in_out(p)
    if nome == "zoom_in":
        return Camera(zoom=1.0 + (ZOOM_MAXIMO - 1.0) * e)
    if nome == "zoom_out":
        return Camera(zoom=ZOOM_MAXIMO - (ZOOM_MAXIMO - 1.0) * e)
    if nome in ("panoramica_esq", "panoramica_dir"):
        zoom = 1.08
        margem = folga(zoom) * 0.95
        sentido = 1 if nome == "panoramica_esq" else -1  # esquerda: a janela sai da direita e vai para a esquerda
        return Camera(zoom=zoom, px=sentido * margem * (1 - 2 * e))
    return Camera()
