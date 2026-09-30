"""Medição real dos motores de IA instalados: voz, recorte de fundo e imagem.

Cada motor roda **de verdade**, num processo à parte: a Fila consegue cancelar no meio, e a memória volta ao sistema ao
terminar. Sem o motor instalado o resultado é "skipped", com o caminho para instalar; nada é estimado às escondidas.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from ..config import Settings
from ..ferramentas import detectar
from ..hardware.capacidades import formatar_duracao
from .resultado import ResultadoBench

if TYPE_CHECKING:
    from ..jobs.worker import JobContext

PASTA = Path(__file__).resolve().parent
NAO_INSTALADO = "Ainda não instalado: abra Modelos e clique em Instalar."
SEM_BIBLIOTECA = "Falta uma biblioteca Python do app: veja o Status."

FRASE_IMAGEM = (
    "a blue rabbit named Bolinho in a field of sunflowers, cute children's book illustration, flat colors, 2D"
)
LADO_IMAGEM = 512
PASSOS_IMAGEM = 4
MODELO_DE_IMAGEM = "FLUX.2 klein 4B (Q4_0)"
ASSINATURA_PNG = b"\x89PNG\r\n\x1a\n"

Faixa = tuple[float, float]  # parte da barra de progresso do job que esta medição ocupa (de 0 a 1)


class Medidores(Protocol):
    """O que o benchmark precisa para medir os motores; os testes trocam por uma versão sem processos de verdade."""

    def voz(self, ctx: JobContext, faixa: Faixa) -> ResultadoBench: ...

    def recorte(self, ctx: JobContext, faixa: Faixa) -> ResultadoBench: ...

    def imagem(self, ctx: JobContext, faixa: Faixa) -> ResultadoBench: ...


def _json_da_saida(texto: str) -> dict[str, Any]:
    """O medidor imprime o resultado como JSON na última linha; o resto da saída é ruído de bibliotecas."""
    for linha in reversed(texto.strip().splitlines()):
        linha = linha.strip()
        if linha.startswith("{") and linha.endswith("}"):
            try:
                dados = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if isinstance(dados, dict):
                return dados
    raise ValueError("o medidor não devolveu o resultado")


def _final_da_saida(texto: str, linhas: int = 3) -> str:
    """As últimas linhas legíveis da saída de um processo, para explicar uma falha."""
    limpas = [" ".join(parte.split()) for parte in re.split(r"[\r\n]+", texto) if parte.strip()]
    return " | ".join(limpas[-linhas:])[:400]


def _br(valor: Any, casas: int = 1) -> str:
    """Número com vírgula decimal, como o usuário lê (4,9 e não 4.9)."""
    try:
        return f"{float(valor):.{casas}f}".replace(".", ",")
    except (TypeError, ValueError):
        return "?"


def _tempo(padrao: str, texto: str) -> float | None:
    achou = re.search(padrao, texto)
    return float(achou.group(1)) if achou else None


def _e_png(arquivo: Path) -> bool:
    """Gerou mesmo uma imagem? (existe, não é minúscula e começa com a assinatura de um PNG)"""
    try:
        if arquivo.stat().st_size < 10_000:
            return False
        with arquivo.open("rb") as f:
            return f.read(8) == ASSINATURA_PNG
    except OSError:
        return False


class MedidoresReais:
    def __init__(self, settings: Settings, usa_vulkan: Callable[[], bool]) -> None:
        self._settings = settings
        self._usa_vulkan = usa_vulkan

    def _pendencia(self, tarefa: str, motor: str) -> ResultadoBench | None:
        itens_faltam, libs_faltam = detectar.pendencias(self._settings, motor)
        if itens_faltam or libs_faltam:
            return ResultadoBench(tarefa, "skipped", detail=NAO_INSTALADO if itens_faltam else SEM_BIBLIOTECA)
        return None

    # --- voz e recorte: um script pequeno, em processo à parte -----------------------------------------------------
    def _rodar_script(
        self,
        ctx: JobContext,
        tarefa: str,
        modelo: str,
        comando: list[str],
        faixa: Faixa,
        mensagem: str,
        estimativa: float,
        timeout: float,
    ) -> tuple[dict[str, Any], float] | ResultadoBench:
        """Roda o medidor; devolve (json, segundos) se deu certo ou o resultado de erro."""
        inicio = time.monotonic()

        def andamento(decorrido: float) -> None:
            ctx.progresso(faixa[0] + (faixa[1] - faixa[0]) * min(0.95, decorrido / estimativa), mensagem)

        try:
            proc = ctx.executar_processo(comando, timeout=timeout, ao_tick=andamento, cwd=PASTA)
        except TimeoutError as exc:
            return ResultadoBench(tarefa, "error", model=modelo, detail=f"Não terminou a tempo: {exc}")
        gasto = round(time.monotonic() - inicio, 1)
        if proc.returncode != 0:
            detalhe = f"A medição falhou (código {proc.returncode}): {_final_da_saida(proc.stdout)}"
            return ResultadoBench(tarefa, "error", model=modelo, seconds=gasto, detail=detalhe)
        try:
            return _json_da_saida(proc.stdout), gasto
        except ValueError as exc:
            detalhe = f"{exc}: {_final_da_saida(proc.stdout)}"
            return ResultadoBench(tarefa, "error", model=modelo, seconds=gasto, detail=detalhe)

    def voz(self, ctx: JobContext, faixa: Faixa) -> ResultadoBench:
        if pendente := self._pendencia("tts", "voz"):
            return pendente
        comando = [
            sys.executable,
            str(PASTA / "medidor_voz.py"),
            str(detectar.caminho(self._settings, "kokoro-modelo")),
            str(detectar.caminho(self._settings, "kokoro-vozes")),
        ]
        rodou = self._rodar_script(ctx, "tts", "Kokoro 82M", comando, faixa, "Medindo a voz (Kokoro)...", 20, 600)
        if isinstance(rodou, ResultadoBench):
            return rodou
        dados, gasto = rodou
        rtf = dados.get("rtf")
        por_minuto = f" (≈ {float(rtf) * 60:.0f} s para cada minuto de fala)" if isinstance(rtf, (int, float)) else ""
        return ResultadoBench(
            "tts",
            "ok",
            model="Kokoro 82M",
            seconds=gasto,
            metrics=dados,
            detail=f"Falou {_br(dados.get('audio_s'))} s de áudio em {_br(dados.get('synth_s'))} s{por_minuto}, no processador.",
        )

    def recorte(self, ctx: JobContext, faixa: Faixa) -> ResultadoBench:
        if pendente := self._pendencia("cutout", "recorte"):
            return pendente
        comando = [
            sys.executable,
            str(PASTA / "medidor_recorte.py"),
            str(detectar.caminho(self._settings, "birefnet-lite")),
        ]
        rodou = self._rodar_script(
            ctx, "cutout", "BiRefNet lite", comando, faixa, "Medindo o recorte de fundo...", 60, 900
        )
        if isinstance(rodou, ResultadoBench):
            return rodou
        dados, gasto = rodou
        infer = dados.get("infer_s")
        detalhe = (
            f"≈ {formatar_duracao(float(infer))} por imagem de {dados.get('size')} px, no processador."
            if isinstance(infer, (int, float))
            else "Medido."
        )
        return ResultadoBench("cutout", "ok", model="BiRefNet lite", seconds=gasto, metrics=dados, detail=detalhe)

    # --- imagem: o próprio motor (stable-diffusion.cpp) com o modelo FLUX.2 klein ---------------------------------
    def _tentativas_de_imagem(self) -> list[tuple[str, str]]:
        """(caminho de execução, id do programa) na ordem de preferência; só os programas que estão instalados."""
        vulkan, cpu = ("vulkan", "sd-cpp"), ("cpu", "sd-cpp-cpu")
        ordem = [vulkan, cpu] if self._usa_vulkan() else [cpu, vulkan]
        return [(nome, id_) for nome, id_ in ordem if detectar.caminho(self._settings, id_).exists()]

    def _comando_de_imagem(self, programa: str, saida: Path) -> list[str]:
        s = self._settings
        return [
            str(detectar.caminho(s, programa)),
            "--diffusion-model",
            str(detectar.caminho(s, "flux2-klein-4b")),
            "--vae",
            str(detectar.caminho(s, "flux2-vae")),
            "--llm",
            str(detectar.caminho(s, "qwen3-4b-texto")),
            "-p",
            FRASE_IMAGEM,
            "-W",
            str(LADO_IMAGEM),
            "-H",
            str(LADO_IMAGEM),
            "--steps",
            str(PASSOS_IMAGEM),
            "--cfg-scale",
            "1.0",
            "--sampling-method",
            "euler",
            "--diffusion-fa",
            "-o",
            str(saida),
        ]

    def imagem(self, ctx: JobContext, faixa: Faixa) -> ResultadoBench:
        if pendente := self._pendencia("image", "imagem"):
            return pendente

        def andamento(decorrido: float) -> None:
            ctx.progresso(
                faixa[0] + (faixa[1] - faixa[0]) * min(0.95, decorrido / 150),
                f"Gerando uma imagem de teste ({LADO_IMAGEM} px, {PASSOS_IMAGEM} passos)...",
            )

        self._settings.data_dir.mkdir(parents=True, exist_ok=True)  # a imagem de teste é gravada aqui e apagada no fim
        falhas: list[str] = []
        for caminho, programa in self._tentativas_de_imagem():
            with tempfile.TemporaryDirectory(prefix="benchmark-", dir=self._settings.data_dir) as pasta:
                saida = Path(pasta) / "imagem.png"
                comando = self._comando_de_imagem(programa, saida)
                inicio = time.monotonic()
                try:
                    proc = ctx.executar_processo(comando, timeout=1800, ao_tick=andamento, cwd=Path(comando[0]).parent)
                except TimeoutError as exc:
                    falhas.append(f"{caminho}: não terminou a tempo ({exc})")
                    continue
                gasto = round(time.monotonic() - inicio, 1)
                if proc.returncode != 0 or not _e_png(saida):
                    motivo = _final_da_saida(proc.stdout)
                    falhas.append(f"{caminho}: {motivo}")
                    ctx.log(f"A imagem de teste falhou com o caminho {caminho}: {motivo}", "WARNING")
                    continue
                metricas: dict[str, Any] = {
                    "wall_s": gasto,
                    "generate_s": _tempo(r"generate_image completed in ([0-9.]+)s", proc.stdout),
                    "text_s": _tempo(r"get_learned_condition completed, taking ([0-9.]+)s", proc.stdout),
                    "sampling_s": _tempo(r"sampling completed, taking ([0-9.]+)s", proc.stdout),
                    "decode_s": _tempo(r"decode_first_stage completed, taking ([0-9.]+)s", proc.stdout),
                    "size": LADO_IMAGEM,
                    "steps": PASSOS_IMAGEM,
                    "backend": caminho,
                    "fell_back": bool(falhas),
                }
                onde = "com a placa de vídeo (Vulkan)" if caminho == "vulkan" else "no processador"
                aviso = " A placa de vídeo falhou e o teste foi refeito no processador." if falhas else ""
                resumo = f"≈ {formatar_duracao(gasto)} por imagem de {LADO_IMAGEM} px ({PASSOS_IMAGEM} passos), {onde}."
                return ResultadoBench(
                    "image", "ok", model=MODELO_DE_IMAGEM, seconds=gasto, metrics=metricas, detail=resumo + aviso
                )
        if not falhas:
            return ResultadoBench("image", "skipped", model=MODELO_DE_IMAGEM, detail=NAO_INSTALADO)
        return ResultadoBench(
            "image", "error", model=MODELO_DE_IMAGEM, detail="A geração falhou. " + " | ".join(falhas)
        )
