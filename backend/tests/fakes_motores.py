"""Motores falsos e determinísticos (briefing, seção 12.1): a suíte principal roda rápido, offline e sem GPU."""

from __future__ import annotations

import subprocess
import wave
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from app.jobs.worker import JobCanceled
from app.motores.fabrica import Motores
from app.motores.ffmpeg import Sonda
from app.motores.tipos import ItemDeVoz, MotorFalhou, MotorIndisponivel, PedidoImagem, ResultadoDeVoz, ResultadoImagem


class ContextoDeTeste:
    """Um contexto de job que só anota as chamadas. ``cancelar_no_ponto`` cancela no N-ésimo ponto de controle."""

    def __init__(self, cancelar_no_ponto: int | None = None, servicos: Any = None) -> None:
        self.progressos: list[tuple[float, str | None]] = []
        self.logs: list[tuple[str, str]] = []
        self.pontos = 0
        self._cancelar_no_ponto = cancelar_no_ponto
        self.comandos: list[list[str]] = []
        self.servicos = servicos  # para chamar os handlers dos jobs direto, sem a fila
        self.job_id = "0" * 32
        self.kind = "teste"

    def progresso(self, fracao: float, mensagem: str | None = None) -> None:
        self.progressos.append((fracao, mensagem))

    def log(self, mensagem: str, nivel: str = "INFO") -> None:
        self.logs.append((nivel, mensagem))

    def ponto_de_controle(self) -> None:
        self.pontos += 1
        if self._cancelar_no_ponto is not None and self.pontos >= self._cancelar_no_ponto:
            raise JobCanceled

    def executar_processo(
        self,
        comando: Sequence[str],
        *,
        timeout: float,
        ao_tick: Callable[[float], None] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self.comandos.append(list(comando))
        return subprocess.CompletedProcess(list(comando), 0, "", "")


class ContextoReal(ContextoDeTeste):
    """Contexto que roda os processos de verdade (para os poucos testes que usam o ffmpeg real)."""

    def executar_processo(
        self,
        comando: Sequence[str],
        *,
        timeout: float,
        ao_tick: Callable[[float], None] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self.comandos.append(list(comando))
        proc = subprocess.run(list(comando), capture_output=True, timeout=timeout, cwd=cwd, check=False)
        texto = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
        return subprocess.CompletedProcess(list(comando), proc.returncode, texto, "")


class ImagemFalsa:
    def __init__(self, indisponivel: str | None = None, falhar: str | None = None) -> None:
        self._indisponivel = indisponivel
        self._falhar = falhar
        self.pedidos: list[PedidoImagem] = []

    def indisponivel(self) -> str | None:
        return self._indisponivel

    def estimativa(self, largura: int, altura: int, com_referencia: bool = False) -> float:
        return 100.0 * (largura * altura) / (512 * 512) * (1.3 if com_referencia else 1.0)

    def gerar(
        self, ctx: Any, pedido: PedidoImagem, saida: Path, faixa: tuple[float, float] = (0.0, 1.0)
    ) -> ResultadoImagem:
        if self._indisponivel:
            raise MotorIndisponivel(self._indisponivel)
        if self._falhar:
            raise MotorFalhou(self._falhar)
        ctx.ponto_de_controle()
        self.pedidos.append(pedido)
        cor = ((pedido.seed * 47) % 200 + 30, (pedido.seed * 91) % 200 + 30, (pedido.seed * 13) % 200 + 30)
        imagem = Image.new("RGB", (pedido.largura, pedido.altura), (245, 245, 245))
        ImageDraw.Draw(imagem).ellipse(
            (pedido.largura * 0.3, pedido.altura * 0.2, pedido.largura * 0.7, pedido.altura * 0.9), fill=cor
        )
        saida.parent.mkdir(parents=True, exist_ok=True)
        imagem.save(saida, "PNG")
        ctx.progresso(faixa[1], None)
        return ResultadoImagem(
            caminho=saida,
            segundos=0.5,
            seed=pedido.seed,
            largura=pedido.largura,
            altura=pedido.altura,
            caminho_de_execucao="vulkan",
            modelo="falso",
            metricas={"references": len(pedido.referencias)},
        )


class RecorteFalso:
    def __init__(self, indisponivel: str | None = None) -> None:
        self._indisponivel = indisponivel
        self.origens: list[Path] = []

    def indisponivel(self) -> str | None:
        return self._indisponivel

    def recortar(
        self, ctx: Any, origem: Path, saida: Path, *, caixa: bool = True, faixa: tuple[float, float] = (0.0, 1.0)
    ) -> dict[str, Any]:
        if self._indisponivel:
            raise MotorIndisponivel(self._indisponivel)
        ctx.ponto_de_controle()
        self.origens.append(origem)
        with Image.open(origem) as original:
            rgba = original.convert("RGBA")
            mascara = Image.new("L", rgba.size, 0)
            largura, altura = rgba.size
            ImageDraw.Draw(mascara).ellipse((largura * 0.3, altura * 0.2, largura * 0.7, altura * 0.9), fill=255)
            rgba.putalpha(mascara)
            if caixa and (limites := mascara.getbbox()):
                rgba = rgba.crop(limites)
        saida.parent.mkdir(parents=True, exist_ok=True)
        rgba.save(saida, "PNG")
        return {"width": rgba.size[0], "height": rgba.size[1], "seconds": 0.1}


class VozFalsa:
    SEGUNDOS_POR_LETRA = 0.05

    def __init__(self, indisponivel: str | None = None) -> None:
        self._indisponivel = indisponivel
        self.itens: list[ItemDeVoz] = []

    def indisponivel(self) -> str | None:
        return self._indisponivel

    def falar(
        self, ctx: Any, itens: Sequence[ItemDeVoz], faixa: tuple[float, float] = (0.0, 1.0)
    ) -> list[ResultadoDeVoz]:
        if self._indisponivel:
            raise MotorIndisponivel(self._indisponivel)
        resultados: list[ResultadoDeVoz] = []
        for item in itens:
            ctx.ponto_de_controle()
            self.itens.append(item)
            duracao = max(0.4, len(item.texto) * self.SEGUNDOS_POR_LETRA)
            item.saida.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(item.saida), "wb") as arquivo:
                arquivo.setnchannels(1)
                arquivo.setsampwidth(2)
                arquivo.setframerate(24_000)
                arquivo.writeframes(b"\x00\x00" * int(24_000 * duracao))
            resultados.append(ResultadoDeVoz(item.saida, duracao))
        return resultados


class TextoFalso:
    """Devolve respostas prontas, na ordem (ou pela função ``responder``); anota o que foi pedido."""

    def __init__(
        self,
        respostas: list[dict[str, Any]] | None = None,
        responder: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        indisponivel: str | None = None,
    ) -> None:
        self.respostas = list(respostas or [])
        self._responder = responder
        self._indisponivel = indisponivel
        self.chamadas: list[dict[str, Any]] = []

    def indisponivel(self) -> str | None:
        return self._indisponivel

    def estruturar(
        self,
        ctx: Any,
        *,
        sistema: str,
        dados: str,
        instrucao: str,
        esquema: dict[str, Any],
        num_predict: int = 1500,
        temperatura: float = 0.4,
        faixa: tuple[float, float] = (0.0, 1.0),
        seed: int | None = None,
    ) -> dict[str, Any]:
        if self._indisponivel:
            raise MotorIndisponivel(self._indisponivel)
        ctx.ponto_de_controle()
        chamada = {"sistema": sistema, "dados": dados, "instrucao": instrucao, "esquema": esquema}
        self.chamadas.append(chamada)
        if self._responder:
            return self._responder(chamada)
        if not self.respostas:
            raise MotorFalhou("TextoFalso sem resposta pronta")
        return self.respostas.pop(0)


class FfmpegFalso:
    """Não roda o ffmpeg: anota os argumentos e cria o arquivo de saída (a cópia da primeira entrada, se houver)."""

    def __init__(self, indisponivel: str | None = None) -> None:
        self._indisponivel = indisponivel
        self.execucoes: list[list[str]] = []
        self.sondas: dict[str, Sonda] = {}
        self.falhar_com: str | None = None
        self.renders: list[dict[str, Any]] = []
        self.luminancias: dict[str, list[float]] = {}

    def indisponivel(self) -> str | None:
        return self._indisponivel

    def exe(self, nome: str = "ffmpeg") -> str:
        return f"/falso/{nome}"

    def rodar(
        self,
        ctx: Any,
        argumentos: Sequence[str | Path],
        *,
        timeout: float = 3600,
        ao_tick: Callable[[float], None] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if self._indisponivel:
            raise MotorIndisponivel(self._indisponivel)
        args = [str(a) for a in argumentos]
        ctx.ponto_de_controle()
        self.execucoes.append(args)
        if self.falhar_com:
            raise MotorFalhou(self.falhar_com)
        saida = Path(args[-1])
        # «-f null -» só mede: o ffmpeg de verdade não grava nada (o falso deixava um arquivo «-» na pasta do projeto)
        if saida.name == "-":
            return subprocess.CompletedProcess(args, 0, "", "")
        entradas = [Path(args[i + 1]) for i, a in enumerate(args[:-1]) if a == "-i"]
        saida.parent.mkdir(parents=True, exist_ok=True)
        if entradas and entradas[0].is_file() and entradas[0].suffix == saida.suffix:
            saida.write_bytes(entradas[0].read_bytes())
        else:
            saida.write_bytes(b"falso" * 100)
        return subprocess.CompletedProcess(args, 0, "", "")

    def rodar_com_quadros(
        self,
        ctx: Any,
        quadros: Iterable[bytes],
        *,
        largura: int,
        altura: int,
        fps: float,
        total: int,
        saida: Path,
        argumentos_de_saida: Sequence[str | Path] = (),
        timeout: float = 7200.0,
        ao_progresso: Callable[[float], None] | None = None,
    ) -> None:
        """Consome os quadros de verdade (o desenho roda inteiro) e guarda o primeiro e o último para os testes."""
        if self._indisponivel:
            raise MotorIndisponivel(self._indisponivel)
        contagem = 0
        primeiro: bytes | None = None
        ultimo: bytes | None = None
        for quadro in quadros:
            if contagem % 6 == 0:
                ctx.ponto_de_controle()  # como o ffmpeg de verdade: pausar e cancelar valem a cada poucos quadros
            if len(quadro) != largura * altura * 3:
                raise MotorFalhou("Um quadro da animação saiu com tamanho errado.")
            primeiro = primeiro if primeiro is not None else quadro
            ultimo = quadro
            contagem += 1
            if ao_progresso and contagem % 6 == 0:
                ao_progresso(contagem / max(total, 1))
        if self.falhar_com:
            raise MotorFalhou(self.falhar_com)
        self.renders.append(
            {
                "largura": largura,
                "altura": altura,
                "fps": fps,
                "quadros": contagem,
                "saida": saida,
                "argumentos": [str(a) for a in argumentos_de_saida],
                "primeiro": primeiro,
                "ultimo": ultimo,
            }
        )
        saida.parent.mkdir(parents=True, exist_ok=True)
        saida.write_bytes(b"falso" * 100)
        self.sondas[str(saida)] = Sonda("mov,mp4", contagem / fps, largura, altura, fps, "h264", None, None, None, 500)

    def extrair_luminancia(self, video: Path, amostras_por_s: int = 12) -> list[float]:
        return self.luminancias.get(str(video), [0.5] * (amostras_por_s * 3))

    def sondar(self, arquivo: Path) -> Sonda:
        if str(arquivo) in self.sondas:
            return self.sondas[str(arquivo)]
        if arquivo.suffix == ".wav" and arquivo.is_file():
            with wave.open(str(arquivo), "rb") as wav:
                duracao = wav.getnframes() / wav.getframerate()
                return Sonda(
                    "wav",
                    duracao,
                    None,
                    None,
                    None,
                    None,
                    "pcm_s16le",
                    wav.getnchannels(),
                    wav.getframerate(),
                    arquivo.stat().st_size,
                )
        if arquivo.suffix in (".mp4", ".mov", ".mkv", ".webm"):
            return Sonda(
                "mov,mp4",
                3.0,
                1280,
                720,
                24.0,
                "h264",
                "aac",
                2,
                44100,
                arquivo.stat().st_size if arquivo.exists() else 0,
            )
        raise MotorFalhou("O arquivo não é um vídeo ou áudio válido.")


def motores_falsos() -> Motores:
    return Motores(
        imagem=ImagemFalsa(), recorte=RecorteFalso(), voz=VozFalsa(), texto=TextoFalso(), ffmpeg=FfmpegFalso()
    )
