"""Verificações de qualidade antes de exportar (briefing, seção 8): flashes, volume, duração, conteúdo e originalidade."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from ..conteudo.filtro import verificar_campos
from ..motores.interfaces import MotorFfmpeg
from ..prompts.parser import normalizar
from .cenas import DadosDaCena
from .repositorio import Cena, Projeto

AMOSTRAS_POR_SEGUNDO = 12
VARIACAO_DE_UM_FLASH = 0.10  # 10% da faixa de luminância (o critério de segurança para fotossensibilidade)
MAXIMO_DE_FLASHES_POR_SEGUNDO = 3
LIMITE_DE_SEMELHANCA = 0.8
DURACAO_MAXIMA_DO_SHORT_S = 60.0
DURACAO_MAXIMA_DO_LONGO_S = 300.0


@dataclass(frozen=True)
class ResultadoDeFlashes:
    maximo_por_segundo: float
    aprovado: bool
    momento_s: float | None  # onde está o pior trecho

    def para_api(self) -> dict[str, Any]:
        return {
            "max_per_second": self.maximo_por_segundo,
            "passed": self.aprovado,
            "worst_at_s": self.momento_s,
            "limit_per_second": MAXIMO_DE_FLASHES_POR_SEGUNDO,
        }


def contar_flashes(
    luminancia: npt.NDArray[np.float64] | list[float], amostras_por_s: int = AMOSTRAS_POR_SEGUNDO
) -> ResultadoDeFlashes:
    """Os piores "flashes por segundo" de uma série de luminância (0 a 1) medida em ``amostras_por_s`` quadros por segundo.

    Um flash é um par de mudanças de sentidos opostos (claro→escuro→claro) de pelo menos 10% da faixa. Conta as inversões
    de sentido de mudanças relevantes em qualquer janela de 1 segundo; metade delas são os flashes.
    """
    serie = np.asarray(luminancia, dtype=np.float64)
    if len(serie) < 3:
        return ResultadoDeFlashes(0.0, True, None)
    delta = np.diff(serie)
    sentido = np.where(np.abs(delta) >= VARIACAO_DE_UM_FLASH, np.sign(delta), 0)
    inversoes: list[int] = []
    anterior = 0.0
    for i, s in enumerate(sentido):
        if s == 0:
            continue
        if anterior != 0 and s != anterior:
            inversoes.append(i)
        anterior = float(s)
    if not inversoes:
        return ResultadoDeFlashes(0.0, True, None)
    melhor, momento = 0, 0
    for i, inicio in enumerate(inversoes):
        dentro = sum(1 for j in inversoes[i:] if j - inicio < amostras_por_s)
        if dentro > melhor:
            melhor, momento = dentro, inicio
    por_segundo = round(melhor / 2, 1)
    return ResultadoDeFlashes(
        por_segundo, por_segundo <= MAXIMO_DE_FLASHES_POR_SEGUNDO, round(momento / amostras_por_s, 1)
    )


def verificar_flashes(ffmpeg: MotorFfmpeg, video: Any) -> ResultadoDeFlashes:
    """Mede a luminância do vídeo (12 quadros por segundo, em miniatura) e conta os flashes."""
    return contar_flashes(ffmpeg.extrair_luminancia(video, AMOSTRAS_POR_SEGUNDO), AMOSTRAS_POR_SEGUNDO)


# --- semelhança entre enredos (originalidade) -----------------------------------------------------------------------------
def _termos(texto: str) -> Counter[str]:
    return Counter(p for p in re.findall(r"[a-z0-9]{3,}", normalizar(texto)))


def semelhanca(a: str, b: str) -> float:
    """Semelhança (0 a 1) entre dois textos pelo cosseno da frequência de palavras."""
    ta, tb = _termos(a), _termos(b)
    if not ta or not tb:
        return 0.0
    produto = sum(ta[t] * tb[t] for t in ta.keys() & tb.keys())
    norma = math.sqrt(sum(v * v for v in ta.values())) * math.sqrt(sum(v * v for v in tb.values()))
    return produto / norma if norma else 0.0


def texto_do_projeto(projeto: Projeto, cenas: list[Cena]) -> str:
    historia = str(projeto.enredo.get("story") or "")
    return historia + " " + " ".join(str(c.dados.get("narration") or "") for c in cenas)


def mais_parecido(sv: Any, projeto: Projeto) -> tuple[Projeto, float] | None:
    """O outro projeto (que não seja variante deste) mais parecido com este, para avisar quando o enredo é repetido demais."""
    meu = texto_do_projeto(projeto, sv.projetos.cenas(projeto.id))
    melhor: tuple[Projeto, float] | None = None
    for outro in sv.projetos.listar(limite=300):
        if outro.id == projeto.id or outro.origem_id == projeto.id or projeto.origem_id == outro.id:
            continue
        nota = semelhanca(meu, texto_do_projeto(outro, sv.projetos.cenas(outro.id)))
        if melhor is None or nota > melhor[1]:
            melhor = (outro, nota)
    return melhor


# --- checklist ------------------------------------------------------------------------------------------------------------
def _item(id_: str, rotulo: str, estado: str, detalhe: str) -> dict[str, str]:
    return {"id": id_, "label": rotulo, "status": estado, "detail": detalhe}


def checklist(sv: Any, projeto: Projeto) -> list[dict[str, str]]:
    """O checklist de qualidade que roda antes de exportar. ``ok``, ``warning`` (revisar) ou ``error`` (bloqueia)."""
    cenas = sv.projetos.cenas(projeto.id)
    dados = [(c, DadosDaCena.model_validate(c.dados)) for c in cenas]
    itens: list[dict[str, str]] = []
    if not dados:
        return [_item("cenas", "O vídeo tem cenas", "error", "Ainda não há cenas: gere o roteiro.")]
    # 1. conteúdo
    for cena, d in dados:
        textos: dict[str, object] = {
            "title": d.title,
            "visual": d.visual,
            "action": d.action,
            "narration": d.narration,
            "lyrics": d.lyrics,
        }
        textos.update({f"dialogue{i}": f.text for i, f in enumerate(d.dialogue)})
        if r := verificar_campos(textos):
            itens.append(_item("conteudo", "Conteúdo para 2 a 5 anos", "error", f"Cena {cena.ordem}: {r.motivo}"))
            break
    else:
        itens.append(
            _item(
                "conteudo", "Conteúdo para 2 a 5 anos", "ok", "Nenhum trecho de medo, violência, marca ou propaganda."
            )
        )
    # 2. cenas de 3 a 8 s
    fora = [c.ordem for c, d in dados if not 3.0 <= float((d.timeline or {}).get("duration_s", d.duration_s)) <= 8.5]
    itens.append(
        _item("ritmo", "Cenas de 3 a 8 segundos", "warning", f"Fora do ritmo calmo: cenas {', '.join(map(str, fora))}.")
        if fora
        else _item("ritmo", "Cenas de 3 a 8 segundos", "ok", "Todas as cenas têm um ritmo calmo.")
    )
    # 3. sugestões do modelo
    sugestoes = [c.ordem for c, d in dados if d.suggestion and not d.approved.get("roteiro")]
    itens.append(
        _item(
            "sugestoes",
            "Sugestões do modelo revisadas",
            "warning",
            f"Cenas com sugestões ainda não aprovadas: {', '.join(map(str, sugestoes))}.",
        )
        if sugestoes
        else _item("sugestoes", "Sugestões do modelo revisadas", "ok", "Nada pendente de revisão.")
    )
    qualidade = projeto.configuracoes.get("quality") or {}
    # 4. flashes
    flashes = qualidade.get("flashes")
    if flashes is None:
        itens.append(
            _item(
                "flashes", "Sem flashes (máx. 3 por segundo)", "warning", "O vídeo ainda não foi montado para conferir."
            )
        )
    elif flashes.get("passed"):
        itens.append(
            _item(
                "flashes",
                "Sem flashes (máx. 3 por segundo)",
                "ok",
                f"No máximo {flashes.get('max_per_second')} por segundo.",
            )
        )
    else:
        itens.append(
            _item(
                "flashes",
                "Sem flashes (máx. 3 por segundo)",
                "error",
                f"{flashes.get('max_per_second')} flashes por segundo perto de {flashes.get('worst_at_s')} s: reduza os efeitos e as trocas de cena.",
            )
        )
    # 5. volume
    medido = qualidade.get("loudness_input")
    if medido is None:
        itens.append(
            _item("volume", "Volume próximo de -14 LUFS", "warning", "O vídeo ainda não foi montado para medir.")
        )
    else:
        itens.append(
            _item(
                "volume",
                "Volume próximo de -14 LUFS",
                "ok",
                f"Medido em {medido} LUFS antes do ajuste; o vídeo final é ajustado para -14.",
            )
        )
    # 6. duração
    total = float(
        qualidade.get("duration_s") or sum(float((d.timeline or {}).get("duration_s", d.duration_s)) for _, d in dados)
    )
    limite = DURACAO_MAXIMA_DO_SHORT_S if projeto.formato == "short" else DURACAO_MAXIMA_DO_LONGO_S
    itens.append(
        _item(
            "duracao",
            "Duração dentro do formato",
            "warning",
            f"{total:.0f} s passa do limite de {limite:.0f} s para este formato.",
        )
        if total > limite + 0.5
        else _item("duracao", "Duração dentro do formato", "ok", f"{total:.0f} s (limite de {limite:.0f} s).")
    )
    # 7. legendas
    tem_legenda = bool((projeto.configuracoes.get("audio") or {}).get("srt_media_id"))
    itens.append(
        _item("legendas", "Legendas geradas", "ok", "Arquivo SRT junto com o vídeo.")
        if tem_legenda
        else _item("legendas", "Legendas geradas", "warning", "Ainda não há legendas: faça a etapa de áudio.")
    )
    # 8. originalidade
    parecido = mais_parecido(sv, projeto)
    if parecido and parecido[1] >= LIMITE_DE_SEMELHANCA:
        itens.append(
            _item(
                "originalidade",
                "Enredo original",
                "warning",
                f"Muito parecido com «{parecido[0].titulo}» ({parecido[1] * 100:.0f}%): o YouTube desmonetiza conteúdo repetitivo. Varie a história.",
            )
        )
    else:
        itens.append(
            _item(
                "originalidade",
                "Enredo original",
                "ok",
                "Diferente dos seus outros vídeos." if parecido else "Primeiro vídeo do estúdio.",
            )
        )
    itens.append(
        _item(
            "logo",
            "Sem o logo do estúdio no vídeo",
            "ok",
            "O logo do Fabulim nunca entra nos vídeos nem nas miniaturas.",
        )
    )
    itens.append(
        _item(
            "criancas",
            "Marcar como «conteúdo para crianças»",
            "warning",
            "No YouTube, marque o vídeo como conteúdo para crianças ao enviar.",
        )
    )
    return itens
