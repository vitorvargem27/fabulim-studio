# Modelos

Política (briefing, seção 4): para cada tarefa, escolher o melhor modelo por **licença comercial**, **cabe no perfil**, **qualidade** e **velocidade**, nessa ordem. A escolha é **por perfil** (`config/models.yaml`, Fase 2). Pesquisa feita em 2026-09-28/29 nas fontes oficiais. Nada foi baixado além do que já existia (`qwen3:4b`).

Legenda de status: **medido** (nesta máquina), **estimado** (hipótese), **a verificar** (falta checar na fonte antes de usar).

## Medições nesta máquina (perfil C)

Modelo: `qwen3:4b` (Q4_K_M, 2,3 GB), Ollama 0.33.3, sem download novo. Script de referência: `scripts/medicoes/llm_ollama.ps1`.

| Caminho | Geração (160 tokens) | Prefill (1.046 tokens) | Observação |
|---|---|---|---|
| CPU (AVX-512), servidor padrão | 10,81 tok/s | 35,4 tok/s | `ollama ps`: 100% CPU |
| iGPU Iris Xe (Vulkan, `OLLAMA_IGPU_ENABLE=1`, servidor temporário) | 9,69 tok/s | 128,9 tok/s | 100% GPU, 37/37 camadas; saída íntegra |

O Ollama descarta a GPU integrada por padrão ("dropping integrated GPU"). A geração é limitada pela banda da memória; por isso o ganho da iGPU está só no prefill.

## LLM e visão

| Modelo | Tamanhos (Ollama) | Licença | Perfil C | Status |
|---|---|---|---|---|
| Qwen3.5 | 0,8B, 2B, 4B (3,4 GB), **9B (6,6 GB)**, 27B (17 GB), 35B (24 GB), 122B | Apache-2.0 | 4B e 9B; 27B+ não cabem/lentos; multimodal (visão), 201 idiomas com PT, contexto 256K | licença verificada; velocidade 9B estimada (~5 tok/s) |
| Gemma 4 | e2b, e4b (9,6 GB), **12b (7,6 GB)**, 26b MoE, 31b | Apache-2.0 (primeira geração Gemma com Apache) | e4b e 12b | licença verificada; a medir |
| Qwen3 | 4B (instalado), 8B | Apache-2.0 | 4B medido | medido |
| Qwen3.6 / 3.8 | 27B, 35B | a verificar | não cabem com folga | não avaliar |
| Xiaomi MiMo | MiMo-7B (MIT, raciocínio EN/ZH); V2-Flash e V2.5 são grandes | MIT | 7B cabe; fluência em PT-BR não verificada | baixa prioridade; entra no benchmark só se houver GGUF acessível |
| Phi-4, Mistral Small 3 | 14B, 24B | a verificar | pesados para este perfil | não avaliar agora |

Notas: saída sempre em JSON validado por schema (parâmetro `format` do Ollama). Modelos com modo "thinking" gastam tokens: desligar pelo parâmetro `think:false` da API de chat.

## Imagem e consistência

| Modelo / técnica | Licença | Observação | Status |
|---|---|---|---|
| **FLUX.2-klein-4B** (`black-forest-labs/FLUX.2-klein-4B`) | Apache-2.0 | 4 passos; **edição com várias imagens de referência**; o repositório traz o **próprio VAE** (Apache-2.0); GGUF da comunidade em `leejet/FLUX.2-klein-4B-GGUF`; texto Qwen3-4B | licença verificada; velocidade a medir (Fase 3) |
| FLUX.2 small-decoder | Apache-2.0 | decoder de VAE ~1,4x mais rápido e com menos memória | verificada |
| Z-Image-Turbo (`Tongyi-MAI/Z-Image-Turbo`) | Apache-2.0 | 6B, 8 passos, sem referência | licença verificada |
| SDXL + IP-Adapter | OpenRAIL++-M (SDXL); IP-Adapter Apache-2.0 | referência de estilo/personagem; **evitar FaceID e InstantID** (dependem de InsightFace, não comercial) | a verificar na fonte |
| SD 1.5 + LCM-LoRA | OpenRAIL-M | rascunhos rápidos | a verificar |
| LoRA por personagem | conforme a base | treino só em perfil A/desktop | futuro |
| Fine-tunes de estilo 2D/3D | **cada um tem licença própria** | não usar sem verificar (regra do briefing, seção 4) | a verificar caso a caso |

Runtime: **stable-diffusion.cpp** (MIT; release master-929 de 2026-09-27; binários Windows CPU 16,7 MB e Vulkan 28,7 MB; suporta FLUX.1/2, Z-Image, SD/SDXL/SD3, Qwen-Image, Kontext, PhotoMaker, IP-Adapter, LoRA, ControlNet, GGUF). Alternativa: OpenVINO GenAI. Descartados neste perfil: ComfyUI/PyTorch.

## Recorte de fundo, voz, música, vídeo

| Tarefa | Modelo | Licença | Observação | Status |
|---|---|---|---|---|
| Recorte de fundo | BiRefNet (0,2B) | MIT | via ONNX Runtime | licença verificada |
| Recorte 2D | rembg (isnet-anime, birefnet-*) | MIT | **evitar bria-rmbg** (licença paga para uso comercial) | verificada |
| Voz PT-BR | Kokoro-82M | Apache-2.0 | 3 vozes PT-BR (pf_dora, pm_alex, pm_santa); exige espeak-ng | verificada |
| Voz (design e clonagem) | Qwen3-TTS 0,6B/1,7B | Apache-2.0 | PT incluso; VoiceDesign/CustomVoice/Base; velocidade em CPU a medir | licença verificada |
| Clonagem | Chatterbox multilingual | MIT | **CPU muito lenta** (~40 s para 100 palavras); só no desktop | não usar aqui |
| Música com letra | ACE-Step 1.5 (turbo, 8 passos) | MIT (segundo a model card; conferir no GitHub) | PT incluso; repaint/cover; CPU possível mas lenta | licença a confirmar; velocidade a medir |
| Efeitos | biblioteca CC0 local | CC0 | sem gerador por IA | |
| Vídeo por IA | Wan 2.2 TI2V-5B (Apache-2.0), LTX-2.3 (licença comunitária, receita < US$ 10 mi/ano) | | **só perfis A e B** | indisponível aqui |
| Legendas | do roteiro (tempos por fala); Whisper (MIT) opcional | MIT | | |

## Como a escolha será confirmada

Fases 2 a 6 rodam, para cada tarefa, um benchmark com o **mesmo prompt de teste** (2 a 3 candidatos), registram aqui o modelo, versão/commit, fonte, licença, memória usada, tempo medido e data, e recomendam um. A página **Modelos** já existe: mostra o que está instalado e instala com um clique (D-034); o botão "Procurar modelos melhores" (a fazer) sugerirá candidatos e **nunca baixará nada sozinho**.

## Instalados nesta máquina (2026-09-29)

Fonte da verdade: [`backend/app/ferramentas/catalogo.py`](../backend/app/ferramentas/catalogo.py) (de onde vem cada item) e os `manifesto.json` de `tools/` e `models/` (endereço final, **SHA-256 conferido**, tamanho, licença e data de cada arquivo baixado). Só o que está neste catálogo é instalado pelo app.

| Item | Para quê | Licença | Tamanho |
|---|---|---|---|
| ffmpeg (build GPL do BtbN, win64) | montar e exportar vídeo | GPL-3.0-or-later, uso local | 185 MB |
| stable-diffusion.cpp (Vulkan e CPU) | motor de imagens | MIT | 29 MB e 17 MB |
| FLUX.2 klein 4B, Q4_0 (GGUF) | modelo de imagens | Apache-2.0 | 2,3 GB |
| FLUX.2 small-decoder | decodificador do modelo de imagens | Apache-2.0 | 238 MB |
| Qwen3-4B, Q4_K_M (GGUF) | codificador de texto do FLUX.2 | Apache-2.0 | 2,3 GB |
| Kokoro 82M (ONNX) e vozes | voz dos personagens e narração | Apache-2.0 (a pronúncia usa o espeak-ng, GPL-3.0) | 310 MB e 27 MB |
| BiRefNet lite (ONNX) | recorte de fundo | MIT | 214 MB |

Tamanhos como o Windows os mostra (múltiplos de 1024). Total: cerca de 5,6 GB.

### Medido nesta máquina (2026-09-29)

Pelo **benchmark de calibração do próprio app** (tela Status › Sua máquina; cada motor roda de verdade, num processo à parte). ThinkPad T14 Gen 2i, i7-1185G7, 32 GB, Iris Xe, na tomada, plano Equilibrado. **Os tempos variam com a carga do notebook** (o Windows mantém processos de fundo pesados): cada número é uma amostra, e o app guarda a data.

| Tarefa | Resultado | Como |
|---|---|---|
| Imagem, FLUX.2 klein 4B, 512 px, 4 passos, **placa de vídeo integrada (Vulkan)** | **78 a 112 s** por imagem (82 s na última medição do app) | texto 22 s + 4 passos de 13 a 22 s + decodificação 14 s (medição manual); 89 s no teste `--hw` |
| A mesma imagem **só no processador** (CPU) | **764 s (12,7 min)** | medição manual, mesmo modelo e parâmetros: a placa integrada é cerca de **8 vezes mais rápida** |
| Voz, Kokoro 82M, PT-BR (`pf_dora`) | 4,9 s de fala em 4,3 s (**0,88× o tempo real**, ≈ 53 s de processamento por minuto de fala); 3,6 s no teste manual em máquina quieta | processador; a 1ª fala (aquecimento) não conta |
| Recorte de fundo, BiRefNet lite, 1024 px | **≈ 20 s** por imagem com o modelo já carregado (a 1ª passada e a carga custam mais: 14 s + 20 s) | processador |
| Texto, `qwen3:4b` pelo Ollama | **5,9 tok/s** de geração e 23 tok/s de prefill (≈ 5 min por roteiro de 6 cenas) | processador; na Fase 0, com a máquina mais quieta, deu 10,8 tok/s. Com a placa integrada só o prefill melhora (129 tok/s), a geração fica igual |

A imagem de teste (um coelho azul num campo de girassóis, em estilo de livro infantil) saiu correta e no estilo pedido. **Consequência para o plano:** neste notebook uma imagem custa cerca de 1,5 min, então a folha de um personagem (10 imagens) leva ≈ 14 min: cabe numa rodada normal, sem precisar deixar só para a noite. **Não instalado:** ACE-Step (música); **não medidos:** música e animação por IA.

### Medido no uso real das ferramentas (2026-09-30)

Do personagem ao vídeo, **pela interface**, com os motores de verdade (FLUX.2 klein pela placa integrada, Kokoro, BiRefNet e o `qwen3:4b` do Ollama). Mesmo notebook, na tomada. Os números são de **uma execução** cada; o app mostra o tempo estimado antes de rodar e o tempo que falta durante.

| Tarefa | Tempo | Detalhe |
|---|---|---|
| Variação de personagem (1 imagem, 512 px, 4 passos) | **90 s** | pela placa integrada (Vulkan) |
| Recorte do fundo da imagem principal | **26 s** | BiRefNet lite |
| Folha de referência (2 poses, com a imagem principal de referência) | **358 s** (≈ 3 min por pose) | a referência custa mais que uma imagem simples |
| Roteiro de 3 cenas pelo modelo local | **150 a 172 s** | `qwen3:4b`, com narração e falas |
| Storyboard, 3 cenas, qualidade Rascunho (9:16) | **278 s** (≈ 93 s por cena) | cenário por FLUX; os personagens entram por cima (PNG transparente) |
| Animação por código, 3 cenas (≈ 33 s de vídeo, 1080×1920, 24 fps) | **125 s**, contando ≈ 50 s das vozes | eram 269 s antes de o desenho dos quadros passar a usar `resize` com recorte e 3 desenhistas em paralelo; o teste com o ffmpeg de verdade confere que o resultado é o mesmo |
| Áudio (vozes já feitas, música e efeitos por código) | **6 s** | mistura em -14 LUFS |
| Montagem do vídeo final (33 s) | **10 s** | H.264 e AAC; medido: -14,4 LUFS, pico -1,4 dBFS |
| Miniaturas 1280×720 (3 variações) | **2,4 s** | Pillow; sem o logo |
| Título, descrição e tags em PT e EN pelo modelo local | **60 s** | |
| Versão em inglês (tradução do roteiro pelo modelo local) | **96 s** | mantém os cenários e os personagens |
| Clipe rápido de 4 s (Rascunho) | **112 s** | cenário por FLUX + animação por código |
| Unir 2 clipes (37 s), transição fade | **52 s** | recodifica no tamanho do primeiro |
| Outro formato de um clipe de 4 s | **12 s** | |

**Consequências:** um Short de ~30 s com 3 cenas sai em **≈ 15 min** de máquina trabalhando (cenários e roteiro dominam); a folha de um personagem e os cenários pedem paciência, e a **fila noturna** existe para isso.

