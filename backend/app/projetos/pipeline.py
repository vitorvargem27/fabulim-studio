"""Peças do pipeline de vídeo: layout da cena, camadas de animação, linha do tempo das falas e impressão digital do clipe."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..animacao.camera import MOVIMENTOS_DE_CAMERA
from ..animacao.envelope import combinar_envelopes, envelope_de_audio
from ..animacao.layout import ItemDeLayout, acao_do_texto, compor_layout, efeitos_do_texto, escolher_pose
from ..animacao.render import CamadaDeRender, CenaDeRender
from ..erros import ErroParaOUsuario
from ..midias.repositorio import Midia
from ..personagens import fluxos
from ..personagens.repositorio import Personagem
from ..prompts.parser import normalizar
from .cenas import DadosDaCena
from .repositorio import Projeto

if TYPE_CHECKING:
    from ..container import Servicos

RESOLUCOES = {
    ("16:9", "rascunho"): (1280, 720),
    ("16:9", "final"): (1920, 1080),
    ("9:16", "rascunho"): (720, 1280),
    ("9:16", "final"): (1080, 1920),
    ("1:1", "rascunho"): (720, 720),
    ("1:1", "final"): (1080, 1080),
}
FPS_PADRAO = 24
ENTRADA_INICIAL = 0.35  # silêncio antes da primeira fala
PAUSA_ENTRE_FALAS = 0.4
FOLGA_NO_FIM = 0.7
ENTRADAS_EM_ROTACAO = ("pular_entrada", "deslizar_esq", "crescer", "deslizar_dir", "aparecer")


def resolucao(proporcao: str, qualidade: str) -> tuple[int, int]:
    return RESOLUCOES[(proporcao, "rascunho" if qualidade == "rascunho" else "final")]


def fps_do_projeto(projeto: Projeto) -> int:
    try:
        return min(max(int(projeto.configuracoes.get("fps", FPS_PADRAO)), 12), 60)
    except (TypeError, ValueError):
        return FPS_PADRAO


def personagens_do_projeto(sv: Servicos, projeto: Projeto) -> list[Personagem]:
    encontrados = [sv.personagens.obter(id_) for id_ in projeto.personagens]
    return [p for p in encontrados if p is not None]


def _sem_nomes(texto: str, personagens: list[Personagem]) -> str:
    """Tira do texto do cenário o nome e a espécie dos personagens: o cenário é gerado sem personagens (eles entram por cima)."""
    limpo = texto
    for p in personagens:
        palavras = {p.nome, str(p.ficha.get("species") or "")}
        for palavra in palavras:
            for parte in [w for w in re.split(r"[\s,/]+", palavra) if len(w) > 2]:
                limpo = re.sub(rf"(?i)\b{re.escape(parte)}\w*", "", limpo)
    return " ".join(limpo.replace(" ,", ",").split())


def descricao_do_cenario(dados: DadosDaCena, personagens: list[Personagem]) -> str:
    """O que vai para o gerador de imagens como descrição do fundo da cena (sem os personagens)."""
    partes = [dados.visual or "", dados.setting if dados.setting and dados.setting not in (dados.visual or "") else ""]
    texto = _sem_nomes(", ".join(p for p in partes if p), personagens)
    return texto or "um cenário alegre e colorido para crianças"


# --- layout e camadas ---------------------------------------------------------------------------------------------------
def layout_da_cena(projeto: Projeto, dados: DadosDaCena) -> list[ItemDeLayout]:
    """O layout salvo na cena (editado pelo usuário) ou o automático; sempre só com personagens que estão na cena."""
    presentes = list(dados.characters)
    if dados.layout:
        itens = [ItemDeLayout.de_dict(i) for i in dados.layout if i.get("personagem_id") in presentes]
        faltam = [pid for pid in presentes if pid not in {i.personagem_id for i in itens}]
        if faltam:
            itens += compor_layout(faltam, projeto.proporcao, dados.framing)
        return itens
    return compor_layout(presentes, projeto.proporcao, dados.framing)


def escolher_recorte(
    sv: Servicos, personagem: Personagem, emocao: str, acao: str, pose: str | None
) -> tuple[str, Midia]:
    recortes = fluxos.recortes_por_slot(sv, personagem.id)
    if not recortes:
        raise ErroParaOUsuario(
            f"«{personagem.nome}» ainda não tem o PNG transparente. Escolha uma variação na página Personagens "
            "(o fundo é recortado ao escolher) ou gere a folha de referência."
        )
    slot = pose if pose in recortes else escolher_pose(set(recortes), emocao, acao)
    return slot, recortes[slot]


def acao_do_personagem(dados: DadosDaCena, item: ItemDeLayout) -> str:
    if item.acao:
        return item.acao
    return acao_do_texto(f"{dados.action} {dados.narration}")


def camadas_da_cena(
    sv: Servicos,
    projeto: Projeto,
    dados: DadosDaCena,
    personagens: dict[str, Personagem],
    fps: int,
    quadros: int,
    falas_por_personagem: dict[str | None, list[tuple[Path, float]]] | None = None,
) -> list[tuple[CamadaDeRender, str, str]]:
    """As camadas de personagem da cena, prontas para o renderizador. Devolve (camada, pose, id do recorte) de cada uma."""
    camadas: list[tuple[CamadaDeRender, str, str]] = []
    for indice, item in enumerate(layout_da_cena(projeto, dados)):
        personagem = personagens.get(item.personagem_id)
        if personagem is None:
            raise ErroParaOUsuario("Um personagem desta cena não existe mais na biblioteca.")
        acao = acao_do_personagem(dados, item)
        pose, recorte = escolher_recorte(sv, personagem, dados.emotion, acao, item.pose)
        envelopes = [
            envelope_de_audio(caminho, fps, quadros, inicio)
            for caminho, inicio in (falas_por_personagem or {}).get(item.personagem_id, [])
        ]
        facing = str(recorte.metadados.get("facing") or "right")
        camada = CamadaDeRender(
            caminho=sv.midias.caminho_absoluto(recorte),
            x=item.x,
            base_y=item.base_y,
            altura=item.altura,
            espelhar=False if facing == "front" else (item.espelhar != (facing == "left")),
            acao=acao,
            entrada=item.entrada or ENTRADAS_EM_ROTACAO[indice % len(ENTRADAS_EM_ROTACAO)],
            fase=round(0.31 * indice, 3),
            envelope=combinar_envelopes(envelopes, quadros) if envelopes else None,
        )
        camadas.append((camada, pose, recorte.id))
    return camadas


def efeitos_da_cena(dados: DadosDaCena) -> tuple[str, ...]:
    return efeitos_do_texto(f"{dados.visual} {dados.action} {dados.narration} {dados.setting}")


def cena_para_render(
    sv: Servicos,
    projeto: Projeto,
    dados: DadosDaCena,
    personagens: dict[str, Personagem],
    duracao_s: float,
    fps: int,
    falas_por_personagem: dict[str | None, list[tuple[Path, float]]] | None = None,
    semente: int = 1,
) -> tuple[CenaDeRender, list[str]]:
    """A cena pronta para desenhar e os ids dos recortes usados (para a impressão digital do clipe)."""
    if dados.background is None:
        raise ErroParaOUsuario("Esta cena ainda não tem cenário. Gere o storyboard primeiro.")
    fundo = sv.midias.obter(dados.background.media_id)
    if fundo is None:
        raise ErroParaOUsuario("O cenário desta cena não está mais na biblioteca. Gere o storyboard de novo.")
    quadros = max(1, round(duracao_s * fps))
    camadas = camadas_da_cena(sv, projeto, dados, personagens, fps, quadros, falas_por_personagem)
    cena = CenaDeRender(
        fundo=sv.midias.caminho_absoluto(fundo),
        duracao_s=duracao_s,
        camadas=[c for c, _, _ in camadas],
        camera=dados.camera if dados.camera in MOVIMENTOS_DE_CAMERA else "parada",
        efeitos=efeitos_da_cena(dados),
        semente=semente,
    )
    return cena, [recorte_id for _, _, recorte_id in camadas]


# --- falas: linha do tempo -----------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class LinhaDoTempo:
    inicios: list[float]
    fins: list[float]
    duracao_s: float


def linha_do_tempo(duracoes_das_falas: list[float], planejada_s: float, fps: int = FPS_PADRAO) -> LinhaDoTempo:
    """Quando cada fala começa e termina na cena; a cena dura o planejado ou o tempo das falas (o que for maior)."""
    inicios: list[float] = []
    fins: list[float] = []
    cursor = ENTRADA_INICIAL
    for duracao in duracoes_das_falas:
        inicios.append(round(cursor, 3))
        cursor += duracao
        fins.append(round(cursor, 3))
        cursor += PAUSA_ENTRE_FALAS
    fim_das_falas = fins[-1] if fins else 0.0
    total = max(planejada_s, fim_das_falas + FOLGA_NO_FIM if fins else planejada_s)
    return LinhaDoTempo(inicios, fins, round(round(total * fps) / fps, 3))


def impressao_digital(*partes: Any) -> str:
    """Um código curto do que entra no clipe: se nada mudou, o clipe pronto ainda vale e não precisa ser desenhado de novo."""
    bruto = json.dumps(partes, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()[:16]


def hash_da_fala(texto: str, voz: dict[str, Any], idioma: str) -> str:
    return impressao_digital(normalizar(texto), voz.get("id"), voz.get("speed"), voz.get("pitch"), idioma)
