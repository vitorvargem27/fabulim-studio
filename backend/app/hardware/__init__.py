"""Detecção e classificação de hardware (briefing, seção 2)."""

from .perfil import (
    Classificacao,
    HardwareInvalido,
    Pendencia,
    classificar,
    estimar_gfx_amd,
    ferramentas_pendentes,
    inferir_tipo_gpu,
    normalizar_hardware,
    python_do_projeto,
    validar_hardware,
)
from .relatorio import renderizar_ambiente

__all__ = [
    "Classificacao",
    "HardwareInvalido",
    "Pendencia",
    "classificar",
    "estimar_gfx_amd",
    "ferramentas_pendentes",
    "inferir_tipo_gpu",
    "normalizar_hardware",
    "python_do_projeto",
    "renderizar_ambiente",
    "validar_hardware",
]
