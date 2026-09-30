"""ffmpeg e ffprobe: sempre por lista de argumentos (nunca shell), com caminhos absolutos e dentro da pasta do projeto.

Toda a montagem (áudio, vídeo, legendas, emendas) passa por aqui. O ffmpeg roda como processo cancelável da Fila; o ffprobe
(rápido) roda direto, com tempo limite.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np

from ..config import Settings
from ..ferramentas import detectar
from ..ferramentas.catalogo import por_id
from ..ferramentas.instalador import Instalador
from .tipos import Contexto, MotorFalhou, MotorIndisponivel
from .util import final_da_saida

NAO_INSTALADO = "O ffmpeg ainda não está instalado: abra Modelos e clique em «Instalar tudo o que falta»."
ENCODE_PADRAO = (
    "-c:v",
    "libx264",
    "-preset",
    "veryfast",
    "-crf",
    "18",
    "-pix_fmt",
    "yuv420p",
    "-movflags",
    "+faststart",
)


@dataclass(frozen=True)
class Sonda:
    """O que o ffprobe encontrou num arquivo de mídia."""

    formato: str
    duracao_s: float
    largura: int | None
    altura: int | None
    fps: float | None
    codec_de_video: str | None
    codec_de_audio: str | None
    canais: int | None
    taxa_de_audio: int | None
    tamanho_bytes: int

    @property
    def tem_video(self) -> bool:
        return self.codec_de_video is not None

    @property
    def tem_audio(self) -> bool:
        return self.codec_de_audio is not None


def _fps(texto: str | None) -> float | None:
    try:
        valor = float(Fraction(texto or "0"))
    except (ValueError, ZeroDivisionError):
        return None
    return round(valor, 3) if valor > 0 else None


class Ffmpeg:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # --- onde estão os programas -----------------------------------------------------------------------------------
    def _procurar(self, nome: str) -> Path | None:
        item = detectar.caminho(self._settings, "ffmpeg")
        local = item.parent / (nome + item.suffix)
        if local.is_file() and Instalador(self._settings).instalado(por_id("ffmpeg")):
            return local
        achado = shutil.which(nome)  # Linux e macOS: o ffmpeg do sistema
        return Path(achado) if achado else None

    def indisponivel(self) -> str | None:
        return None if self._procurar("ffmpeg") else NAO_INSTALADO

    def exe(self, nome: str = "ffmpeg") -> str:
        caminho = self._procurar(nome)
        if caminho is None:
            raise MotorIndisponivel(NAO_INSTALADO)
        return str(caminho)

    # --- rodar ---------------------------------------------------------------------------------------------------------
    def rodar(
        self,
        ctx: Contexto,
        argumentos: Sequence[str | Path],
        *,
        timeout: float = 3600,
        ao_tick: Callable[[float], None] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Roda o ffmpeg (cancelável). Falha com uma mensagem legível; o registro completo vai para o log do job."""
        comando = [self.exe(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *map(str, argumentos)]
        try:
            proc = ctx.executar_processo(comando, timeout=timeout, ao_tick=ao_tick, cwd=cwd)
        except TimeoutError as exc:
            raise MotorFalhou(f"O ffmpeg não terminou a tempo: {exc}") from exc
        if proc.returncode != 0:
            ctx.log(f"ffmpeg falhou: {final_da_saida(proc.stdout, 8)}", "ERROR")
            raise MotorFalhou(f"A montagem do vídeo falhou: {final_da_saida(proc.stdout, 2)}")
        return proc

    def rodar_com_quadros(
        self,
        ctx: Contexto,
        quadros: Iterable[bytes],
        *,
        largura: int,
        altura: int,
        fps: float,
        total: int,
        saida: Path,
        argumentos_de_saida: Sequence[str | Path] = ENCODE_PADRAO,
        timeout: float = 7200.0,
        ao_progresso: Callable[[float], None] | None = None,
    ) -> None:
        """Codifica um vídeo a partir de quadros crus (RGB) que o app desenha, enviados ao ffmpeg por um pipe.

        Cancelar ou pausar o job vale a cada poucos quadros; se o ffmpeg morrer no meio, o erro dele volta em português.
        """
        saida.parent.mkdir(parents=True, exist_ok=True)
        comando = [
            self.exe(),
            "-hide_banner",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{largura}x{altura}",
            "-framerate",
            f"{fps:g}",
            "-i",
            "-",
            *map(str, argumentos_de_saida),
            str(saida.resolve()),
        ]
        tamanho = largura * altura * 3
        inicio = time.monotonic()
        with tempfile.TemporaryFile() as erros:
            proc = subprocess.Popen(comando, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=erros)
            codigo: int | None = None
            try:
                assert proc.stdin is not None
                try:
                    for indice, quadro in enumerate(quadros):
                        if len(quadro) != tamanho:
                            raise MotorFalhou("Um quadro da animação saiu com tamanho errado.")
                        if indice % 6 == 0:
                            ctx.ponto_de_controle()  # pausar ou cancelar vale no meio da codificação
                            if time.monotonic() - inicio > timeout:
                                raise TimeoutError(f"a codificação passou de {timeout:.0f} s")
                            if ao_progresso:
                                ao_progresso(indice / max(total, 1))
                        proc.stdin.write(quadro)
                    proc.stdin.close()
                except (BrokenPipeError, OSError):
                    pass  # o ffmpeg encerrou antes da hora: o código de saída e o erro dele explicam
                codigo = proc.wait(timeout=900)
            except TimeoutError as exc:
                raise MotorFalhou(f"O ffmpeg não terminou a tempo: {exc}") from exc
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
            erros.seek(0)
            texto = erros.read().decode("utf-8", errors="replace")
        if codigo != 0:
            ctx.log(f"ffmpeg falhou: {final_da_saida(texto, 8)}", "ERROR")
            raise MotorFalhou(f"A montagem do vídeo falhou: {final_da_saida(texto, 2)}")

    def extrair_luminancia(self, video: Path, amostras_por_s: int = 12) -> list[float]:
        """A luminância média (0 a 1) de cada quadro amostrado, com o vídeo reduzido a miniaturas em tons de cinza."""
        largura, altura = 32, 18
        try:
            proc = subprocess.run(
                [
                    self.exe(),
                    "-hide_banner",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-i",
                    str(video.resolve()),
                    "-vf",
                    f"fps={amostras_por_s},scale={largura}:{altura},format=gray",
                    "-f",
                    "rawvideo",
                    "-",
                ],
                capture_output=True,
                timeout=1800,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise MotorFalhou(f"Não consegui medir a luminância do vídeo: {exc}") from exc
        if proc.returncode != 0:
            raise MotorFalhou("Não consegui medir a luminância do vídeo.")
        tamanho = largura * altura
        quadros = len(proc.stdout) // tamanho
        if quadros == 0:
            return []
        matriz = np.frombuffer(proc.stdout[: quadros * tamanho], dtype=np.uint8).reshape(quadros, tamanho)
        return [float(v) for v in matriz.mean(axis=1) / 255.0]

    def sondar(self, arquivo: Path) -> Sonda:
        """Confere de verdade o que o arquivo é (duração, tamanho, codecs), sem confiar na extensão."""
        try:
            proc = subprocess.run(
                [
                    self.exe("ffprobe"),
                    "-v",
                    "error",
                    "-show_format",
                    "-show_streams",
                    "-of",
                    "json",
                    str(arquivo.resolve()),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise MotorFalhou(f"Não consegui examinar o arquivo: {exc}") from exc
        if proc.returncode != 0:
            raise MotorFalhou("O arquivo não é um vídeo ou áudio válido.")
        try:
            dados: dict[str, Any] = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise MotorFalhou("O arquivo não é um vídeo ou áudio válido.") from exc
        return _sonda_de(dados, arquivo)


def _sonda_de(dados: dict[str, Any], arquivo: Path) -> Sonda:
    fluxos = [f for f in dados.get("streams", []) if isinstance(f, dict)]
    video = next(
        (f for f in fluxos if f.get("codec_type") == "video" and f.get("disposition", {}).get("attached_pic") != 1),
        None,
    )
    audio = next((f for f in fluxos if f.get("codec_type") == "audio"), None)
    formato = dados.get("format", {}) or {}
    try:
        duracao = float(formato.get("duration") or (video or audio or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        duracao = 0.0
    if video is None and audio is None:
        raise MotorFalhou("O arquivo não tem vídeo nem áudio.")
    return Sonda(
        formato=str(formato.get("format_name") or ""),
        duracao_s=duracao,
        largura=int(video["width"]) if video and video.get("width") else None,
        altura=int(video["height"]) if video and video.get("height") else None,
        fps=_fps(video.get("avg_frame_rate") or video.get("r_frame_rate")) if video else None,
        codec_de_video=str(video["codec_name"]) if video and video.get("codec_name") else None,
        codec_de_audio=str(audio["codec_name"]) if audio and audio.get("codec_name") else None,
        canais=int(audio["channels"]) if audio and audio.get("channels") else None,
        taxa_de_audio=int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
        tamanho_bytes=int(formato.get("size") or (arquivo.stat().st_size if arquivo.exists() else 0)),
    )
