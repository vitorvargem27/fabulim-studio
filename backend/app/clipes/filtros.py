"""Filtros e argumentos do ffmpeg para reenquadrar, normalizar e unir clipes. Funções puras: recebem tamanhos e devolvem texto."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..projetos.montagem import CODEC_DE_AUDIO, CODEC_DE_VIDEO, TRANSICOES, filtro_de_volume

PRESETS_DE_TAMANHO = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "720p": (1280, 720),
}
FPS_DA_UNIAO = 24
TAXA_DE_AUDIO = 44_100


def tamanho_do_preset(preset: str, origem: tuple[int, int] | None = None) -> tuple[int, int]:
    """O tamanho de saída de um preset. «720p» mantém o formato do vídeo (720 de altura no horizontal; 720 de largura no vertical)."""
    if preset == "720p" and origem:
        largura, altura = origem
        if altura >= largura:  # vertical ou quadrado: 720 de largura
            return 720, max(2, round(720 * altura / largura / 2) * 2)
        return max(2, round(720 * largura / altura / 2) * 2), 720
    return PRESETS_DE_TAMANHO[preset]


def filtro_de_reenquadrar(
    largura: int, altura: int, modo: str = "fit", foco_x: float = 0.5, fps: int = FPS_DA_UNIAO
) -> str:
    """Leva o vídeo para ``largura``×``altura``. ``fit``: o vídeo inteiro sobre um fundo desfocado do próprio vídeo (nada é cortado).
    ``crop``: preenche o quadro cortando, centrado no ``foco_x`` (0 = borda esquerda, 1 = direita)."""
    if modo == "crop":
        x = f"max(0,min(iw-{largura},iw*{foco_x:.3f}-{largura}/2))"
        return (
            f"[0:v]scale={largura}:{altura}:force_original_aspect_ratio=increase,crop={largura}:{altura}:x='{x}':y='(ih-{altura})/2',"
            f"fps={fps},setsar=1,format=yuv420p[saida]"
        )
    raio = max(4, min(largura, altura) // 40)
    return (
        f"[0:v]split=2[fundo][frente];"
        f"[fundo]scale={largura}:{altura}:force_original_aspect_ratio=increase,crop={largura}:{altura},"
        f"boxblur=luma_radius={raio}:luma_power=2[desfocado];"
        f"[frente]scale={largura}:{altura}:force_original_aspect_ratio=decrease[inteiro];"
        f"[desfocado][inteiro]overlay=(W-w)/2:(H-h)/2,fps={fps},setsar=1,format=yuv420p[saida]"
    )


def argumentos_de_reenquadrar(
    origem: Path,
    saida: Path,
    largura: int,
    altura: int,
    *,
    modo: str = "fit",
    foco_x: float = 0.5,
    tem_audio: bool = True,
) -> list[str | Path]:
    args: list[str | Path] = [
        "-i",
        origem.resolve(),
        "-filter_complex",
        filtro_de_reenquadrar(largura, altura, modo, foco_x),
        "-map",
        "[saida]",
    ]
    if tem_audio:
        args += ["-map", "0:a:0"]
    return [
        *args,
        *CODEC_DE_VIDEO,
        *(CODEC_DE_AUDIO if tem_audio else ["-an"]),
        "-movflags",
        "+faststart",
        saida.resolve(),
    ]


def argumentos_de_normalizacao(
    origem: Path, saida: Path, largura: int, altura: int, *, tem_audio: bool, duracao_s: float, foco_x: float = 0.5
) -> list[str | Path]:
    """Deixa o clipe no formato comum da união (tamanho, quadros por segundo, áudio estéreo 44,1 kHz; sem áudio ganha silêncio)."""
    filtro = filtro_de_reenquadrar(largura, altura, "fit", foco_x)
    if tem_audio:
        return [
            "-i",
            origem.resolve(),
            "-filter_complex",
            f"{filtro};[0:a]aresample={TAXA_DE_AUDIO},aformat=channel_layouts=stereo[audio]",
            "-map",
            "[saida]",
            "-map",
            "[audio]",
            *CODEC_DE_VIDEO,
            *CODEC_DE_AUDIO,
            "-movflags",
            "+faststart",
            saida.resolve(),
        ]
    return [
        "-i",
        origem.resolve(),
        "-f",
        "lavfi",
        "-t",
        f"{duracao_s:.3f}",
        "-i",
        f"anullsrc=r={TAXA_DE_AUDIO}:cl=stereo",
        "-filter_complex",
        filtro,
        "-map",
        "[saida]",
        "-map",
        "1:a:0",
        *CODEC_DE_VIDEO,
        *CODEC_DE_AUDIO,
        "-shortest",
        "-movflags",
        "+faststart",
        saida.resolve(),
    ]


def filtro_de_uniao_com_transicao(duracoes: list[float], nome: str, sobreposicao: float, filtro_do_volume: str) -> str:
    """Video (xfade) e áudio (acrossfade) encadeados; a saída é ``[saida]`` e ``[audio]``, com o volume normalizado."""
    if len(duracoes) == 1:
        return f"[0:v]null[saida];[0:a]{filtro_do_volume}[audio]"
    partes: list[str] = []
    video, audio = "[0:v]", "[0:a]"
    acumulado = duracoes[0]
    for i in range(1, len(duracoes)):
        ultimo = i == len(duracoes) - 1
        rotulo_v = "[saida]" if ultimo else f"[v{i}]"
        rotulo_a = "[audio_cru]" if ultimo else f"[a{i}]"
        partes.append(
            f"{video}[{i}:v]xfade=transition={nome}:duration={sobreposicao:g}:offset={acumulado - sobreposicao:.3f}{rotulo_v}"
        )
        partes.append(f"{audio}[{i}:a]acrossfade=d={sobreposicao:g}{rotulo_a}")
        video, audio = rotulo_v, rotulo_a
        acumulado += duracoes[i] - sobreposicao
    partes.append(f"[audio_cru]{filtro_do_volume}[audio]")
    return ";".join(partes)


def argumentos_de_uniao_com_transicao(
    clipes: list[Path], duracoes: list[float], transicao: str, saida: Path, medida: dict[str, Any] | None
) -> list[str | Path]:
    nome, sobreposicao = TRANSICOES[transicao]
    entradas: list[str | Path] = []
    for clipe in clipes:
        entradas += ["-i", clipe.resolve()]
    return [
        *entradas,
        "-filter_complex",
        filtro_de_uniao_com_transicao(duracoes, nome, sobreposicao, filtro_de_volume(medida)),
        "-map",
        "[saida]",
        "-map",
        "[audio]",
        *CODEC_DE_VIDEO,
        *CODEC_DE_AUDIO,
        "-movflags",
        "+faststart",
        saida.resolve(),
    ]


def argumentos_de_uniao_em_corte(lista: Path, saida: Path, medida: dict[str, Any] | None) -> list[str | Path]:
    """Clipes já normalizados emendados sem transição: o vídeo é copiado e só o áudio é ajustado (volume) e codificado."""
    return [
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        lista.resolve(),
        "-c:v",
        "copy",
        "-af",
        filtro_de_volume(medida),
        *CODEC_DE_AUDIO,
        "-movflags",
        "+faststart",
        saida.resolve(),
    ]
