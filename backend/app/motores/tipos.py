"""Tipos compartilhados pelos motores de IA (imagem, recorte, voz, texto, vídeo, música)."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..erros import ErroParaOUsuario


class Contexto(Protocol):
    """O que um motor usa do job em andamento: andamento, log, pausa e cancelamento, e subprocesso cancelável.

    ``JobContext`` (a fila) cumpre isto; os testes usam um contexto simples que só anota as chamadas.
    """

    def progresso(self, fracao: float, mensagem: str | None = None) -> None: ...

    def log(self, mensagem: str, nivel: str = "INFO") -> None: ...

    def ponto_de_controle(self) -> None: ...

    def executar_processo(
        self,
        comando: Sequence[str],
        *,
        timeout: float,
        ao_tick: Callable[[float], None] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]: ...


class MotorIndisponivel(ErroParaOUsuario):
    """O motor não pode rodar agora (não instalado, faltando biblioteca...). A mensagem já diz o que fazer."""


class MotorFalhou(ErroParaOUsuario):
    """O motor rodou e falhou. A mensagem é em português e cabe numa tela de erro."""


@dataclass(frozen=True)
class PedidoImagem:
    prompt: str
    largura: int
    altura: int
    seed: int
    passos: int = 4
    referencias: tuple[Path, ...] = ()  # imagens de referência (consistência de personagem)


@dataclass(frozen=True)
class ResultadoImagem:
    caminho: Path
    segundos: float
    seed: int
    largura: int
    altura: int
    caminho_de_execucao: str  # vulkan | cpu
    modelo: str
    metricas: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ItemDeVoz:
    texto: str
    voz: str
    velocidade: float
    lingua: str
    saida: Path


@dataclass(frozen=True)
class ResultadoDeVoz:
    saida: Path
    duracao_s: float


def dimensoes_da_imagem(formato: str, qualidade: str) -> tuple[int, int]:
    """Largura e altura (múltiplos de 16) para o formato pedido e a qualidade: rascunho, padrão ou alta.

    Os tempos crescem com o número de pixels; a página mostra a estimativa antes de gerar.
    """
    lado = {"rascunho": 512, "padrao": 768, "alta": 1024}[qualidade]
    razoes = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1)}
    a, b = razoes[formato]
    if a == b:
        return lado, lado
    longo = lado if qualidade != "rascunho" else 640
    curto = round(longo * min(a, b) / max(a, b) / 16) * 16
    return (longo, curto) if a > b else (curto, longo)
