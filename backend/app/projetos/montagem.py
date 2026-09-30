"""Montagem final com o ffmpeg: emenda os clipes das cenas (corte seco ou transição), junta o áudio e normaliza o volume.

Funções puras que montam a lista de argumentos (fáceis de testar) e duas que rodam o ffmpeg: medir o volume e emendar.
Todos os caminhos entram por lista de argumentos, nunca por shell.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..motores.interfaces import MotorFfmpeg
from ..motores.tipos import Contexto, MotorFalhou

ALVO_DE_VOLUME = -14.0  # LUFS, o padrão de plataformas como o YouTube
PICO_MAXIMO = -1.5
TRANSICOES = {
    "corte": ("", 0.0),
    "fade": ("fade", 0.5),  # crossfade
    "suave": ("dissolve", 0.9),
}
CODEC_DE_VIDEO = ("-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p")
CODEC_DE_AUDIO = ("-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2")


@dataclass(frozen=True)
class Plano:
    inicios: list[float]  # quando cada cena começa no vídeo final
    duracao_total_s: float
    transicao: str
    sobreposicao_s: float


def plano_de_montagem(duracoes: list[float], transicao: str) -> Plano:
    """Onde cada cena começa. Com transição as cenas se sobrepõem um pouco; sem, uma começa quando a outra acaba."""
    nome, sobreposicao = TRANSICOES.get(transicao, TRANSICOES["corte"])
    inicios: list[float] = []
    cursor = 0.0
    for i, duracao in enumerate(duracoes):
        inicios.append(round(cursor, 3))
        cursor += duracao - (sobreposicao if i < len(duracoes) - 1 else 0.0)
    return Plano(inicios, round(cursor, 3), nome, sobreposicao if len(duracoes) > 1 else 0.0)


def filtro_de_volume(medida: dict[str, Any] | None) -> str:
    """O filtro loudnorm: com a medição da primeira passada aplica o ajuste exato; sem ela, ajusta em uma passada só."""
    base = f"loudnorm=I={ALVO_DE_VOLUME:g}:TP={PICO_MAXIMO:g}:LRA=11"
    if not medida:
        return base
    campos = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    if not all(c in medida for c in campos):
        return base
    return (
        f"{base}:measured_I={medida['input_i']}:measured_TP={medida['input_tp']}:measured_LRA={medida['input_lra']}"
        f":measured_thresh={medida['input_thresh']}:offset={medida['target_offset']}:linear=true"
    )


def ler_medicao(saida_do_ffmpeg: str) -> dict[str, Any] | None:
    """O bloco JSON que o loudnorm imprime ao final da primeira passada."""
    achou = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", saida_do_ffmpeg, flags=re.DOTALL)
    if not achou:
        return None
    try:
        dados = json.loads(achou.group(0))
    except json.JSONDecodeError:
        return None
    return dados if isinstance(dados, dict) else None


def medir_volume(ffmpeg: MotorFfmpeg, ctx: Contexto, audio: Path) -> dict[str, Any] | None:
    """Primeira passada do loudnorm: mede o volume do áudio (LUFS, pico e faixa dinâmica) sem gerar arquivo."""
    proc = ffmpeg.rodar(
        ctx,
        [
            "-loglevel",
            "info",
            "-i",
            audio.resolve(),
            "-af",
            f"{filtro_de_volume(None)}:print_format=json",
            "-f",
            "null",
            "-",
        ],
        timeout=600,
    )
    return ler_medicao(proc.stdout)


def _escapar(caminho: Path) -> str:
    return str(caminho.resolve()).replace("\\", "/").replace("'", "'\\''")


def escrever_lista_de_concatenacao(clipes: list[Path], lista: Path) -> Path:
    lista.parent.mkdir(parents=True, exist_ok=True)
    lista.write_text("".join(f"file '{_escapar(c)}'\n" for c in clipes), encoding="utf-8")
    return lista


def argumentos_de_corte_seco(lista: Path, audio: Path, saida: Path, medida: dict[str, Any] | None) -> list[str | Path]:
    """Cenas emendadas sem transição: o vídeo é copiado (não reencoda) e só o áudio é codificado e normalizado."""
    return [
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        lista.resolve(),
        "-i",
        audio.resolve(),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-af",
        filtro_de_volume(medida),
        *CODEC_DE_AUDIO,
        "-shortest",
        "-movflags",
        "+faststart",
        saida.resolve(),
    ]


def filtro_de_transicoes(duracoes: list[float], nome: str, sobreposicao: float) -> str:
    """A cadeia de xfade que funde cada cena com a próxima. Entradas 0..N-1 são os clipes; a saída é ``[saida]``."""
    if len(duracoes) == 1:
        return "[0:v]null[saida]"
    partes: list[str] = []
    anterior = "[0:v]"
    acumulado = duracoes[0]
    for i in range(1, len(duracoes)):
        rotulo = "[saida]" if i == len(duracoes) - 1 else f"[v{i}]"
        partes.append(
            f"{anterior}[{i}:v]xfade=transition={nome}:duration={sobreposicao:g}:offset={acumulado - sobreposicao:.3f}{rotulo}"
        )
        anterior = rotulo
        acumulado += duracoes[i] - sobreposicao
    return ";".join(partes)


def argumentos_com_transicao(
    clipes: list[Path], duracoes: list[float], transicao: str, audio: Path, saida: Path, medida: dict[str, Any] | None
) -> list[str | Path]:
    nome, sobreposicao = TRANSICOES[transicao]
    entradas: list[str | Path] = []
    for clipe in clipes:
        entradas += ["-i", clipe.resolve()]
    return [
        *entradas,
        "-i",
        audio.resolve(),
        "-filter_complex",
        filtro_de_transicoes(duracoes, nome, sobreposicao),
        "-map",
        "[saida]",
        "-map",
        f"{len(clipes)}:a:0",
        *CODEC_DE_VIDEO,
        "-af",
        filtro_de_volume(medida),
        *CODEC_DE_AUDIO,
        "-shortest",
        "-movflags",
        "+faststart",
        saida.resolve(),
    ]


def montar_video(
    ffmpeg: MotorFfmpeg,
    ctx: Contexto,
    clipes: list[Path],
    duracoes: list[float],
    transicao: str,
    audio: Path,
    saida: Path,
    pasta_temporaria: Path,
    medida: dict[str, Any] | None,
) -> None:
    if not clipes or len(clipes) != len(duracoes):
        raise MotorFalhou("Não há clipes para montar.")
    saida.parent.mkdir(parents=True, exist_ok=True)
    if transicao == "corte" or len(clipes) == 1:
        lista = escrever_lista_de_concatenacao(clipes, pasta_temporaria / f"lista-{saida.stem}.txt")
        try:
            ffmpeg.rodar(ctx, argumentos_de_corte_seco(lista, audio, saida, medida), timeout=3600)
        finally:
            lista.unlink(missing_ok=True)
    else:
        ffmpeg.rodar(ctx, argumentos_com_transicao(clipes, duracoes, transicao, audio, saida, medida), timeout=7200)
