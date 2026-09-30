# Licenças

Regra do briefing (seção 5): só entra o que permite **uso comercial e monetização dos resultados** (Apache-2.0, MIT, BSD, CreativeML OpenRAIL++-M ou licença comunitária com teto de receita que não atingimos). Proibido: NC, "research only", "non-production" ou restrição ao uso dos resultados. Cada linha tem a fonte e a data da verificação. **"A verificar" significa que ainda não conferi na fonte** e o item não pode ser usado antes disso.

Verificado em 2026-09-29 (páginas oficiais dos modelos e projetos).

## Modelos

| Item | Licença | Comercial | Fonte | Status |
|---|---|---|---|---|
| Qwen3.5 (0,8B a 122B) | Apache-2.0 | sim | https://huggingface.co/Qwen/Qwen3.5-9B | verificada |
| Qwen3 (4B) | Apache-2.0 | sim | https://huggingface.co/Qwen/Qwen3-4B | verificada na model card em 2026-09-29 |
| Gemma 4 | Apache-2.0 (mudou das versões 1 a 3, que tinham "Gemma Terms of Use") | sim | https://opensource.googleblog.com/2026/03/gemma-4-expanding-the-gemmaverse-with-apache-20.html | verificada por fonte oficial do Google |
| FLUX.2-klein-4B (inclui VAE) | Apache-2.0 | sim | https://huggingface.co/black-forest-labs/FLUX.2-klein-4B | verificada |
| FLUX.2-small-decoder | Apache-2.0 | sim | https://huggingface.co/black-forest-labs/FLUX.2-small-decoder | verificada |
| FLUX.2-dev (**não usar**) | não comercial | **não** | https://huggingface.co/black-forest-labs/FLUX.2-dev | evitar; o VAE necessário vem do repositório do klein |
| Z-Image-Turbo | Apache-2.0 | sim | https://huggingface.co/Tongyi-MAI/Z-Image-Turbo | verificada |
| SDXL base 1.0 | CreativeML OpenRAIL++-M | sim | https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0 | a verificar |
| IP-Adapter (h94) | Apache-2.0 | sim | https://huggingface.co/h94/IP-Adapter | a verificar |
| IP-Adapter FaceID / InstantID / PhotoMaker v2 | dependem de InsightFace (não comercial) | **não** | | evitar |
| BiRefNet | MIT | sim | https://huggingface.co/ZhengPeng7/BiRefNet | verificada |
| rembg (biblioteca) | MIT | sim | https://github.com/danielgatis/rembg | verificada |
| bria-rmbg 2.0 (**não usar**) | licença BRIA, paga para uso comercial | **não** | (citado no README do rembg) | evitar |
| Kokoro-82M | Apache-2.0 | sim | https://huggingface.co/hexgrad/Kokoro-82M | verificada |
| Qwen3-TTS | Apache-2.0 | sim | https://github.com/QwenLM/Qwen3-TTS | verificada por busca; confirmar na model card ao baixar |
| Chatterbox | MIT | sim | https://github.com/resemble-ai/chatterbox | não será usado neste perfil |
| ACE-Step 1.5 | MIT (model card do HF); o briefing cita Apache-2.0 | sim | https://huggingface.co/ACE-Step/Ace-Step1.5 | conferir no GitHub antes de baixar |
| Wan 2.2 TI2V-5B | Apache-2.0 | sim | https://github.com/Wan-Video/Wan2.2 | a verificar (só desktop) |
| LTX-2.3 | comunitária, gratuita para receita < US$ 10 mi/ano | sim, com teto | https://huggingface.co/Lightricks | a verificar (só desktop) |
| XTTS-v2, F5-TTS (**não usar**) | não comercial | **não** | | evitar (regra do briefing) |

Fine-tunes de estilo e LoRAs: **cada um tem licença própria** e só entram depois de verificados individualmente.

### Arquivos que o app instala (catálogo de `backend/app/ferramentas/catalogo.py`)

Conferidos na **fonte** em 2026-09-29: a licença vem dos metadados do próprio repositório (API do Hugging Face e do GitHub), e o programa foi executado para ler a configuração da compilação. O SHA-256 de cada arquivo baixado está nos `manifesto.json` de `tools/` e `models/`.

| Item instalado | Repositório de origem | Licença declarada pela fonte | Comercial |
|---|---|---|---|
| FLUX.2 klein 4B, Q4_0 (GGUF) | `leejet/FLUX.2-klein-4B-GGUF` (Hugging Face) | Apache-2.0 | sim |
| FLUX.2 small-decoder | `black-forest-labs/FLUX.2-small-decoder` | Apache-2.0 | sim |
| Qwen3-4B, Q4_K_M (GGUF) | `unsloth/Qwen3-4B-GGUF` | Apache-2.0 | sim |
| BiRefNet lite (ONNX) | `onnx-community/BiRefNet_lite-ONNX` | MIT | sim |
| Kokoro 82M (modelo e vozes) | `thewh1teagle/kokoro-onnx`, release `model-files-v1.1`; o modelo original é `hexgrad/Kokoro-82M` | código MIT; modelo Apache-2.0. **A pronúncia em português usa o espeak-ng (GPL-3.0)**, veja a ressalva abaixo | sim, com a ressalva abaixo |
| stable-diffusion.cpp (Vulkan e CPU) | `leejet/stable-diffusion.cpp`, release `master-929-3f8527a` | MIT | sim |
| ffmpeg (win64) | `BtbN/FFmpeg-Builds` (scripts de build: MIT), release `latest`, compilação `gpl` | **GPL-3.0-or-later**: `ffmpeg -version` mostra `--enable-gpl --enable-version3` | sim, com a ressalva abaixo |

**Sobre o ffmpeg GPL:** a licença vale para o **programa**, não para os vídeos que ele produz. O Fabulim só o **executa localmente** (não o distribui nem o incorpora ao app); se um dia o estúdio for distribuído para outras pessoas, trocar por uma compilação LGPL ou distribuir o código-fonte do ffmpeg. Fica registrado aqui para essa decisão não passar despercebida.

**Sobre o espeak-ng e o phonemizer (GPL) na voz em português:** o Kokoro transforma texto em sons com o **espeak-ng** (GPL-3.0, embutido pelo `espeakng-loader`, que é MIT) e com o **phonemizer** (GPL-3.0-or-later). Conferido no GitHub e no PyPI em 2026-09-29. Não há como falar português com o Kokoro sem essas duas peças. O efeito é o mesmo do ffmpeg: a GPL vale para esses **programas**, não para o áudio e os vídeos que eles ajudam a gerar (o resultado não os contém), então o uso comercial dos vídeos continua livre. O Fabulim as **executa só neste computador** e não as distribui; **se o estúdio for distribuído para outras pessoas**, é preciso tratar a GPL (código-fonte e aviso) ou trocar a voz por um modelo sem GPL, como o Qwen3-TTS (Apache-2.0, ainda não testado aqui).

## Ferramentas e bibliotecas

| Item | Licença | Fonte | Status |
|---|---|---|---|
| stable-diffusion.cpp | MIT | https://github.com/leejet/stable-diffusion.cpp | verificada |
| Ollama | MIT | https://github.com/ollama/ollama | verificada no arquivo LICENSE em 2026-09-29 |
| OpenVINO / OpenVINO GenAI | Apache-2.0 | https://github.com/openvinotoolkit/openvino | a verificar |
| Remotion | gratuita para pessoa física e até 3 funcionários; empresa maior precisa de licença paga | https://www.remotion.dev/docs/license | verificada (você é pessoa física) |
| FFmpeg | LGPL-2.1+ no núcleo; a compilação instalada (BtbN, `gpl`) é GPL-3.0-or-later | https://ffmpeg.org/legal.html | verificada: `ffmpeg -version` da compilação instalada mostra `--enable-gpl --enable-version3`; uso local, sem distribuir (veja a ressalva acima) |
| Fredoka (fonte) | SIL OFL 1.1 | https://fonts.google.com/specimen/Fredoka | verificada pelos metadados do pacote empacotado `@fontsource-variable/fredoka` (OFL-1.1) |
| Fredoka (fonte embutida no backend, para as miniaturas) | SIL OFL 1.1 | https://fonts.google.com/specimen/Fredoka | o arquivo `backend/app/recursos/fontes/Fredoka-Variable.woff2` vem do pacote `@fontsource-variable/fredoka` (OFL-1.1) e a licença vai ao lado, em `Fredoka-OFL.txt`; a OFL permite usar e embutir a fonte em software e nos vídeos e imagens gerados, sem vendê-la sozinha |
| Fraunces (fonte) | SIL OFL 1.1 | https://fonts.google.com/specimen/Fraunces | verificada pelos metadados do pacote `@fontsource-variable/fraunces` (OFL-1.1) |
| Nunito Sans (fonte) | SIL OFL 1.1 | https://fonts.google.com/specimen/Nunito+Sans | verificada pelos metadados do pacote `@fontsource-variable/nunito-sans` (OFL-1.1) |
| Angular, RxJS, Angular CDK, **Angular Aria** | MIT | https://angular.dev | `@angular/aria` verificada no `package.json` instalado (MIT); ver tabela de dependências abaixo |
| **Tailwind CSS** (v4) e `@tailwindcss/postcss` | MIT | https://tailwindcss.com | verificada no `package.json` instalado (MIT); só em desenvolvimento (gera o CSS no build) |
| ONNX Runtime, kokoro-onnx, NumPy, Pillow, soundfile | MIT, MIT, BSD-3-Clause (e permissivas nas peças embutidas), MIT-CMU, BSD-3-Clause | PyPI e GitHub | as bibliotecas Python dos modelos; ver tabela de dependências abaixo. O `kokoro-onnx` não informa a licença no PyPI: conferida no GitHub (MIT) |
| phonemizer e espeak-ng (embutido no `espeakng-loader`) | **GPL-3.0-or-later** | https://github.com/bootphon/phonemizer e https://github.com/espeak-ng/espeak-ng | verificadas no GitHub e no PyPI em 2026-09-29; uso local, sem distribuir (veja a ressalva acima) |
| FastAPI, Starlette, Pydantic, httpx, uvicorn | MIT / BSD | | ver tabela de dependências abaixo |

## Dependências instaladas

Gerada por `scripts/licencas.py --atualizar` a partir dos metadados dos próprios pacotes (regerar a cada mudança de dependência). "Comercial: sim" quer dizer que a licença consta da lista de permitidas do briefing. Situação em 2026-09-29: **0 pacotes para revisar**, e 2 **com ressalva** (`phonemizer` e `espeakng-loader`, explicadas acima). Os pacotes que o gerador não reconhece sozinho e que já foram conferidos na fonte ficam na lista `REVISADOS` de `scripts/licencas.py`.

**Observação sobre MPL-2.0** (copyleft fraco, por arquivo): `certifi` (em execução) só obriga a devolver alterações feitas nos próprios arquivos dele, e o Fabulim não os modifica nem distribui o app; `pathspec` e `@axe-core/playwright` só existem em desenvolvimento e testes. Uso comercial permitido nos três casos.

<!-- deps:inicio -->

### Python (.venv)

| Pacote | Versão | Licença | Uso | Comercial |
|---|---|---|---|---|
| annotated-doc | 0.0.5 | MIT | execução | sim |
| annotated-types | 0.8.0 | MIT | execução | sim |
| anyio | 4.15.1 | MIT | execução | sim |
| ast_serialize | 0.11.2 | MIT | desenvolvimento | sim |
| attrs | 26.1.0 | MIT | execução | sim |
| boolean.py | 5.0 | BSD-2-Clause | desenvolvimento | sim |
| CacheControl | 0.14.4 | Apache-2.0 | desenvolvimento | sim |
| certifi | 2026.7.22 | MPL-2.0 | execução | sim |
| cffi | 2.1.1 | MIT-0 | execução | sim |
| charset-normalizer | 3.5.1 | MIT | desenvolvimento | sim |
| click | 8.5.0 | BSD-3-Clause | execução | sim |
| cloudpickle | 3.1.2 | BSD-3-Clause | execução | sim |
| colorama | 0.4.6 | BSD License | desenvolvimento | sim |
| coverage | 7.16.2 | Apache-2.0 | desenvolvimento | sim |
| cyclonedx-python-lib | 11.12.0 | Apache-2.0 | desenvolvimento | sim |
| defusedxml | 0.7.1 | PSFL | desenvolvimento | sim |
| dlinfo | 2.0.0 | MIT | execução | sim |
| espeakng-loader | 0.2.4 | MIT (o carregador; leva o espeak-ng, GPL-3.0, junto) | execução | sim, com ressalva (GPL embutida) |
| fastapi | 0.141.1 | MIT | execução | sim |
| filelock | 4.0.6 | MIT | desenvolvimento | sim |
| flatbuffers | 25.12.19 | Apache 2.0 | execução | sim |
| h11 | 0.16.0 | MIT | execução | sim |
| httpcore | 1.0.9 | BSD-3-Clause | execução | sim |
| httpx | 0.28.1 | BSD-3-Clause | execução | sim |
| idna | 3.20 | BSD-3-Clause | execução | sim |
| iniconfig | 2.3.0 | MIT | desenvolvimento | sim |
| joblib | 1.6.0 | BSD-3-Clause | execução | sim |
| kokoro-onnx | 0.6.1 | MIT (conferida no GitHub; o PyPI não informa) | execução | sim |
| librt | 0.16.0 | MIT | desenvolvimento | sim |
| license-expression | 30.4.4 | Apache-2.0 | desenvolvimento | sim |
| markdown-it-py | 4.2.0 | MIT License | desenvolvimento | sim |
| mdurl | 0.1.2 | MIT License | desenvolvimento | sim |
| msgpack | 1.2.3 | Apache-2.0 | desenvolvimento | sim |
| mypy | 2.3.1 | MIT | desenvolvimento | sim |
| mypy_extensions | 1.1.0 | MIT | desenvolvimento | sim |
| numpy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | execução | sim |
| onnxruntime | 1.30.0 | MIT License | execução | sim |
| packageurl-python | 0.17.6 | MIT | desenvolvimento | sim |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | desenvolvimento | sim |
| pathspec | 1.1.1 | Mozilla Public License 2.0 (MPL 2.0) | desenvolvimento | sim |
| phonemizer | 3.4.0 | GPL-3.0-or-later | execução | sim, com ressalva (GPL, uso local) |
| pillow | 12.3.0 | MIT-CMU | execução | sim |
| pip_api | 0.0.35 | Apache Software License | desenvolvimento | sim |
| pip_audit | 2.10.1 | Apache Software License | desenvolvimento | sim |
| pip-requirements-parser | 32.0.1 | MIT | desenvolvimento | sim |
| platformdirs | 4.12.1 | MIT | desenvolvimento | sim |
| pluggy | 1.6.0 | MIT | desenvolvimento | sim |
| protobuf | 7.36.2 | 3-Clause BSD License | execução | sim |
| py-serializable | 2.1.0 | Apache-2.0 | desenvolvimento | sim |
| pycparser | 3.0 | BSD-3-Clause | execução | sim |
| pydantic | 2.13.5 | MIT | execução | sim |
| pydantic_core | 2.46.5 | MIT | execução | sim |
| Pygments | 2.21.0 | BSD-2-Clause | desenvolvimento | sim |
| pyparsing | 3.3.3 | MIT | desenvolvimento | sim |
| pytest | 9.1.1 | MIT | desenvolvimento | sim |
| pytest-cov | 7.1.0 | MIT | desenvolvimento | sim |
| requests | 2.34.2 | Apache-2.0 | desenvolvimento | sim |
| rich | 15.0.0 | MIT | desenvolvimento | sim |
| ruff | 0.16.9 | MIT | desenvolvimento | sim |
| sortedcontainers | 2.4.0 | Apache 2.0 | desenvolvimento | sim |
| soundfile | 0.14.0 | BSD 3-Clause License | execução | sim |
| starlette | 1.7.0 | BSD-3-Clause | execução | sim |
| tomli | 2.4.1 | MIT | desenvolvimento | sim |
| tomli_w | 1.2.0 | MIT License | desenvolvimento | sim |
| typing_extensions | 4.16.0 | PSF-2.0 | execução | sim |
| typing-inspection | 0.4.4 | MIT | execução | sim |
| urllib3 | 2.8.0 | MIT | desenvolvimento | sim |
| uvicorn | 0.54.0 | BSD-3-Clause | execução | sim |

### Frontend (npm, dependências diretas)

| Pacote | Versão | Licença | Uso | Comercial |
|---|---|---|---|---|
| @angular/aria | 21.2.14 | MIT | execução | sim |
| @angular/cdk | 21.2.14 | MIT | execução | sim |
| @angular/common | 21.2.24 | MIT | execução | sim |
| @angular/compiler | 21.2.24 | MIT | execução | sim |
| @angular/core | 21.2.24 | MIT | execução | sim |
| @angular/forms | 21.2.24 | MIT | execução | sim |
| @angular/platform-browser | 21.2.24 | MIT | execução | sim |
| @angular/router | 21.2.24 | MIT | execução | sim |
| @fontsource-variable/fraunces | 5.3.0 | OFL-1.1 | execução | sim |
| @fontsource-variable/fredoka | 5.3.0 | OFL-1.1 | execução | sim |
| @fontsource-variable/nunito-sans | 5.3.0 | OFL-1.1 | execução | sim |
| rxjs | 7.8.2 | Apache-2.0 | execução | sim |
| tslib | 2.8.1 | 0BSD | execução | sim |
| @angular/build | 21.2.24 | MIT | desenvolvimento | sim |
| @angular/cli | 21.2.24 | MIT | desenvolvimento | sim |
| @angular/compiler-cli | 21.2.24 | MIT | desenvolvimento | sim |
| @axe-core/playwright | 4.13.0 | MPL-2.0 | desenvolvimento | sim |
| @eslint/js | 9.39.5 | MIT | desenvolvimento | sim |
| @playwright/test | 1.63.0 | Apache-2.0 | desenvolvimento | sim |
| @tailwindcss/postcss | 4.3.3 | MIT | desenvolvimento | sim |
| @types/node | 22.20.4 | MIT | desenvolvimento | sim |
| @vitest/coverage-v8 | 4.1.11 | MIT | desenvolvimento | sim |
| angular-eslint | 21.4.0 | MIT | desenvolvimento | sim |
| eslint | 9.39.5 | MIT | desenvolvimento | sim |
| jsdom | 28.1.0 | MIT | desenvolvimento | sim |
| postcss | 8.5.28 | MIT | desenvolvimento | sim |
| prettier | 3.9.9 | MIT | desenvolvimento | sim |
| tailwindcss | 4.3.3 | MIT | desenvolvimento | sim |
| typescript | 5.9.3 | Apache-2.0 | desenvolvimento | sim |
| typescript-eslint | 8.71.0 | MIT | desenvolvimento | sim |
| vitest | 4.1.11 | MIT | desenvolvimento | sim |

<!-- deps:fim -->
