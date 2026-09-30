"""Um contexto de execução para operações curtas fora da fila (por exemplo, tirar uma miniatura de um vídeo enviado)."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path


class ContextoSincrono:
    """Cumpre o contrato de ``Contexto`` sem job: não há progresso nem cancelamento, só o processo com tempo limite."""

    def progresso(self, fracao: float, mensagem: str | None = None) -> None:
        return None

    def log(self, mensagem: str, nivel: str = "INFO") -> None:
        return None

    def ponto_de_controle(self) -> None:
        return None

    def executar_processo(
        self,
        comando: Sequence[str],
        *,
        timeout: float,
        ao_tick: Callable[[float], None] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            proc = subprocess.run(list(comando), capture_output=True, timeout=timeout, cwd=cwd, check=False)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"o processo passou de {timeout:.0f} s e foi encerrado") from exc
        texto = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
        return subprocess.CompletedProcess(list(comando), proc.returncode, texto, "")
