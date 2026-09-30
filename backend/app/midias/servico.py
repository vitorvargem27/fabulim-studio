"""Guardar uma mídia na biblioteca e avisar a interface (evento ``media.created``), num passo só."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .repositorio import Midia

if TYPE_CHECKING:
    from ..container import Servicos


def adotar_e_avisar(sv: Servicos, origem: Path, **campos: Any) -> Midia:
    midia = sv.midias.adotar(origem, **campos)
    sv.bus.publicar("media.created", midia.para_api())
    return midia


def remover_e_avisar(sv: Servicos, id_: str) -> bool:
    removida = sv.midias.remover(id_)
    if removida:
        sv.bus.publicar("media.deleted", {"id": id_})
    return removida
