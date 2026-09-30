"""O que está instalado de verdade neste computador (arquivos no disco e bibliotecas importáveis)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from ..config import Settings
from ..security.caminhos import dentro_da_pasta
from .catalogo import Item, por_id
from .instalador import Instalador

# motor → itens do catálogo e bibliotecas Python de que ele precisa
MOTORES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "imagem": (("sd-cpp", "flux2-klein-4b", "flux2-vae", "qwen3-4b-texto"), ()),
    "voz": (("kokoro-modelo", "kokoro-vozes"), ("kokoro_onnx", "soundfile", "numpy")),
    "recorte": (("birefnet-lite",), ("onnxruntime", "numpy", "PIL")),
}


def tem_modulo(nome: str) -> bool:
    return importlib.util.find_spec(nome) is not None


def caminho(settings: Settings, item: Item | str) -> Path:
    """Onde o item (já instalado ou não) fica: o arquivo marcador dentro de tools/ ou models/."""
    item = por_id(item) if isinstance(item, str) else item
    base = settings.tools_dir if item.base == "tools" else settings.models_dir
    return dentro_da_pasta(base, item.marcador)


def pendencias(settings: Settings, motor: str) -> tuple[list[str], list[str]]:
    """O que falta para o motor funcionar: (itens do catálogo, bibliotecas Python)."""
    itens, modulos = MOTORES[motor]
    instalador = Instalador(settings)
    itens_faltam = [por_id(i).nome for i in itens if not instalador.instalado(por_id(i))]
    libs_faltam = [f"biblioteca Python {m}" for m in modulos if not tem_modulo(m)]
    return itens_faltam, libs_faltam


def faltando(settings: Settings, motor: str) -> list[str]:
    """Nomes de tudo o que ainda falta para o motor funcionar (itens do catálogo e bibliotecas)."""
    itens_faltam, libs_faltam = pendencias(settings, motor)
    return itens_faltam + libs_faltam


def motores_instalados(settings: Settings) -> set[str]:
    """Motores prontos para uso: ``imagem``, ``voz`` e ``recorte``."""
    return {motor for motor in MOTORES if not faltando(settings, motor)}
