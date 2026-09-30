# Plano do Fabulim Studio (Fase 0)

> Estado: 2026-09-29, com as medições do uso real das ferramentas de 2026-09-30 (veja [MODELOS.md](MODELOS.md#medido-no-uso-real-das-ferramentas-2026-09-30)). Máquina de referência: ThinkPad T14 Gen 2i (perfil C). Números marcados **medido** foram obtidos nesta máquina; os marcados **estimado** são hipóteses a confirmar. Detalhes da máquina: [AMBIENTE.md](AMBIENTE.md). Modelos e licenças: [MODELOS.md](MODELOS.md), [LICENCAS.md](LICENCAS.md). Decisões: [DECISOES.md](DECISOES.md).

## 1. Resumo

- Esta máquina é **perfil C** (notebook, GPU integrada Intel Iris Xe, 32 GB de RAM, sem CUDA nem NPU). Roda texto, voz, recorte de fundo, montagem e a **Animação de cena por código** sem problema. Imagem e música por IA rodam, mas em **minutos por item**. **Animação por IA (image-to-video) não roda aqui**; fica para o desktop.
- O caminho que funciona neste perfil é **compor em vez de gerar**: personagem em PNG transparente (gerado uma vez, com folha de referência) + cenários + motor de animação por código. A consistência do personagem passa a ser garantida pela construção, e a difusão só entra para cenários, objetos e poses novas (à noite, ou no desktop).
- **Não há CUDA/ROCm/PyTorch acelerado** aqui. A pilha recomendada usa runtimes portáveis: **Ollama** (LLM), **stable-diffusion.cpp** (imagem, MIT, Vulkan/CPU) e **ONNX Runtime** (segmentação, voz).
- O frontend será **Angular 21 + TypeScript** (você é dev Angular; o briefing deixava a decisão final comigo). O backend é **Python + FastAPI + SQLite**, com fila única de GPU.
- Riscos principais: **disco (só ~61 GB livres)**, tempo de geração de imagem/música neste notebook e a **regra da Anthropic** sobre uso da assinatura em apps próprios. Todos têm mitigação abaixo.
- **Volume realista:** 10 vídeos por semana só fecha aqui reaproveitando cenários e personagens (biblioteca crescendo) ou renderizando no desktop.

## 2. A máquina e o perfil

| Item | Valor |
|---|---|
| CPU | Core i7-1185G7, 4 núcleos / 8 threads, AVX2 e **AVX-512** |
| RAM | 31,7 GB (≈ 11 GB livres com o sistema em uso normal) |
| GPU | Intel Iris Xe integrada: 128 MB dedicados + 16 GB compartilhados; Vulkan 1.4; DirectML |
| Disco | SSD NVMe; **61 GB livres em C:** |
| Energia | Notebook com bateria; plano Equilibrado |

Justificativa do perfil C e orçamento de memória para modelos (≈ 23,7 GB, estimado): ver [AMBIENTE.md](AMBIENTE.md). A classificação é reproduzível (`backend/app/hardware/perfil.py`, testada com hardware simulado de A, B, C e D em Windows, Linux e macOS). O benchmark de calibração (Fase 1) confirma ou corrige o perfil.

## 3. Matriz de capacidades prevista (perfil C)

| Funcionalidade | Estado previsto | Motivo / tempo | Origem |
|---|---|---|---|
| Parser de prompts e formulários | disponível | não precisa de modelo para o formato estruturado | projeto |
| LLM local (roteiro, enredo, prompt técnico) | **lenta** | 4B ≈ 10,8 tok/s; 9B ≈ 5 tok/s; roteiro de 6 cenas ≈ 2,5 a 5 min | 4B **medido**, 9B estimado |
| Visão local (descrever personagem) | lenta | Qwen3.5 traz visão; dezenas de segundos por imagem | estimado |
| Gerar imagem (personagem, cenário) | **lenta** | ≈ 80 s a 2 min por imagem de 512 px pela placa integrada (Vulkan); ≈ 12,7 min só pelo processador | **medido** (2026-09-29) |
| 4 variações + folha de referência | lenta | 4 imagens + ~6 poses ≈ 14 a 20 min por personagem (10 imagens × o tempo medido) | calculado a partir do medido |
| Remoção de fundo (PNG transparente) | disponível | BiRefNet lite em ONNX/CPU: ≈ 20 s por imagem de 1024 px | **medido** |
| Consistência por composição (camadas) | disponível | não usa difusão por cena | projeto |
| Consistência por imagem de referência (FLUX.2 klein) | lenta | poses novas: minutos por imagem | estimado |
| Voz de personagens e narração (PT-BR/EN) | disponível | Kokoro-82M em CPU: ≈ 0,9× o tempo real (≈ 53 s de processamento por minuto de fala) | **medido** |
| Voz própria (clonagem) | lenta | modelos de clonagem em CPU são lentos | estimado |
| Música com letra | **lenta** | ACE-Step 1.5 em CPU: minutos por música; fallback instrumental por MIDI | estimado |
| Efeitos sonoros, música instrumental, legendas SRT, mixagem | disponível | efeitos e melodia gerados por código (segundos); ffmpeg mistura em -14 LUFS | **medido** (áudio de 33 s em 6 s) |
| Animação de cena (código) | disponível | ≈ 4 min por minuto de vídeo em 1080p, contando as vozes (33 s de Short em 2 min) | **medido** (2026-09-30) |
| **Animação por IA / Clipe rápido por IA** | **indisponível** | "precisa de GPU dedicada"; marcar a cena para renderizar no desktop | briefing 3.2 |
| Montagem, exportação, unir, outra resolução | disponível | exige ffmpeg (instalado pela tela Modelos) | projeto |
| Continuar a partir de um vídeo | disponível (cenas por código) | modo IA indisponível | projeto |
| Fila noturna, exportar/importar `.fabulim` | disponível | | projeto |
| Reforço do Claude (texto e visão) | opcional | disponível se conectado | projeto |

## 4. Aceleração: recomendada e alternativa

**Medição nesta máquina** (`qwen3:4b` Q4_K_M, sem download novo):

| Caminho | Geração | Prefill (1.046 tokens) |
|---|---|---|
| CPU (AVX-512), padrão do Ollama | **10,8 tok/s** | 35 a 42 tok/s |
| iGPU Iris Xe via Vulkan (`OLLAMA_IGPU_ENABLE=1`) | 9,7 tok/s | **129 tok/s** (≈ 3,6x) |

Conclusões:

1. O Ollama **descarta a GPU integrada por padrão**. A iGPU só ajuda no prefill (prompts longos), não na geração, que é limitada pela banda da memória. O app deve subir o **próprio servidor Ollama numa porta separada com a variável só no processo** (nunca global), e só se o benchmark de calibração mostrar ganho.
2. **Recomendado:** CPU com AVX-512 como linha de base para tudo; **Vulkan na iGPU** para prefill do LLM e para o stable-diffusion.cpp (**medido: cerca de 8 vezes mais rápido que a CPU** na mesma imagem, 78 a 112 s contra 764 s); **ONNX Runtime** (CPU) para segmentação e voz.
3. **Alternativa:** OpenVINO GenAI (SD 1.5/SDXL/FLUX, CPU/iGPU/NPU) se o stable-diffusion.cpp render mal na Iris Xe. Fica atrás de `ImageProvider`, então trocar não afeta a interface.
4. **Descartados neste perfil:** ComfyUI/PyTorch (Tiger Lake não tem aceleração PyTorch oficial; DirectML está estagnado). Continuam candidatos no desktop.

## 5. Arquitetura

```
 Angular 21 (TypeScript, signals)  ──HTTP + SSE──►  FastAPI (Python 3.12, 127.0.0.1:8765)
   shell, páginas, Status,                            │
   Sua máquina, Fila                                  ├─ api/        rotas REST e eventos SSE
                                                      ├─ jobs/       fila única, worker, retomada, logs
                                                      ├─ hardware/   diagnóstico, perfil, capacidades
                                                      ├─ providers/  LLM, Visão, Imagem, Consistência, Vídeo,
                                                      │              Música, TTS, Compute (Fases 2 a 6)
                                                      ├─ pipeline/   enredo → roteiro → storyboard → ... (Fase 4+)
                                                      ├─ safety/     filtro de conteúdo infantil (Fase 2)
                                                      └─ db/         SQLite (WAL, migrações versionadas)
 Serviços locais (uma tarefa pesada por vez): Ollama, stable-diffusion.cpp, TTS, música, ffmpeg,
 motor de animação por código.
```

- **AIRouter** decide Local ou Claude por tarefa, com fallback para o local (Fase 2).
- **Tudo em 127.0.0.1**, CORS restrito, validação do cabeçalho `Host`, sem telemetria, subprocessos sempre com lista de argumentos.
- **Uma implementação, dois modos de servir:** em desenvolvimento o Angular roda em `:4200` com proxy; no uso normal o FastAPI serve o build do Angular, e `iniciar.bat` sobe tudo.
- **Motor de animação por código (Fase 6):** a decidir entre Remotion (gratuito para pessoa física, confirmado na licença) e canvas + WebCodecs no navegador, por benchmark.
- **Portabilidade entre máquinas:** o mesmo código roda no notebook e no desktop; mudam só `hardware.json`, `capabilities.json` e os modelos baixados. Projetos migram por `.fabulim`.

## 6. Modelos candidatos (resumo; detalhes em MODELOS.md)

| Tarefa | Primeira escolha para este perfil | Alternativas |
|---|---|---|
| LLM (roteiro, JSON) | Qwen3.5-9B ou Gemma 4 e4b/12b (Apache-2.0) via Ollama | Qwen3.5-4B (mais rápido), MiMo-7B (só benchmark) |
| Visão | Qwen3.5 (multimodal, mesmo modelo do texto) | Gemma 4 |
| Imagem | FLUX.2-klein-4B (Apache-2.0, GGUF) no stable-diffusion.cpp | Z-Image-Turbo, SDXL + IP-Adapter, SD 1.5 + LCM |
| Consistência | Composição por camadas + FLUX.2 klein com referência | IP-Adapter (SDXL), LoRA por personagem (desktop) |
| Recorte de fundo | BiRefNet (MIT) em ONNX | rembg com isnet-anime (2D) |
| Voz | Kokoro-82M (3 vozes PT-BR) | Qwen3-TTS (voice design, a medir) |
| Música | ACE-Step 1.5 turbo | instrumental por MIDI + SoundFont |
| Vídeo por IA | indisponível aqui | Wan 2.2 TI2V-5B, LTX-2.3 (no desktop) |

## 7. Claude: caminho recomendado

Consultei a documentação oficial atual (Legal and compliance, Agent SDK, Authentication, headless). O que ela diz:

- A autenticação OAuth da assinatura é para "uso comum do Claude Code e apps nativos". Desenvolvedores que constroem produtos, **incluindo com o Agent SDK, devem usar chave de API**.
- É proibido oferecer login do Claude.ai, repassar credenciais de assinatura em nome de usuários ou guardar/intermediar tokens. É permitido o usuário final logar no **binário `claude` sem modificação**.
- No modo `claude -p`, a flag `--bare` (recomendada para scripts) **não usa a assinatura**. A Anthropic "pode aplicar medidas sem aviso".

**Leitura:** usar a sua assinatura por um app próprio é **zona cinzenta**: um app pessoal, de um usuário só, que chama o binário oficial sem tocar em credenciais, não viola as proibições explícitas, mas contraria a orientação "desenvolvedores devem usar chave de API".

**Recomendação (aguarda a sua decisão, D1):** implementar `ClaudeProvider` com **dois backends atrás da mesma interface**:
1. **Chave de API do Console** (padrão): documentado, previsível, custo baixo para texto (centavos por roteiro), chave no cofre do sistema (`keyring`).
2. **Subprocesso `claude -p`** com o binário oficial (uso pessoal, **opt-in explícito**), em pasta neutra, sem loops, com cache e contador de uso. Não uso a biblioteca Agent SDK com login de assinatura.

O app funciona 100% sem o Claude. Nos perfis C e D, "Claude quando conectado" será o padrão sugerido para tarefas de texto, mantendo a sua escolha final.

## 8. Disco

Livre hoje: **61 GB** (C:). Orçamento estimado para o conjunto mínimo do perfil C:

| Item | Tamanho |
|---|---|
| LLM 9B Q4 (Qwen3.5-9B: 6,6 GB) + `qwen3:4b` já instalado (2,3 GB) | ~9 GB |
| Imagem: FLUX.2 klein 4B (GGUF Q4) + VAE + texto Qwen3-4B (reaproveitável do Ollama) | ~3 a 6 GB (estimado) |
| Voz (Kokoro ~0,3 GB) + recorte (BiRefNet ~0,5 GB) | ~1 GB |
| Música (ACE-Step 1.5) | ~5 a 8 GB (estimado) |
| venv Python + node_modules + ferramentas | ~4 GB |
| **Subtotal de modelos e ferramentas** | **~25 a 30 GB** |
| Cada vídeo de 5 min exportado | 0,3 a 0,6 GB |

**Mitigação:** a pasta `data/` (projetos, imagens, clipes, exportações) e `models/` é **configurável** (`FABULIM_DATA_DIR`, `FABULIM_MODELS_DIR`); recomendo apontar `data/` para outro disco ou pasta (D3). O app mostra o espaço livre no Status e limpa temporários.

## 9. Estimativas de tempo (perfil C)

| Tarefa | Tempo esperado | Origem |
|---|---|---|
| Roteiro de 6 cenas (~1.500 tokens de saída) | 4B: ≈ 2,5 min (máquina quieta) a ≈ 5 min (medição do app, máquina carregada) · 9B: ~10 min · Claude: 10 a 30 s | 4B medido; resto estimado |
| Imagem 512² com FLUX.2 klein (4 passos) | **iGPU Vulkan 78 a 112 s · CPU 12,7 min**; com referência, esperar ~2× | **medido** (o de referência ainda é estimado) |
| Narração de 60 s (Kokoro) | ≈ 53 s (medido: 0,88× o tempo real) | **medido** |
| Música de 60 s (ACE-Step, CPU) | 5 a 20 min | estimado (medir na Fase 5) |
| Render de Short de 60 s (animação por código) | ≈ 4 min (com as vozes) | **medido** (33 s de Short em 125 s) |
| Vídeo longo de 5 min | ≈ 20 min | calculado a partir do medido (o cenário de cada cena, ~93 s em rascunho, soma à parte) |

A interface mostrará a estimativa antes de cada geração cara, calculada a partir do benchmark de calibração (Fase 1, seção 2.4 do briefing).

## 10. Riscos e mitigação

| Risco | Impacto | Mitigação |
|---|---|---|
| Pouco disco (61 GB) | modelos + vídeos não cabem | `data/` e `models/` configuráveis; limpeza; conjunto mínimo; downloads sempre com a sua autorização |
| Difusão lenta no notebook | fluxo de storyboard travado | composição por camadas como padrão; fila noturna; renderizar no desktop; Claude para texto |
| Iris Xe pode não ganhar da CPU na difusão | estimativas erradas | benchmark antes de escolher o runtime; `ImageProvider` trocável (OpenVINO como alternativa) |
| Regra da Anthropic sobre assinatura | risco para a sua conta | API key como padrão; `claude -p` só opt-in; nunca tocar em credenciais |
| Licenças de fine-tunes e LoRAs | risco comercial | verificar um a um antes de usar; registrar em LICENCAS.md |
| Superaquecimento em jobs longos (notebook) | queda de desempenho | modo silencioso (menos núcleos), aviso de bateria, impedir suspensão durante jobs |
| Desmonetização por conteúdo repetitivo | canal | facilitar autoria (personagens recorrentes, voz própria); alerta de similaridade por embeddings |
| Coletor Linux/macOS só testado por simulação | falha na primeira execução real | validar no desktop e registrar |

## 11. Decisões que dependem de você

| # | Decisão | Recomendação |
|---|---|---|
| D1 | Caminho do Claude | chave de API como padrão; `claude -p` opt-in; ou só local |
| D2 | Consistência no notebook | composição por camadas como padrão + referência (FLUX.2 klein) à noite |
| D3 | Onde ficam `data/`, `models/` e `tools/` | hoje dentro do projeto (~58 GB livres em C:); outro disco só se você quiser (`FABULIM_DATA_DIR`, `FABULIM_MODELS_DIR`, `FABULIM_TOOLS_DIR`) |
| D4 | Runtime de imagem | stable-diffusion.cpp (já instalado); decidir de vez após o benchmark da Fase 3 |
| D5 | Instalações das próximas fases | **Resolvida em 2026-09-29**: o Vitor autorizou instalar tudo o que fosse necessário. Instalados (~6 GB, hash conferido): ffmpeg, sd.cpp, FLUX.2 klein 4B, small-decoder, Qwen3-4B, Kokoro, BiRefNet lite. Falta só o ACE-Step (música): pesado e com licença a conferir |
| D6 | Arquivos da marca | enviar os 4 arquivos para `marca/` (não existem na máquina) |

## 12. Roteiro das fases neste perfil

Fases 0 a 9 como no briefing. Diferenças previstas para o perfil C: Fase 3 (imagem) mede o runtime e define a estratégia de consistência; Fase 5 mede música em CPU; Fase 6 entrega o Short 100% em "Animação de cena" e mostra o modo IA desativado com explicação; Fase 7 valida o `.fabulim` numa pasta limpa e, quando possível, no desktop.
