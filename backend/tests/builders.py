"""Construtores de hardware.json simulados para os testes (perfis A, B, C, D em Windows, Linux e macOS)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"


def gpu(
    vendor: str,
    name: str,
    *,
    dedicated_mb: int | None = None,
    shared_mb: int | None = None,
    kind: str | None = None,
    driver: str = "1.0",
    gfx_arch: str | None = None,
) -> dict[str, Any]:
    return {
        "vendor": vendor,
        "name": name,
        "kind": kind,
        "dedicated_mb": dedicated_mb,
        "shared_mb": shared_mb,
        "driver": driver,
        "driver_date": None,
        "driver_model": None,
        "d3d12_ml": None,
        "pci_id": None,
        "gfx_arch": gfx_arch,
        "gfx_arch_source": None,
    }


def aceleracao(
    *, cuda: bool = False, rocm: bool = False, directml: bool = False, vulkan: bool = False, metal: bool = False
) -> dict[str, Any]:
    def item(ok: bool) -> dict[str, Any]:
        return {"available": ok, "detail": None, "version": None}

    return {
        "cuda": item(cuda),
        "rocm": item(rocm),
        "directml": item(directml),
        "vulkan": {"available": vulkan, "api_version": "1.3" if vulkan else None, "devices": []},
        "metal": item(metal),
        "openvino": {"available": False, "candidate": False, "version": None},
    }


def ferramentas(**substituicoes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "python": {"installed": True, "version": "3.12.4", "path": "/usr/bin/python3", "versions_available": ["3.12"]},
        "node": {"installed": True, "version": "22.18.0", "path": "/usr/bin/node"},
        "npm": {"installed": True, "version": "11.0.0", "path": "/usr/bin/npm"},
        "git": {"installed": True, "version": "2.46.0", "path": "/usr/bin/git"},
        "ffmpeg": {"installed": True, "version": "7.1", "path": "/usr/bin/ffmpeg", "encoders": ["libx264"]},
        "ollama": {
            "installed": True,
            "version": "0.33.3",
            "path": "/usr/bin/ollama",
            "server_active": True,
            "host": "127.0.0.1:11434",
            "models": [],
            "loaded": [],
            "gpu_discovery": [],
            "igpu_dropped": False,
        },
        "claude_code": {
            "installed": True,
            "version": "2.1.284",
            "path": "/usr/bin/claude",
            "source": "path",
            "logged_in": True,
            "auth_method": "claude.ai",
            "subscription": "pro",
        },
    }
    base.update(substituicoes)
    return base


def hw(
    *,
    familia: str = "windows",
    arch: str = "x64",
    ram_mb: int = 32_475,
    livre_gb: float = 200.0,
    laptop: bool = False,
    gpus: list[dict[str, Any]] | None = None,
    accel: dict[str, Any] | None = None,
    cpu_modelo: str = "CPU de teste",
    avx512: bool = False,
    na_tomada: bool | None = True,
    plano: str = "Equilibrado",
    npu: str | None = None,
    tools: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Hardware.json completo e válido; cada teste sobrescreve só o que importa."""
    return {
        "schema_version": 1,
        "collected_at": "2026-09-28T12:00:00-03:00",
        "full_collected_at": "2026-09-28T12:00:00-03:00",
        "mode": "full",
        "os": {"family": familia, "name": familia.capitalize(), "version": "1", "build": None, "arch": arch},
        "system": {
            "vendor": "Teste",
            "model": "Modelo",
            "marketing_name": None,
            "is_laptop": laptop,
            "battery": {"present": laptop, "percent": 80 if laptop else None, "on_ac": na_tomada if laptop else None},
            "power_plan": plano,
            "power_plan_guid": None,
        },
        "cpu": {
            "model": cpu_modelo,
            "cores": 8,
            "threads": 16,
            "max_mhz": 4000,
            "features": {"avx": True, "avx2": True, "avx512": avx512, "sse42": True, "neon": arch == "arm64"},
            "npu": {"present": npu is not None, "name": npu},
        },
        "memory": {"ram_total_mb": ram_mb, "ram_free_mb": ram_mb // 2},
        "disk": {
            "path": "/projeto",
            "drive": "/",
            "total_mb": int((livre_gb + 100) * 1024),
            "free_mb": int(livre_gb * 1024),
            "kind": "SSD",
        },
        "gpus": gpus if gpus is not None else [],
        "acceleration": accel if accel is not None else aceleracao(),
        "tools": tools if tools is not None else ferramentas(),
        "fingerprint": "0123456789abcdef",
        "changed_since_last_run": False,
    }


def carregar_thinkpad() -> dict[str, Any]:
    """Coleta real (higienizada) do ThinkPad T14 Gen 2i, a máquina de referência do projeto."""
    caminho = FIXTURES / "thinkpad_t14_gen2i.json"
    data: dict[str, Any] = json.loads(caminho.read_text(encoding="utf-8"))
    return data
