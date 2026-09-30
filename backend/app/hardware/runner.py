"""Monta o comando do diagnóstico (scripts/diagnostico.ps1 ou .sh). Sempre lista de argumentos, nunca shell."""

from __future__ import annotations

import shutil
import sys

from ..config import Settings


class DiagnosticoIndisponivel(RuntimeError):
    """Não há como rodar o coletor nesta máquina (interpretador ausente)."""


def comando_diagnostico(settings: Settings, *, leve: bool, plataforma: str | None = None) -> list[str]:
    """Comando que grava ``hardware.json`` (a classificação é feita depois, em Python)."""
    sistema = plataforma or sys.platform
    saida = str(settings.hardware_json)
    if sistema == "win32":
        shell = shutil.which("powershell") or shutil.which("pwsh")
        if not shell:
            raise DiagnosticoIndisponivel("PowerShell não encontrado para rodar o diagnóstico")
        cmd = [
            shell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(settings.scripts_dir / "diagnostico.ps1"),
            "-Saida",
            saida,
            "-SemPerfil",
            "-Silencioso",
        ]
        return cmd + (["-Leve"] if leve else [])
    bash = shutil.which("bash")
    if not bash:
        raise DiagnosticoIndisponivel("bash não encontrado para rodar o diagnóstico")
    cmd = [bash, str(settings.scripts_dir / "diagnostico.sh"), "--saida", saida, "--sem-perfil", "--silencioso"]
    return cmd + (["--leve"] if leve else [])
