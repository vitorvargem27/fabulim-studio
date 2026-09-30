"""Miniatura do YouTube (1280×720): os personagens do vídeo sobre um cenário do storyboard, com o título em letras grandes.

Tudo é desenhado por código (Pillow), sem gerar imagem por IA: é rápido e mantém os personagens iguais aos do vídeo (usa os
mesmos PNG transparentes). Cada variação muda o cenário, a posição e o tamanho dos personagens e onde fica o título, para o
usuário escolher. **Nunca** entra o logo do estúdio (regra da marca).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

LARGURA = 1280
ALTURA = 720
FONTE = Path(__file__).resolve().parent.parent / "recursos" / "fontes" / "Fredoka-Variable.woff2"
AMARELO = (255, 201, 60)
TINTA = (43, 45, 110)
BRANCO = (255, 255, 255)
LAYOUTS = 4
MAXIMO_DE_LINHAS = 3


@dataclass(frozen=True)
class Caixa:
    """Um retângulo em frações do quadro (esquerda, topo, direita, base)."""

    e: float
    t: float
    d: float
    b: float

    def px(self) -> tuple[int, int, int, int]:
        return round(self.e * LARGURA), round(self.t * ALTURA), round(self.d * LARGURA), round(self.b * ALTURA)


@dataclass(frozen=True)
class Posicao:
    x: float  # centro, em fração da largura
    chao: float  # base do personagem, em fração da altura (pode passar de 1: o pé sai do quadro)
    altura: float  # em fração da altura do quadro


def carregar_fonte(tamanho: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Fredoka em negrito (a fonte dos títulos do estúdio); sem ela, a fonte padrão do Pillow no mesmo tamanho."""
    try:
        fonte = ImageFont.truetype(str(FONTE), tamanho)
    except OSError:
        return ImageFont.load_default(tamanho)
    with contextlib.suppress(
        OSError, AttributeError, ValueError
    ):  # sem suporte a fontes variáveis: fica no peso padrão
        fonte.set_variation_by_axes([700])  # eixo do peso: 700 = negrito
    return fonte


# --- o cenário ------------------------------------------------------------------------------------------------------------------
def fundo_16_9(caminho: Path, zoom: float = 1.0, deslocamento: float = 0.5) -> Image.Image:
    """O cenário preenchendo 1280×720. Cenário vertical (Short) vira um fundo desfocado com a imagem inteira no meio."""
    with Image.open(caminho) as original:
        base = original.convert("RGB")
    proporcao = base.width / base.height
    if proporcao >= 1.6:
        escala = max(LARGURA / base.width, ALTURA / base.height) * zoom
        redimensionada = base.resize(
            (round(base.width * escala), round(base.height * escala)), Image.Resampling.LANCZOS
        )
        x = round((redimensionada.width - LARGURA) * deslocamento)
        y = round((redimensionada.height - ALTURA) * 0.5)
        return redimensionada.crop((x, y, x + LARGURA, y + ALTURA))
    escala_fundo = max(LARGURA / base.width, ALTURA / base.height)
    fundo = base.resize((round(base.width * escala_fundo), round(base.height * escala_fundo)), Image.Resampling.LANCZOS)
    x = (fundo.width - LARGURA) // 2
    y = (fundo.height - ALTURA) // 2
    fundo = fundo.crop((x, y, x + LARGURA, y + ALTURA)).filter(ImageFilter.GaussianBlur(28))
    escala = ALTURA / base.height * zoom
    inteira = base.resize((round(base.width * escala), round(base.height * escala)), Image.Resampling.LANCZOS)
    fundo.paste(inteira, ((LARGURA - inteira.width) // 2, (ALTURA - inteira.height) // 2))
    return fundo


def realcar(imagem: Image.Image) -> Image.Image:
    """Cores um pouco mais vivas e contraste maior: miniatura pequena precisa "saltar" mais que o vídeo."""
    vivida = ImageEnhance.Color(imagem).enhance(1.18)
    return ImageEnhance.Contrast(vivida).enhance(1.08)


def vinheta(imagem: Image.Image, forca: float = 0.35) -> Image.Image:
    """Escurece de leve as bordas, para o título e os personagens destacarem do cenário."""
    mascara = Image.new("L", (LARGURA, ALTURA), 0)
    ImageDraw.Draw(mascara).ellipse((-LARGURA * 0.25, -ALTURA * 0.35, LARGURA * 1.25, ALTURA * 1.35), fill=255)
    mascara = mascara.filter(ImageFilter.GaussianBlur(120))
    escura = Image.new("RGB", (LARGURA, ALTURA), (0, 0, 0))
    return Image.composite(imagem, Image.blend(imagem, escura, forca), mascara)


# --- os personagens ---------------------------------------------------------------------------------------------------------
def recortar_ao_conteudo(imagem: Image.Image) -> Image.Image:
    caixa = imagem.getchannel("A").getbbox()
    return imagem.crop(caixa) if caixa else imagem


def com_contorno_e_sombra(personagem: Image.Image, espessura: int) -> Image.Image:
    """O personagem como um adesivo: contorno branco grosso e sombra suave (destaca em qualquer cenário)."""
    margem = espessura * 3
    tela = Image.new("RGBA", (personagem.width + margem * 2, personagem.height + margem * 2), (0, 0, 0, 0))
    tela.paste(personagem, (margem, margem), personagem)
    alfa = tela.getchannel("A")
    dilatada = alfa.filter(ImageFilter.GaussianBlur(espessura)).point(lambda v: 255 if v > 8 else 0)
    saida = Image.new("RGBA", tela.size, (0, 0, 0, 0))
    sombra = Image.new("RGBA", tela.size, (0, 0, 0, 0))
    sombra.putalpha(dilatada.filter(ImageFilter.GaussianBlur(espessura * 1.6)).point(lambda v: int(v * 0.5)))
    saida.alpha_composite(sombra, (espessura // 2, espessura))
    borda = Image.new("RGBA", tela.size, (*BRANCO, 255))
    borda.putalpha(dilatada)
    saida.alpha_composite(borda)
    saida.alpha_composite(tela)
    return saida


def posicoes(layout: int, n: int) -> list[Posicao]:
    """Onde cada personagem fica em cada um dos 4 desenhos de miniatura."""
    n = max(1, min(n, 3))
    if layout % LAYOUTS == 0:  # centro
        tabela = {
            1: [Posicao(0.5, 1.02, 0.86)],
            2: [Posicao(0.34, 1.02, 0.8), Posicao(0.66, 1.02, 0.8)],
            3: [Posicao(0.2, 1.02, 0.7), Posicao(0.5, 1.02, 0.8), Posicao(0.8, 1.02, 0.7)],
        }
    elif layout % LAYOUTS == 1:  # personagens à direita, título à esquerda
        tabela = {
            1: [Posicao(0.74, 1.02, 0.9)],
            2: [Posicao(0.58, 1.02, 0.8), Posicao(0.85, 1.02, 0.86)],
            3: [Posicao(0.5, 1.02, 0.66), Posicao(0.7, 1.02, 0.78), Posicao(0.89, 1.02, 0.7)],
        }
    elif layout % LAYOUTS == 2:  # personagens acima de uma faixa com o título
        tabela = {
            1: [Posicao(0.5, 0.78, 0.7)],
            2: [Posicao(0.36, 0.78, 0.66), Posicao(0.64, 0.78, 0.66)],
            3: [Posicao(0.24, 0.78, 0.58), Posicao(0.5, 0.78, 0.68), Posicao(0.76, 0.78, 0.58)],
        }
    else:  # zoom: o personagem grande, cortado embaixo
        tabela = {
            1: [Posicao(0.7, 1.16, 1.2)],
            2: [Posicao(0.56, 1.14, 1.0), Posicao(0.86, 1.14, 1.04)],
            3: [Posicao(0.5, 1.1, 0.86), Posicao(0.7, 1.12, 0.96), Posicao(0.9, 1.1, 0.86)],
        }
    return tabela[n]


def caixa_do_titulo(layout: int) -> Caixa:
    return (
        Caixa(0.06, 0.04, 0.94, 0.3),  # centro: em cima, de ponta a ponta
        Caixa(0.04, 0.1, 0.5, 0.86),  # direita: à esquerda, na altura toda
        Caixa(0.03, 0.8, 0.97, 0.985),  # faixa: embaixo
        Caixa(0.04, 0.06, 0.6, 0.42),  # zoom: em cima à esquerda
    )[layout % LAYOUTS]


# --- o título ----------------------------------------------------------------------------------------------------------------------
def quebrar_em_linhas(
    texto: str, fonte: ImageFont.FreeTypeFont | ImageFont.ImageFont, largura_maxima: float
) -> list[str]:
    palavras = texto.split()
    linhas: list[str] = []
    atual = ""
    for palavra in palavras:
        teste = f"{atual} {palavra}".strip()
        if atual and fonte.getlength(teste) > largura_maxima:
            linhas.append(atual)
            atual = palavra
        else:
            atual = teste
    if atual:
        linhas.append(atual)
    return linhas


def ajustar_titulo(
    texto: str, caixa: tuple[int, int, int, int]
) -> tuple[list[str], ImageFont.FreeTypeFont | ImageFont.ImageFont, int]:
    """A maior letra em que o título cabe na caixa (até 3 linhas). Devolve (linhas, fonte, altura de cada linha)."""
    largura = caixa[2] - caixa[0]
    altura = caixa[3] - caixa[1]
    melhor: tuple[list[str], ImageFont.FreeTypeFont | ImageFont.ImageFont, int] | None = None
    for tamanho in range(190, 34, -6):
        fonte = carregar_fonte(tamanho)
        linhas = quebrar_em_linhas(texto, fonte, largura)
        passo = round(tamanho * 1.08)
        if (
            len(linhas) <= MAXIMO_DE_LINHAS
            and len(linhas) * passo <= altura
            and all(fonte.getlength(x) <= largura for x in linhas)
        ):
            return linhas, fonte, passo
        melhor = (linhas[:MAXIMO_DE_LINHAS], fonte, passo)
    assert melhor is not None
    return melhor


def desenhar_titulo(imagem: Image.Image, texto: str, layout: int) -> None:
    texto = " ".join(texto.split())
    if not texto:
        return
    caixa = caixa_do_titulo(layout).px()
    desenho = ImageDraw.Draw(imagem)
    if layout % LAYOUTS == 2:  # faixa amarela com o texto em tinta
        desenho.rounded_rectangle(caixa, radius=36, fill=AMARELO, outline=TINTA, width=8)
        interior = (caixa[0] + 30, caixa[1] + 10, caixa[2] - 30, caixa[3] - 10)
        linhas, fonte, passo = ajustar_titulo(texto, interior)
        topo = interior[1] + ((interior[3] - interior[1]) - passo * len(linhas)) // 2
        for i, linha in enumerate(linhas):
            x = interior[0] + ((interior[2] - interior[0]) - fonte.getlength(linha)) / 2
            desenho.text((x, topo + i * passo), linha, font=fonte, fill=TINTA)
        return
    linhas, fonte, passo = ajustar_titulo(texto, caixa)
    alto = passo * len(linhas)
    topo = caixa[1] + ((caixa[3] - caixa[1]) - alto) // 2
    esquerda = layout % LAYOUTS == 1 or layout % LAYOUTS == 3
    contorno = max(6, round(fonte.size * 0.09)) if isinstance(fonte, ImageFont.FreeTypeFont) else 6
    for i, linha in enumerate(linhas):
        largura = fonte.getlength(linha)
        x = caixa[0] if esquerda else caixa[0] + ((caixa[2] - caixa[0]) - largura) / 2
        y = topo + i * passo
        cor = AMARELO if i % 2 == 0 else BRANCO
        desenho.text(
            (x + 5, y + 7), linha, font=fonte, fill=(0, 0, 0), stroke_width=contorno, stroke_fill=(0, 0, 0)
        )  # sombra
        desenho.text((x, y), linha, font=fonte, fill=cor, stroke_width=contorno, stroke_fill=TINTA)


# --- a miniatura -----------------------------------------------------------------------------------------------------------------
def compor_miniatura(
    fundo: Path,
    recortes: list[Path],
    *,
    titulo: str,
    variacao: int = 0,
    zoom: float = 1.0,
    deslocamento: float = 0.5,
) -> Image.Image:
    """Uma miniatura 1280×720. ``variacao`` escolhe o desenho (0 a 3, e volta ao começo) e a ordem dos personagens."""
    layout = variacao % LAYOUTS
    quadro = vinheta(realcar(fundo_16_9(fundo, zoom, deslocamento)))
    gente = recortes[:3]
    if variacao // LAYOUTS % 2 == 1:
        gente = list(reversed(gente))
    for recorte, lugar in zip(gente, posicoes(layout, len(gente)), strict=False):
        with Image.open(recorte) as aberta:
            personagem = recortar_ao_conteudo(aberta.convert("RGBA"))
        alvo = round(ALTURA * lugar.altura)
        escala = alvo / personagem.height
        personagem = personagem.resize(
            (max(1, round(personagem.width * escala)), max(1, round(personagem.height * escala))),
            Image.Resampling.LANCZOS,
        )
        adesivo = com_contorno_e_sombra(personagem, espessura=max(6, round(ALTURA * 0.014)))
        x = round(LARGURA * lugar.x - adesivo.width / 2)
        y = round(ALTURA * lugar.chao - adesivo.height + adesivo.height * 0.05)
        # `paste` com máscara aceita posição negativa e corta o que passa da borda (o pé pode sair do quadro)
        quadro.paste(adesivo.convert("RGB"), (x, y), adesivo.getchannel("A"))
    desenhar_titulo(quadro, titulo, layout)
    return quadro


def salvar_jpeg(imagem: Image.Image, destino: Path, *, limite_bytes: int = 1_900_000) -> None:
    """JPEG de até ~2 MB (o limite do YouTube para miniaturas): diminui a qualidade se passar."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    for qualidade in (92, 86, 80, 72, 64):
        imagem.save(destino, "JPEG", quality=qualidade, optimize=True)
        if destino.stat().st_size <= limite_bytes:
            return
