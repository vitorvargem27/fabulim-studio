"""Catálogo de tudo o que o Fabulim instala: só fontes oficiais, com o SHA-256 publicado pela própria fonte.

Cada item diz **de onde** vem (GitHub Releases ou Hugging Face), **para quê** serve (texto que aparece para o usuário),
a licença e onde fica dentro do projeto. O endereço final, o tamanho e o hash são resolvidos na hora, direto na API da
fonte (GitHub e Hugging Face publicam o SHA-256 de cada arquivo); sem hash publicado o item **não é instalado**.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class GitHub:
    """Arquivo de um release do GitHub (``tag`` fixa: o que foi testado; ``arquivo`` é uma expressão regular)."""

    repo: str
    tag: str
    arquivo: str


@dataclass(frozen=True)
class HuggingFace:
    """Arquivo de um repositório do Hugging Face, fixado no commit que estava em ``main`` na hora da instalação."""

    repo: str
    arquivo: str


@dataclass(frozen=True)
class Item:
    id: str
    nome: str
    para: str  # o que faz, em português simples (aparece na interface)
    fonte: GitHub | HuggingFace
    licenca: str
    base: Literal["tools", "models"]  # pasta do projeto: tools/ (programas) ou models/ (pesos de modelos)
    destino: str  # relativo à base; para item compactado, a pasta onde é extraído
    marcador: str  # arquivo (relativo à base) que existe quando o item está instalado
    compactado: bool = False
    remover_pasta_raiz: bool = False  # zip com uma pasta única na raiz: sobe o conteúdo um nível
    permitir_pickle: bool = False  # só o que já foi conferido como dado puro (ver `verificacoes`)
    grupo: str = ""  # agrupamento na tela: ffmpeg, imagem, voz, recorte
    aprox_bytes: int = 0  # tamanho aproximado do download, só para avisar antes de instalar (o real vem da fonte)


ITENS: tuple[Item, ...] = (
    Item(
        id="ffmpeg",
        nome="ffmpeg (montagem de vídeo)",
        para="Monta as cenas, mistura o áudio e exporta o vídeo final para o YouTube.",
        fonte=GitHub("BtbN/FFmpeg-Builds", "latest", r"^ffmpeg-n\d+\.\d+-latest-win64-gpl-\d+\.\d+\.zip$"),
        licenca="GPL-3.0-or-later (compilação GPL; uso local, não distribuído)",
        base="tools",
        destino="ffmpeg",
        marcador="ffmpeg/bin/ffmpeg.exe",
        compactado=True,
        remover_pasta_raiz=True,
        grupo="ffmpeg",
        aprox_bytes=194_034_028,
    ),
    Item(
        id="sd-cpp",
        nome="stable-diffusion.cpp (Vulkan)",
        para="Motor que gera as imagens dos personagens e cenários, usando a placa de vídeo integrada.",
        fonte=GitHub("leejet/stable-diffusion.cpp", "master-929-3f8527a", r"^sd-master-.*-bin-win-vulkan-x64\.zip$"),
        licenca="MIT",
        base="tools",
        destino="sd-cpp",
        marcador="sd-cpp/sd-cli.exe",
        compactado=True,
        grupo="imagem",
        aprox_bytes=30_067_605,
    ),
    Item(
        id="sd-cpp-cpu",
        nome="stable-diffusion.cpp (processador)",
        para="Versão do motor de imagens que usa só o processador: reserva, caso a placa de vídeo dê problema.",
        fonte=GitHub("leejet/stable-diffusion.cpp", "master-929-3f8527a", r"^sd-master-.*-bin-win-cpu-x64\.zip$"),
        licenca="MIT",
        base="tools",
        destino="sd-cpp-cpu",
        marcador="sd-cpp-cpu/sd-cli.exe",
        compactado=True,
        grupo="imagem",
        aprox_bytes=17_486_440,
    ),
    Item(
        id="flux2-klein-4b",
        nome="FLUX.2 klein 4B (imagens)",
        para="Modelo que desenha os personagens e cenários a partir do texto, com 4 passos.",
        fonte=HuggingFace("leejet/FLUX.2-klein-4B-GGUF", "flux-2-klein-4b-Q4_0.gguf"),
        licenca="Apache-2.0",
        base="models",
        destino="imagem/flux-2-klein-4b-Q4_0.gguf",
        marcador="imagem/flux-2-klein-4b-Q4_0.gguf",
        grupo="imagem",
        aprox_bytes=2_460_378_560,
    ),
    Item(
        id="flux2-vae",
        nome="FLUX.2 small-decoder (imagens)",
        para="Peça do modelo de imagens que transforma o desenho interno em pixels.",
        fonte=HuggingFace("black-forest-labs/FLUX.2-small-decoder", "full_encoder_small_decoder.safetensors"),
        licenca="Apache-2.0",
        base="models",
        destino="imagem/flux2-vae.safetensors",
        marcador="imagem/flux2-vae.safetensors",
        grupo="imagem",
        aprox_bytes=249_519_092,
    ),
    Item(
        id="qwen3-4b-texto",
        nome="Qwen3 4B (entende o texto das imagens)",
        para="Peça do modelo de imagens que entende a descrição que você escreve.",
        fonte=HuggingFace("unsloth/Qwen3-4B-GGUF", "Qwen3-4B-Q4_K_M.gguf"),
        licenca="Apache-2.0",
        base="models",
        destino="imagem/Qwen3-4B-Q4_K_M.gguf",
        marcador="imagem/Qwen3-4B-Q4_K_M.gguf",
        grupo="imagem",
        aprox_bytes=2_497_281_312,
    ),
    Item(
        id="kokoro-modelo",
        nome="Kokoro 82M (voz)",
        para="Modelo que fala as falas dos personagens e a narração, em português do Brasil e em inglês.",
        fonte=GitHub("thewh1teagle/kokoro-onnx", "model-files-v1.1", r"^kokoro-v1\.0\.onnx$"),
        licenca="Apache-2.0 (a pronúncia em português usa o espeak-ng, GPL-3.0, só neste computador)",
        base="models",
        destino="voz/kokoro-v1.0.onnx",
        marcador="voz/kokoro-v1.0.onnx",
        grupo="voz",
        aprox_bytes=325_505_369,
    ),
    Item(
        id="kokoro-vozes",
        nome="Vozes do Kokoro",
        para="As vozes prontas (inclusive 3 em português do Brasil) que o Kokoro usa para falar.",
        fonte=GitHub("thewh1teagle/kokoro-onnx", "model-files-v1.1", r"^voices-v1\.0\.bin$"),
        licenca="Apache-2.0",
        base="models",
        destino="voz/voices-v1.0.bin",
        marcador="voz/voices-v1.0.bin",
        permitir_pickle=True,  # é um pacote .npz de números; `verificacoes.vozes_sao_dados_puros` prova isso ao instalar
        grupo="voz",
        aprox_bytes=28_214_398,
    ),
    Item(
        id="birefnet-lite",
        nome="BiRefNet lite (recorte de fundo)",
        para="Modelo que recorta o personagem do fundo e gera o PNG transparente.",
        fonte=HuggingFace("onnx-community/BiRefNet_lite-ONNX", "onnx/model.onnx"),
        licenca="MIT",
        base="models",
        destino="recorte/birefnet-lite.onnx",
        marcador="recorte/birefnet-lite.onnx",
        grupo="recorte",
        aprox_bytes=224_005_088,
    ),
)


def por_id(id_: str) -> Item:
    for item in ITENS:
        if item.id == id_:
            return item
    raise KeyError(id_)
