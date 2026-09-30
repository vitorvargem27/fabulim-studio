# Ambiente: LENOVO ThinkPad T14 Gen 2i

> Gerado por `scripts/diagnostico` em 2026-09-29T17:09:51-03:00 (modo completo). Não edite à mão: rode o diagnóstico de novo.

## Resumo

| Item | Valor |
| --- | --- |
| Perfil | **C: Notebook ou GPU integrada** |
| Máquina | LENOVO ThinkPad T14 Gen 2i (20W1SGSV00), notebook |
| Sistema | Microsoft Windows 11 Pro 10.0.26200 (x64) |
| CPU | 11th Gen Intel(R) Core(TM) i7-1185G7 @ 3.00GHz: 4 núcleos, 8 threads; AVX, AVX2, AVX-512 |
| NPU | nenhuma |
| RAM | 31,7 GB total; 12,2 GB livres na coleta |
| GPU principal | Intel(R) Iris(R) Xe Graphics |
| Disco do projeto | 57,6 GB livres de 474,9 GB em C: (SSD (NVMe)) |
| Energia | bateria 95% (na tomada); plano Equilibrado |

## Perfil C: Notebook ou GPU integrada

Por quê:

- RAM de 31,7 GB (mínimo de 16 GB atendido)
- 57,6 GB livres no disco do projeto
- GPU: Intel(R) Iris(R) Xe Graphics (integrada: 128 MB dedicados; 16237 MB compartilhados com a RAM)
- sem VRAM dedicada: modelos usam a CPU e a memória compartilhada
- Notebook: bateria e temperatura entram na gestão de jobs pesados

Orçamento de memória para modelos (estimado): **23,7 GB**. É o teto para escolher o tamanho dos modelos; o benchmark de calibração (seção 2.4 do briefing) confirma ou corrige o perfil.

## Avisos

- Espaço apertado (57,6 GB livres): modelos e vídeos exportados enchem rápido; convém apontar a pasta de dados para outro disco

## GPU

| GPU | Tipo | Dedicada | Compartilhada | Driver | Arquitetura AMD |
| --- | --- | --- | --- | --- | --- |
| Intel(R) Iris(R) Xe Graphics | integrada | 128 MB | 16237 MB | 32.0.101.7085 | - |

## Aceleração disponível

| Caminho | Disponível | Detalhe |
| --- | --- | --- |
| CUDA (NVIDIA) | não | - |
| ROCm/HIP (AMD) | não | - |
| DirectML (Windows) | sim | DirectML.dll presente; adaptador com D3D12 ML |
| Vulkan | sim | API 1.4.313; Intel(R) Iris(R) Xe Graphics |
| Metal/MPS (Apple) | não | - |
| OpenVINO (Intel) | não | candidato (GPU/CPU Intel presente), não instalado |

Caminho recomendado, em ordem de tentativa:

1. CPU com AVX-512: linha de base confiável para llama.cpp e stable-diffusion.cpp
2. Vulkan na GPU integrada: medir, pode não ganhar da CPU (memória compartilhada)
3. OpenVINO (CPU, GPU integrada, NPU): candidato para imagem e transcrição
4. DirectML (Windows): ONNX Runtime para segmentação e TTS em ONNX

## Ferramentas

| Ferramenta | Estado | Versão | Observação |
| --- | --- | --- | --- |
| Python | instalado | 3.14.3 | versões pelo launcher: 3.14, 3.12 |
| Node.js | instalado | 22.18.0 | C:\Program Files\nodejs\node.exe |
| npm | instalado | 11.12.0 | C:\Program Files\nodejs\npm.cmd |
| git | instalado | 2.46.0 | C:\Program Files\Git\cmd\git.exe |
| ffmpeg | instalado | n9.0.2-14-gebafaee10a-20260929 | C:\video_create_ai\tools\ffmpeg\bin\ffmpeg.exe |
| Ollama | instalado | 0.33.3 | servidor ativo |
| Claude Code | instalado | 2.1.284 | logado (claude.ai, plano pro); embutido no app Claude, fora do PATH |

### Ollama e GPU

Modelos instalados: `qwen3:4b` (2,3 GB)

- Vulkan: Intel(R) Iris(R) Xe Graphics: descartada por ser integrada
- CPU: sempre disponível (usada quando nenhuma GPU é aceita)

## Pendências

Nenhuma.

## Como atualizar

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\diagnostico.ps1
```

No Linux e no macOS: `bash scripts/diagnostico.sh`. O modo leve (`-Leve` ou `--leve`) roda a cada inicialização e avisa se a máquina mudou.
