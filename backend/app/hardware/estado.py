"""Estado do hardware para a API: lê ``hardware.json``, classifica o perfil e calcula a matriz de capacidades."""

from __future__ import annotations

import json
import sys
import threading
from collections.abc import Callable
from typing import Any

from ..config import Settings
from ..ferramentas.detectar import motores_instalados
from .capacidades import calcular
from .perfil import (
    Classificacao,
    HardwareInvalido,
    classificar,
    ferramentas_pendentes,
    normalizar_hardware,
    obter,
    validar_hardware,
)


def perfil_para_api(c: Classificacao) -> dict[str, Any]:
    return {
        "letter": c.perfil,
        "name": c.nome,
        "reasons": list(c.justificativa),
        "warnings": list(c.avisos),
        "acceleration": list(c.aceleracao),
        "main_gpu": c.gpu_principal,
        "ai_memory_mb": c.memoria_ia_mb,
    }


class HardwareState:
    def __init__(self, settings: Settings, medicoes: Callable[[], dict[str, Any]] | None = None) -> None:
        self._settings = settings
        self._medicoes = medicoes or (lambda: {})
        self._trava = threading.Lock()

    def carregar(self) -> dict[str, Any] | None:
        """Conteúdo do hardware.json, ou ``None`` se ainda não existe ou está ilegível."""
        try:
            texto = self._settings.hardware_json.read_text(encoding="utf-8-sig")
            dados = json.loads(texto)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        return dados if isinstance(dados, dict) else None

    def snapshot(self) -> dict[str, Any]:
        hw = self.carregar()
        if hw is None:
            return {"exists": False, "valid": False, "errors": [], "capabilities": [], "measurements": self._medicoes()}
        erros = validar_hardware(hw)
        if erros:
            return {
                "exists": True,
                "valid": False,
                "errors": erros,
                "capabilities": [],
                "measurements": self._medicoes(),
            }
        try:
            c = classificar(hw)
        except HardwareInvalido as exc:  # defesa: validar_hardware já cobre, mas o dado vem de disco
            return {
                "exists": True,
                "valid": False,
                "errors": exc.erros,
                "capabilities": [],
                "measurements": self._medicoes(),
            }
        medicoes = self._medicoes()
        return {
            "exists": True,
            "valid": True,
            "errors": [],
            "collected_at": hw.get("collected_at"),
            "full_collected_at": hw.get("full_collected_at") or hw.get("collected_at"),
            "mode": hw.get("mode"),
            "changed": bool(hw.get("changed_since_last_run")),
            "profile": perfil_para_api(c),
            "hardware": normalizar_hardware(hw),
            "pending": [
                {"item": p.item, "state": p.estado, "action": p.acao}
                for p in ferramentas_pendentes(hw, sys.version_info[:2])
            ],
            "capabilities": [cap.para_dict() for cap in calcular(hw, c, medicoes, motores_instalados(self._settings))],
            "measurements": medicoes,
        }

    def salvar_capacidades(self) -> bool:
        """Grava ``config/capabilities.json`` (gerado por máquina; fora do git). Devolve False se não há hardware."""
        snap = self.snapshot()
        if not snap.get("valid"):
            return False
        conteudo = {
            "profile": snap["profile"]["letter"],
            "generated_from": snap["collected_at"],
            "capabilities": snap["capabilities"],
        }
        with self._trava:
            self._settings.capabilities_json.parent.mkdir(parents=True, exist_ok=True)
            self._settings.capabilities_json.write_text(
                json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
            )
        return True

    def notebook_na_bateria(self) -> bool:
        hw = self.carregar()
        return bool(hw and obter(hw, "system.is_laptop") and obter(hw, "system.battery.on_ac") is False)
