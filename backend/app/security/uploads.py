"""Validação de uploads (briefing, seção 11): tipo real pelo conteúdo, tamanho máximo, decodificação de verdade e EXIF removido.

Toda imagem que entra no estúdio é decodificada pelo Pillow e regravada como PNG limpo: sem metadados (EXIF, GPS, miniaturas
embutidas), com a rotação já aplicada e num tamanho razoável. Nenhum byte do arquivo enviado é guardado como veio.
"""

from __future__ import annotations

import io
import warnings
from pathlib import Path

from PIL import Image, ImageOps

MAX_IMAGEM_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 40_000_000  # acima disso a decodificação pode gastar memória demais (bomba de descompressão)
LADO_MAXIMO = 2048
_EXTENSOES = {"png": {".png"}, "jpeg": {".jpg", ".jpeg"}, "webp": {".webp"}, "gif": {".gif"}}


class UploadInvalido(ValueError):
    pass


def tipo_real_da_imagem(dados: bytes) -> str | None:
    """Reconhece PNG, JPEG, WebP e GIF pelos primeiros bytes (a extensão do nome não vale como prova)."""
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if dados.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "webp"
    if dados[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def validar_upload_imagem(dados: bytes, nome: str, *, max_bytes: int = MAX_IMAGEM_BYTES) -> str:
    """Devolve o tipo real ou levanta ``UploadInvalido`` (vazio, grande demais, não é imagem, extensão que mente)."""
    if not dados:
        raise UploadInvalido("arquivo vazio")
    if len(dados) > max_bytes:
        raise UploadInvalido(f"arquivo maior que {max_bytes // (1024 * 1024)} MB")
    tipo = tipo_real_da_imagem(dados)
    if tipo is None:
        raise UploadInvalido("o conteúdo não é uma imagem PNG, JPEG, WebP ou GIF")
    extensao = Path(nome).suffix.lower()
    if extensao not in _EXTENSOES[tipo]:
        raise UploadInvalido(f"a extensão {extensao or '(nenhuma)'} não combina com o conteúdo real ({tipo})")
    return tipo


def sanitizar_imagem(
    dados: bytes, nome: str, destino: Path, *, max_bytes: int = MAX_IMAGEM_BYTES, lado_maximo: int = LADO_MAXIMO
) -> tuple[int, int]:
    """Valida, decodifica de verdade e grava um PNG limpo em ``destino``. Devolve (largura, altura)."""
    validar_upload_imagem(dados, nome, max_bytes=max_bytes)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(dados)) as original:
                if original.width * original.height > MAX_PIXELS:
                    raise UploadInvalido("a imagem tem pixels demais (limite de 40 milhões)")
                original.load()  # decodifica de verdade: um arquivo truncado ou corrompido falha aqui
                girada = ImageOps.exif_transpose(original)
                com_alfa = "A" in girada.getbands() or "transparency" in girada.info
                limpa = girada.convert("RGBA" if com_alfa else "RGB")
    except UploadInvalido:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise UploadInvalido("a imagem está corrompida ou não pôde ser lida") from exc
    limpa.thumbnail((lado_maximo, lado_maximo), Image.Resampling.LANCZOS)
    destino.parent.mkdir(parents=True, exist_ok=True)
    limpa.save(destino, "PNG")  # sem `pnginfo` nem `exif`: nenhum metadado do original sobra
    return limpa.size
