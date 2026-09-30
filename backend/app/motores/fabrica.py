"""Monta os motores reais a partir da configuração e do que foi medido neste computador."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..config import Settings
from ..services.ollama import OllamaClient
from .ffmpeg import Ffmpeg
from .imagem import MotorDeImagemSdCpp
from .interfaces import MotorDeImagem, MotorDeRecorte, MotorDeTexto, MotorDeVoz, MotorFfmpeg
from .recorte import MotorDeRecorteBiRefNet
from .texto import MotorDeTextoOllama
from .voz import MotorDeVozKokoro


@dataclass
class Motores:
    imagem: MotorDeImagem
    recorte: MotorDeRecorte
    voz: MotorDeVoz
    texto: MotorDeTexto
    ffmpeg: MotorFfmpeg

    def motivo(self, *chaves: str) -> str | None:
        """O motivo do primeiro motor pedido que não pode rodar agora (``None`` se todos podem). Só consulta os pedidos."""
        verificadores: dict[str, Callable[[], str | None]] = {
            "image": self.imagem.indisponivel,
            "cutout": self.recorte.indisponivel,
            "voice": self.voz.indisponivel,
            "text": self.texto.indisponivel,
            "ffmpeg": self.ffmpeg.indisponivel,
        }
        for chave in chaves:
            if motivo := verificadores[chave]():
                return motivo
        return None

    def indisponiveis(self) -> dict[str, str]:
        """O que não pode rodar agora, com o motivo em linguagem simples (a interface mostra e desativa o botão)."""
        motivos = {
            "image": self.imagem.indisponivel(),
            "cutout": self.recorte.indisponivel(),
            "voice": self.voz.indisponivel(),
            "text": self.texto.indisponivel(),
            "ffmpeg": self.ffmpeg.indisponivel(),
        }
        return {nome: motivo for nome, motivo in motivos.items() if motivo}


def segundos_por_imagem_512(medicoes: dict[str, Any]) -> float | None:
    """O tempo medido pelo benchmark (para a imagem de teste) convertido para uma imagem de 512 px."""
    segundos = medicoes.get("imagem_seg")
    lado = medicoes.get("imagem_lado") or 512
    if isinstance(segundos, (int, float)) and not isinstance(segundos, bool) and segundos > 0:
        return float(segundos) * (512 * 512) / (float(lado) * float(lado))
    return None


def criar_motores(
    settings: Settings,
    ollama: OllamaClient,
    medicoes: Callable[[], dict[str, Any]],
    usa_vulkan: Callable[[], bool],
) -> Motores:
    return Motores(
        imagem=MotorDeImagemSdCpp(settings, usa_vulkan, lambda: segundos_por_imagem_512(medicoes())),
        recorte=MotorDeRecorteBiRefNet(settings),
        voz=MotorDeVozKokoro(settings),
        texto=MotorDeTextoOllama(ollama),
        ffmpeg=Ffmpeg(settings),
    )
