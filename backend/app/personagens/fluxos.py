"""Como um personagem aparece para a interface: o resumo da biblioteca e os detalhes (variações, folha, voz, versões)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..midias.repositorio import Midia
from ..prompts.tecnico import EXPRESSOES, POSES
from .repositorio import Personagem

if TYPE_CHECKING:
    from ..container import Servicos

SLOTS_EM_ORDEM = ("principal", *POSES, *EXPRESSOES)


def _mais_novas_por_slot(midias: list[Midia]) -> dict[str, Midia]:
    """A mídia mais nova de cada pose ou expressão (a lista já vem da mais nova para a mais antiga)."""
    por_slot: dict[str, Midia] = {}
    for midia in midias:
        slot = midia.metadados.get("slot")
        if isinstance(slot, str) and slot not in por_slot:
            por_slot[slot] = midia
    return por_slot


def recortes_por_slot(sv: Servicos, personagem_id: str) -> dict[str, Midia]:
    """Os recortes (PNG transparente) mais novos de cada pose: é o que a animação de cena usa."""
    midias = sv.midias.listar(papeis=("recorte",), dono_tipo="personagem", dono_id=personagem_id, limite=500)
    return _mais_novas_por_slot(midias)


def resumo(sv: Servicos, personagem: Personagem) -> dict[str, Any]:
    api = personagem.para_api()
    recortes = recortes_por_slot(sv, personagem.id)
    api["cutout_slots"] = [slot for slot in SLOTS_EM_ORDEM if slot in recortes]
    api["has_cutout"] = bool(recortes)
    return api


def detalhes(sv: Servicos, personagem: Personagem) -> dict[str, Any]:
    todas = sv.midias.listar(dono_tipo="personagem", dono_id=personagem.id, limite=1000)
    por_papel: dict[str, list[Midia]] = {}
    for midia in todas:
        por_papel.setdefault(midia.papel, []).append(midia)
    poses = _mais_novas_por_slot(por_papel.get("pose", []))
    recortes = _mais_novas_por_slot(por_papel.get("recorte", []))
    principal = personagem.imagem_principal_id
    # a imagem principal também é a pose "principal": o recorte dela leva o slot "principal"
    if principal:
        base = next((m for m in todas if m.id == principal), None)
        if base is not None:
            poses.setdefault("principal", base)
    folha = [
        {
            "slot": slot,
            "image": poses[slot].para_api() if slot in poses else None,
            "cutout": recortes[slot].para_api() if slot in recortes else None,
        }
        for slot in SLOTS_EM_ORDEM
    ]
    versoes: dict[int, int] = {}
    for midia in todas:
        if midia.papel in ("variacao", "pose", "recorte"):
            versao = int(midia.metadados.get("character_version") or 1)
            versoes[versao] = versoes.get(versao, 0) + 1
    api = resumo(sv, personagem)
    api["cutout_slots"] = [slot for slot in SLOTS_EM_ORDEM if slot in recortes]
    return {
        "character": api,
        "variations": [m.para_api() for m in por_papel.get("variacao", [])],
        "uploads": [m.para_api() for m in por_papel.get("upload", [])],
        "sheet": folha,
        "voice_tests": [m.para_api() for m in por_papel.get("voz_teste", [])],
        "versions": [{"version": v, "images": n} for v, n in sorted(versoes.items(), reverse=True)],
    }
