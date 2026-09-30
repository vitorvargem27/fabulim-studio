"""As interfaces dos motores (briefing, seção 9: adaptadores trocáveis). Trocar um modelo não pode exigir mudança na interface.

Os motores reais (stable-diffusion.cpp, BiRefNet, Kokoro, Ollama, ffmpeg) e os falsos dos testes cumprem estas mesmas
assinaturas; um teste de contrato garante isso.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from .tipos import Contexto, ItemDeVoz, PedidoImagem, ResultadoDeVoz, ResultadoImagem

if TYPE_CHECKING:
    from .ffmpeg import Sonda


class MotorDeImagem(Protocol):
    def indisponivel(self) -> str | None: ...

    def estimativa(self, largura: int, altura: int, com_referencia: bool = False) -> float: ...

    def gerar(
        self, ctx: Contexto, pedido: PedidoImagem, saida: Path, faixa: tuple[float, float] = (0.0, 1.0)
    ) -> ResultadoImagem: ...


class MotorDeRecorte(Protocol):
    def indisponivel(self) -> str | None: ...

    def recortar(
        self, ctx: Contexto, origem: Path, saida: Path, *, caixa: bool = True, faixa: tuple[float, float] = (0.0, 1.0)
    ) -> dict[str, Any]: ...


class MotorDeVoz(Protocol):
    def indisponivel(self) -> str | None: ...

    def falar(
        self, ctx: Contexto, itens: Sequence[ItemDeVoz], faixa: tuple[float, float] = (0.0, 1.0)
    ) -> list[ResultadoDeVoz]: ...


class MotorDeTexto(Protocol):
    def indisponivel(self) -> str | None: ...

    def estruturar(
        self,
        ctx: Contexto,
        *,
        sistema: str,
        dados: str,
        instrucao: str,
        esquema: dict[str, Any],
        num_predict: int = 1500,
        temperatura: float = 0.4,
        faixa: tuple[float, float] = (0.0, 1.0),
        seed: int | None = None,
    ) -> dict[str, Any]: ...


class MotorFfmpeg(Protocol):
    def indisponivel(self) -> str | None: ...

    def exe(self, nome: str = "ffmpeg") -> str: ...

    def rodar(
        self,
        ctx: Contexto,
        argumentos: Sequence[str | Path],
        *,
        timeout: float = 3600,
        ao_tick: Callable[[float], None] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]: ...

    def rodar_com_quadros(
        self,
        ctx: Contexto,
        quadros: Iterable[bytes],
        *,
        largura: int,
        altura: int,
        fps: float,
        total: int,
        saida: Path,
        argumentos_de_saida: Sequence[str | Path] = ...,
        timeout: float = 7200.0,
        ao_progresso: Callable[[float], None] | None = None,
    ) -> None: ...

    def extrair_luminancia(self, video: Path, amostras_por_s: int = 12) -> list[float]: ...

    def sondar(self, arquivo: Path) -> Sonda: ...
