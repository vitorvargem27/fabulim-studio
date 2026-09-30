"""Renderizador de cena: compõe cenário, sombra, personagens, efeitos e câmera, quadro a quadro, e entrega ao ffmpeg."""

from __future__ import annotations

import math
import os
import time
from collections import deque
from collections.abc import Callable, Generator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from ..erros import ErroParaOUsuario
from ..motores.interfaces import MotorFfmpeg
from ..motores.tipos import Contexto
from .camera import camera_em
from .efeitos import Brilho, brilhos_da_cena, desenhar_brilhos, desenhar_chuva
from .envelope import Vetor
from .presets import transformacao_em

ENCODE_DE_CENA = (
    "-c:v",
    "libx264",
    "-preset",
    "veryfast",
    "-crf",
    "17",
    "-pix_fmt",
    "yuv420p",
    "-movflags",
    "+faststart",
)
LARGURA_MAXIMA_DO_PERSONAGEM = 0.62  # fração da largura do quadro
QUALIDADE = Image.Resampling.LANCZOS
DESENHISTAS = 3  # quadros desenhados ao mesmo tempo (o ffmpeg e o resto do app ficam com os outros núcleos)


@dataclass
class CamadaDeRender:
    caminho: Path  # PNG recortado (RGBA)
    x: float  # centro, de 0 a 1 da largura
    base_y: float  # pés, de 0 a 1 da altura
    altura: float  # fração da altura do quadro
    espelhar: bool = False
    acao: str = "respirar"
    entrada: str = "nenhuma"
    fase: float = 0.0
    envelope: Vetor | None = None  # volume da fala por quadro (0 a 1)


@dataclass
class CenaDeRender:
    fundo: Path
    duracao_s: float
    camadas: list[CamadaDeRender] = field(default_factory=list)
    camera: str = "parada"
    efeitos: tuple[str, ...] = ()
    semente: int = 1


@dataclass
class ResultadoDeRender:
    caminho: Path
    quadros: int
    duracao_s: float
    segundos: float


@dataclass
class _Preparada:
    camada: CamadaDeRender
    imagem: Image.Image  # RGBA, já na altura de referência
    sombra: Image.Image  # RGBA (elipse borrada)


def _carregar(caminho: Path, o_que: str) -> Image.Image:
    try:
        with Image.open(caminho) as original:
            original.load()
            return original.copy()
    except (OSError, ValueError) as exc:
        raise ErroParaOUsuario(f"Não consegui abrir {o_que}. Ele foi apagado ou está corrompido?") from exc


def _sombra(largura: int, altura: int) -> Image.Image:
    folga = max(4, altura // 2)
    sprite = Image.new("RGBA", (largura + 2 * folga, altura + 2 * folga), (0, 0, 0, 0))
    ImageDraw.Draw(sprite).ellipse((folga, folga, folga + largura, folga + altura), fill=(20, 20, 40, 120))
    return sprite.filter(ImageFilter.GaussianBlur(max(1.5, altura / 3)))


class RenderizadorDeCena:
    def __init__(self, cena: CenaDeRender, largura: int, altura: int, fps: int) -> None:
        self.cena = cena
        self.largura = largura
        self.altura = altura
        self.fps = fps
        self.quadros_no_total = max(1, round(cena.duracao_s * fps))
        fundo = _carregar(cena.fundo, "o cenário")
        self.fundo = ImageOps.fit(fundo.convert("RGB"), (largura, altura), QUALIDADE, centering=(0.5, 0.5))
        self.camadas = [self._preparar(c) for c in sorted(cena.camadas, key=lambda c: (c.base_y, c.x))]
        self.brilhos: list[Brilho] = brilhos_da_cena(cena.semente) if "brilhos" in cena.efeitos else []

    def _preparar(self, camada: CamadaDeRender) -> _Preparada:
        rgba = _carregar(camada.caminho, "o recorte do personagem").convert("RGBA")
        if camada.espelhar:
            rgba = ImageOps.mirror(rgba)
        alvo_h = max(8, round(camada.altura * self.altura))
        alvo_w = max(8, round(rgba.width * alvo_h / max(rgba.height, 1)))
        if (
            alvo_w > self.largura * LARGURA_MAXIMA_DO_PERSONAGEM
        ):  # personagem largo demais: encolhe mantendo a proporção
            alvo_w = round(self.largura * LARGURA_MAXIMA_DO_PERSONAGEM)
            alvo_h = max(8, round(rgba.height * alvo_w / max(rgba.width, 1)))
        imagem = rgba.resize((alvo_w, alvo_h), QUALIDADE)
        return _Preparada(camada, imagem, _sombra(round(alvo_w * 0.72), max(6, round(alvo_h * 0.05))))

    # --- um quadro -------------------------------------------------------------------------------------------------------
    def quadro(self, indice: int) -> Image.Image:
        t = indice / self.fps
        dur = self.cena.duracao_s
        cam = camera_em(self.cena.camera, t, dur)
        largura, altura = self.largura, self.altura
        cx, cy = largura / 2 + cam.px * largura, altura / 2 + cam.py * altura
        if cam.zoom == 1.0 and cam.px == 0.0 and cam.py == 0.0:
            quadro = self.fundo.copy()
        else:
            # a câmera é um recorte do cenário esticado até o tamanho do quadro (a janela nunca sai do cenário: ver camera.folga);
            # `resize` com `box` dá o mesmo resultado que a transformação afim, na metade do tempo
            a = 1 / cam.zoom
            esquerda, topo = cx - largura * a / 2, cy - altura * a / 2
            caixa = (
                max(0.0, esquerda),
                max(0.0, topo),
                min(float(largura), esquerda + largura * a),
                min(float(altura), topo + altura * a),
            )
            quadro = self.fundo.resize((largura, altura), Image.Resampling.BILINEAR, box=caixa)
        for prep in self.camadas:
            self._desenhar(quadro, prep, indice, t, dur, cam.zoom, cx, cy)
        if self.brilhos:
            desenhar_brilhos(quadro, self.brilhos, t)
        if "chuva" in self.cena.efeitos:
            desenhar_chuva(quadro, self.cena.semente, t)
        return quadro

    def _desenhar(
        self,
        quadro: Image.Image,
        prep: _Preparada,
        indice: int,
        t: float,
        dur: float,
        zoom: float,
        cx: float,
        cy: float,
    ) -> None:
        camada = prep.camada
        volume = (
            float(camada.envelope[indice]) if camada.envelope is not None and indice < len(camada.envelope) else 0.0
        )
        tr = transformacao_em(camada.acao, camada.entrada, t, dur, camada.fase, volume)
        if tr.alfa <= 0.01:
            return
        h0, w0 = prep.imagem.height, prep.imagem.width
        base_x = (camada.x + tr.dxf) * self.largura + tr.dx * h0
        base_y = camada.base_y * self.altura + tr.dy * h0
        tela_x = (base_x - cx) * zoom + self.largura / 2
        tela_y = (base_y - cy) * zoom + self.altura / 2
        # a sombra fica no chão e encolhe quando o personagem salta
        no_ar = max(0.0, -tr.dy)
        largura_da_sombra = max(2, round(prep.sombra.width * zoom * max(0.5, 1 - no_ar * 1.2) * tr.sx))
        altura_da_sombra = max(2, round(prep.sombra.height * zoom))
        sombra = prep.sombra.resize((largura_da_sombra, altura_da_sombra), Image.Resampling.BILINEAR)
        forca = max(0.25, 1 - no_ar * 3.5) * tr.alfa
        if forca < 0.999:
            sombra.putalpha(sombra.getchannel("A").point(lambda v: int(v * forca)))
        quadro.paste(
            sombra,
            (round(tela_x - largura_da_sombra / 2), round(tela_y - altura_da_sombra / 2)),
            sombra,
        )
        w1, h1 = max(1, round(w0 * zoom * tr.sx)), max(1, round(h0 * zoom * tr.sy))
        imagem = prep.imagem.resize((w1, h1), Image.Resampling.BILINEAR)
        if abs(tr.rot) > 0.05:
            girada = imagem.convert("RGBa").rotate(tr.rot, resample=Image.Resampling.BICUBIC, expand=True)
            angulo = math.radians(tr.rot)
            esquerda = tela_x - (girada.width / 2 + (h1 / 2) * math.sin(angulo))
            topo = tela_y - (girada.height / 2 + (h1 / 2) * math.cos(angulo))
            imagem = girada.convert("RGBA")
        else:
            esquerda, topo = tela_x - w1 / 2, tela_y - h1
        if tr.alfa < 0.999:
            imagem.putalpha(imagem.getchannel("A").point(lambda v: int(v * tr.alfa)))
        quadro.paste(imagem, (round(esquerda), round(topo)), imagem)

    def _bytes_do_quadro(self, indice: int) -> bytes:
        return self.quadro(indice).tobytes()

    def quadros(self, desenhistas: int | None = None) -> Generator[bytes, None, None]:
        """Os quadros, em ordem. Vários são desenhados ao mesmo tempo: o Pillow solta o GIL nas contas pesadas, e assim o
        desenho anda junto com a codificação em vez de esperar por ela. Cada quadro só lê o cenário e os personagens já
        preparados, então a ordem de desenho não muda o resultado."""
        if desenhistas is None:
            desenhistas = min(DESENHISTAS, (os.cpu_count() or 1) - 1)
        if desenhistas <= 1 or self.quadros_no_total < 2 * desenhistas:
            for indice in range(self.quadros_no_total):
                yield self._bytes_do_quadro(indice)
            return
        pendentes: deque[Future[bytes]] = deque()
        proximo = 0
        with ThreadPoolExecutor(max_workers=desenhistas, thread_name_prefix="quadro") as pool:
            try:
                while proximo < self.quadros_no_total or pendentes:
                    while proximo < self.quadros_no_total and len(pendentes) < 2 * desenhistas:
                        pendentes.append(pool.submit(self._bytes_do_quadro, proximo))
                        proximo += 1
                    yield pendentes.popleft().result()
            finally:
                for futuro in pendentes:  # cancelou ou falhou: o que ainda não começou não precisa ser desenhado
                    futuro.cancel()


def renderizar_cena(
    ctx: Contexto,
    ffmpeg: MotorFfmpeg,
    cena: CenaDeRender,
    saida: Path,
    *,
    largura: int,
    altura: int,
    fps: int = 24,
    faixa: tuple[float, float] = (0.0, 1.0),
    argumentos_de_saida: Sequence[str] = ENCODE_DE_CENA,
) -> ResultadoDeRender:
    """Desenha os quadros da cena e o ffmpeg codifica o clipe (só imagem; o áudio entra na montagem)."""
    inicio = time.monotonic()
    renderizador = RenderizadorDeCena(cena, largura, altura, fps)
    total = renderizador.quadros_no_total

    def andamento(fracao: float) -> None:
        ctx.progresso(faixa[0] + (faixa[1] - faixa[0]) * min(0.98, fracao), None)

    quadros = renderizador.quadros()
    try:
        ffmpeg.rodar_com_quadros(
            ctx,
            quadros,
            largura=largura,
            altura=altura,
            fps=fps,
            total=total,
            saida=saida,
            argumentos_de_saida=argumentos_de_saida,
            ao_progresso=andamento,
        )
    finally:
        quadros.close()  # cancelou ou falhou no meio: solta os desenhistas na hora
    return ResultadoDeRender(saida, total, total / fps, round(time.monotonic() - inicio, 1))


def quadro_de_capa(cena: CenaDeRender, largura: int, altura: int, t: float = 1.0) -> Image.Image:
    """Um quadro da cena (por padrão em 1 s, quando a entrada já terminou): a miniatura do storyboard."""
    renderizador = RenderizadorDeCena(cena, largura, altura, 24)
    indice = min(int(t * 24), renderizador.quadros_no_total - 1)
    return renderizador.quadro(max(indice, 0))


def aviso_de_progresso(ao_progresso: Callable[[float], None] | None, fracao: float) -> None:
    if ao_progresso:
        ao_progresso(fracao)
