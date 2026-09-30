<div align="center">

# Fabulim Studio

**Estúdio local para criar vídeos infantis originais (2 a 5 anos) para o YouTube, com a IA rodando no seu próprio computador.**

Personagens consistentes · roteiro · cenários · animação · voz · música · montagem · miniaturas · tudo em `127.0.0.1`

![Angular](https://img.shields.io/badge/Angular-21-DD0031?logo=angular&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-SQLite-009688?logo=fastapi&logoColor=white)
![Local first](https://img.shields.io/badge/IA-100%25%20local-2B2D6E)
![Plataforma](https://img.shields.io/badge/Windows-11-0078D4?logo=windows&logoColor=white)

<img src="docs/imagens/etapa-3-storyboard.png" alt="Fabulim Studio: o projeto em andamento, com as sete etapas" width="900">

</div>

---

## O que é

O Fabulim Studio guia você do **personagem ao vídeo pronto**. Você cria a Lila (descrevendo, colando um prompt ou importando uma imagem sua), cola o enredo e o app conduz **sete etapas, cada uma com a sua aprovação**: enredo, roteiro, storyboard, animação, áudio, montagem e revisão. No fim saem o **vídeo em MP4 com legendas**, **miniaturas 1280×720** e **título, descrição e tags em português e inglês**.

Tudo roda **na sua máquina**, mesmo num notebook **sem placa de vídeo dedicada**. Nada é enviado para fora, não há telemetria e o servidor só responde em `127.0.0.1`. O Claude (Anthropic) é a única IA externa prevista e é sempre opcional.

## Resultado

Do mesmo projeto de exemplo, gerado pelo próprio estúdio (cenários por FLUX.2 klein; a coelha Lila é um PNG transparente posto por cima):

<p align="center">
  <img src="docs/imagens/cenario-1.png" alt="Cena 1: jardim florido" height="300">
  <img src="docs/imagens/cenario-2.png" alt="Cena 2: bosque" height="300">
  <img src="docs/imagens/cenario-3.png" alt="Cena 3: céu estrelado" height="300">
</p>

Miniaturas do YouTube desenhadas por código (sem o logo do estúdio):

<p align="center">
  <img src="docs/imagens/miniatura-1.jpg" alt="Miniatura 1" width="290">
  <img src="docs/imagens/miniatura-2.jpg" alt="Miniatura 2" width="290">
  <img src="docs/imagens/miniatura-3.jpg" alt="Miniatura 3" width="290">
</p>

## Como funciona

```mermaid
flowchart LR
    A[Personagem<br/>variações, PNG transparente,<br/>poses e voz] --> B[1 Enredo]
    B --> C[2 Roteiro<br/>modelo local ou modo simples]
    C --> D[3 Storyboard<br/>cenário por IA + personagem por cima]
    D --> E[4 Animação<br/>por código]
    E --> F[5 Áudio<br/>vozes, música, efeitos, SRT]
    F --> G[6 Montagem<br/>MP4, -14 LUFS]
    G --> H[7 Revisão<br/>miniaturas, textos, pacote .fabulim]
```

Nada avança sozinho: cada etapa só libera a próxima quando **você aprova**, e voltar uma etapa nunca apaga o que já foi gerado.

### A ideia central: compor em vez de gerar

Gerar cada cena inteira por difusão, num notebook, leva minutos e ainda deixa o personagem diferente de uma cena para outra. Aqui o personagem é gerado **uma vez**, recortado em **PNG transparente** (uma folha de poses e expressões) e **posto por cima** de cenários gerados por IA. Resultado: o personagem fica **idêntico em todas as cenas** e a animação (respirar, pular, andar, entrar em cena, mexer a boca no ritmo da voz, câmera suave) é feita **por código**, rápida e previsível.

## Telas

| | |
|---|---|
| ![Criar vídeo](docs/imagens/criar-video.png) | ![Personagens](docs/imagens/personagens.png) |
| **Criar vídeo:** cole o enredo, escolha formato, duração e personagens. | **Personagens:** biblioteca com variações, poses e voz. Botão para importar uma imagem sua do Explorer. |
| ![Ficha do personagem](docs/imagens/personagem-lila.png) | ![Gerar imagem](docs/imagens/gerar-imagem.png) |
| **Ficha:** escolha a imagem principal, gere a folha de poses em PNG transparente e ajuste a voz. | **Gerar imagem:** cenários, objetos e miniaturas no estilo dos seus personagens. |
| ![Clipes](docs/imagens/clipes.png) | ![Fila](docs/imagens/fila.png) |
| **Clipes:** clipe rápido, unir, mudar de formato, continuar e enviar vídeo seu. | **Fila:** uma tarefa pesada por vez, ao vivo, com pausa e **fila noturna**. |

### As sete etapas do projeto

| | |
|---|---|
| ![Roteiro](docs/imagens/etapa-2-roteiro.png) | ![Storyboard](docs/imagens/etapa-3-storyboard.png) |
| **2 Roteiro:** cenas de 3 a 8 s com narração e falas, editáveis, com versões. | **3 Storyboard:** cenário por IA, posição de cada personagem ajustável. |
| ![Animação](docs/imagens/etapa-4-animacao.png) | ![Áudio](docs/imagens/etapa-5-audio.png) |
| **4 Animação:** por código; há o modo rascunho para conferir o movimento. | **5 Áudio:** vozes, música instrumental original, efeitos e legendas. |
| ![Montagem](docs/imagens/etapa-6-montagem.png) | ![Revisão](docs/imagens/etapa-7-revisao.png) |
| **6 Montagem:** MP4 H.264 + AAC normalizado em -14 LUFS. | **7 Revisão:** checklist de qualidade, miniaturas, textos do YouTube e versões. |

<p align="center">
  <img src="docs/imagens/tema-escuro-storyboard.png" alt="Tema escuro" width="720"><br>
  <sub>Tema claro e escuro, PT-BR e inglês, responsivo e acessível (axe WCAG AA).</sub>
</p>

## Funcionalidades

- **Personagens:** criar por descrição, prompt colado (estruturado ou texto livre) ou **imagem sua**; 1 a 4 variações; recorte automático do fundo; folha de poses (frente, três quartos, lado) e expressões; direção do olhar; voz com teste; versão 2D ↔ 3D.
- **Gerar imagem:** cenário, objeto, miniatura ou livre; até 3 personagens de referência; "gerar parecida"; prompt técnico editável; biblioteca com busca.
- **Clipes:** clipe rápido (personagem + frase), unir com transição, outro formato (9:16, 16:9, 1:1, 720p), continuar a partir do último quadro, enviar vídeo (validado de verdade).
- **Projetos:** sete etapas com aprovação; roteiro pelo modelo local **ou** modo simples sem IA; cenas com versões; checklist (conteúdo para 2 a 5 anos, ritmo, flashes, volume, duração).
- **Entrega:** miniaturas 1280×720; título, descrição e tags em PT e EN; **versão em outro idioma** e **Short ↔ vídeo longo**.
- **Portabilidade:** pacote **`.fabulim`** para escrever e aprovar no notebook e renderizar em outra máquina; **fila noturna** (nunca aprova nada sozinha).
- **Sua máquina:** perfil A/B/C/D, matriz de capacidades e benchmark de calibração, com tempo estimado antes de cada geração cara.
- **Sem IA quando precisar:** todo passo que usa o modelo de texto tem um modo sem IA, então nada trava se o Ollama estiver desligado.

## Roda no seu notebook

Tempos medidos num ThinkPad T14 Gen 2i (Core i7-1185G7, 32 GB, **Intel Iris Xe integrada**, sem CUDA):

| Tarefa | Tempo |
|---|---|
| Variação de personagem (512 px, 4 passos, Vulkan) | ~90 s |
| Recorte do fundo (BiRefNet) | ~26 s |
| Roteiro de 3 cenas (`qwen3:4b`) | 2,5 a 3 min |
| Cenário em rascunho (por cena) | ~93 s |
| Animação de 33 s de vídeo em 1080p (com as vozes) | ~2 min |
| Áudio · montagem · miniaturas | 6 s · 10 s · 3 s |

Detalhes e o que o notebook **não** faz (animação por IA, `image-to-video`) em [`docs/MODELOS.md`](docs/MODELOS.md).

## Começando

### Requisitos

- **Windows 11** (o instalador de programas só tem pacotes Windows x64), **Python 3.12**, **Node.js 22**, git
- ~6 GB de disco para os modelos (ficam dentro do projeto)
- Opcional: [**Ollama**](https://ollama.com) com `qwen3:4b` (roteiro, tradução e textos do YouTube pela IA local)
- Edge ou Chrome, só para os testes ponta a ponta

### Instalação

```bash
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r backend\requirements-dev.txt
npm --prefix frontend ci
iniciar.bat --compilar
```

O último comando compila a interface, sobe o servidor e abre http://127.0.0.1:8765.

Depois, na tela **Modelos**, clique em **Instalar tudo o que falta**: o app baixa, de **fontes oficiais** e com o **SHA-256 conferido**, o ffmpeg, o stable-diffusion.cpp, o FLUX.2 klein, o Kokoro e o BiRefNet. Nada é instalado no sistema.

### Uso do dia a dia

| Quero | Faça |
|---|---|
| Abrir o app | `iniciar.bat` |
| Deixar o servidor **sempre no ar** | `servico.bat instalar` (como administrador): cria o serviço do Windows que sobe com o Windows e reinicia o servidor se ele cair |
| Testar tudo | `testar.bat` (`--rapido`, `--hw`, `--auditoria`) |

Guia completo: [`docs/MANUAL.md`](docs/MANUAL.md) · Reinstalar do zero: [`docs/SETUP.md`](docs/SETUP.md)

## Arquitetura

```
 Angular 21 (signals, zoneless)  ── HTTP + SSE ──►  FastAPI (Python 3.12, 127.0.0.1:8765)
   Criar vídeo · Personagens ·                        ├─ jobs/        fila única, retomada, pausa, cancelamento
   Imagem · Clipes · Projetos ·                       ├─ motores/     imagem, recorte, voz, texto, ffmpeg (atrás de interfaces)
   Fila · Modelos · Status                            ├─ personagens/ imagens/ clipes/ midias/
                                                      ├─ projetos/    pipeline das 7 etapas, pacote .fabulim, fila noturna
                                                      ├─ animacao/ audio/   quadros por código, música e efeitos
                                                      ├─ conteudo/ prompts/ filtro para 2 a 5 anos, leitura de prompts
                                                      └─ SQLite (WAL, migrações versionadas)
 Locais: stable-diffusion.cpp (FLUX.2 klein) · Kokoro · BiRefNet (ONNX) · Ollama · ffmpeg
```

## Segurança

Tudo só em `127.0.0.1` (Host, CORS e CSRF por `Origin`, CSP estrita) · downloads só de fonte oficial com SHA-256, nunca pickle · subprocessos por lista de argumentos, nunca `shell=True` · uploads e pacotes `.fabulim` validados de verdade (tipo real, tamanho, zip slip) · texto de prompt e saída de LLM tratados como **dado não confiável** · segredos mascarados nos logs · sem telemetria.

## Qualidade

Ruff e mypy `strict` · ESLint e TypeScript `strict` · **~1.200 testes no backend** (cobertura ~95%) · **~300 no frontend** · ponta a ponta no Edge (desktop, tablet e celular) que percorre **do personagem ao vídeo final**, com axe (WCAG AA) nos dois temas · `pip-audit` e `npm audit`. Resultados e limites em [`docs/QA.md`](docs/QA.md).

## Documentação

| Arquivo | Conteúdo |
|---|---|
| [`docs/MANUAL.md`](docs/MANUAL.md) | como usar cada tela, formatos de prompt, tempos |
| [`docs/SETUP.md`](docs/SETUP.md) | instalar, rodar, serviço do Windows, configuração |
| [`docs/PLANO.md`](docs/PLANO.md) | perfil da máquina, arquitetura, modelos, riscos |
| [`docs/MODELOS.md`](docs/MODELOS.md) e [`docs/LICENCAS.md`](docs/LICENCAS.md) | modelos, tempos medidos e licenças (só uso comercial permitido) |
| [`docs/DESIGN.md`](docs/DESIGN.md) | linguagem visual "papel e tinta", acessibilidade |
| [`docs/DECISOES.md`](docs/DECISOES.md) | cada decisão e o porquê |
| [`docs/QA.md`](docs/QA.md) | testes, matriz de rastreabilidade e limites |
| [`CLAUDE.md`](CLAUDE.md) | memória do projeto entre sessões de trabalho |

## Limites conhecidos

- **Animação por IA** (`image-to-video`) não roda sem GPU dedicada: a animação é por código, e dá para exportar o projeto (`.fabulim`) para renderizar em outra máquina.
- **Música com letra cantada** não está instalada: a música é instrumental, gerada por código, e a letra vai como legenda.
- **Claude** (opcional), monitor de recursos e notificações do navegador ainda não existem.
- Só há pacotes de programas para **Windows x64**; o coletor de diagnóstico para Linux e macOS foi validado apenas por simulação.
- A voz em português usa espeak-ng e phonemizer, e o ffmpeg instalado é uma compilação GPL: uso **só local**, sem distribuir. Veja [`docs/LICENCAS.md`](docs/LICENCAS.md) antes de distribuir o estúdio.
- A pasta `marca/` (logo oficial) ainda não foi entregue: o logo é um texto provisório.

## Estrutura

```
backend/      FastAPI + SQLite (Python 3.12) e os testes
frontend/     Angular 21 + Tailwind v4 (tema exclusivo) e o ponta a ponta (Playwright)
scripts/      diagnóstico da máquina, instalador, testar, servidor, serviço do Windows
docs/         documentação (e docs/imagens com as capturas deste README)
tools/ models/ data/   programas, pesos e dados locais (fora do git)
```

## Licença

Defina a licença do código antes de publicar (por exemplo MIT ou Apache-2.0), respeitando as licenças das dependências e dos modelos listadas em [`docs/LICENCAS.md`](docs/LICENCAS.md).
