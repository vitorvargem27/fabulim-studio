# Reinstalar do zero (SETUP)

Tudo abaixo é **local ao projeto**: nada é instalado no sistema além do que você já tem (Python, Node, git). Nenhuma variável de ambiente global é alterada.

## Requisitos

| Item | Versão | Observação |
|---|---|---|
| Python | **3.12** (recomendado) | o 3.14 também tem, mas o 3.12 é o mais compatível com pacotes de IA |
| Node.js | 22 LTS (20.19+ também serve) | só para compilar e testar a interface |
| git | qualquer recente | |
| Ollama | opcional | runtime de LLM local (roteiro e enredo); https://ollama.com/download |
| Edge ou Chrome | para os testes ponta a ponta | o Playwright usa o **Edge instalado** e não baixa navegador |
| Espaço em disco | ~6 GB para os modelos + ~1 GB de dependências (Python e Node) | os modelos ficam em `models/` e os programas em `tools/`; dá para apontar para outro disco (veja "Configuração") |

## Windows

```bash
py -3.12 -m venv .venv
```

```bash
.venv\Scripts\python -m pip install -r backend\requirements-dev.txt
```

```bash
npm --prefix frontend ci
```

```bash
iniciar.bat --compilar
```

O último comando compila a interface, sobe o servidor em `http://127.0.0.1:8765` e abre o navegador. Depois basta `iniciar.bat`.

### Programas e modelos de IA (ffmpeg, motor de imagens, voz, recorte)

Com o app aberto, vá em **Modelos** e clique em **Instalar tudo o que falta**: cada item vira um job na Fila, com progresso. Só o que está no catálogo é instalado, de fonte oficial (GitHub Releases ou Hugging Face), e só se o **SHA-256 publicado pela própria fonte** conferir; o download retoma de onde parou e o espaço em disco é conferido antes. Nada é instalado no sistema: programas ficam em `tools/`, modelos em `models/` (cada pasta tem um `manifesto.json` com a origem, o hash e a licença de cada arquivo).

**Hoje o instalador só tem os pacotes de Windows (64 bits)**: em Linux e macOS os programas (ffmpeg e stable-diffusion.cpp) precisam vir do gerenciador de pacotes do sistema; os modelos (`.gguf` e `.onnx`) servem em qualquer sistema.

Pela linha de comando, o mesmo instalador:

```bash
.venv\Scripts\python scripts\instalar.py --lista
```

```bash
.venv\Scripts\python scripts\instalar.py --tudo
```

Você também pode passar o id de um item (`ffmpeg`, `sd-cpp`, `flux2-klein-4b`…). As **bibliotecas Python** que os modelos usam (`numpy`, `pillow`, `soundfile`, `onnxruntime`, `kokoro-onnx` e o que elas trazem) já estão em `backend/requirements.txt`, com a versão fixada: o `pip install` do começo deste guia as instala, e o Status avisa (com o comando) se alguma faltar.

## Linux e macOS

```bash
python3.12 -m venv .venv && .venv/bin/python -m pip install -r backend/requirements-dev.txt
```

```bash
npm --prefix frontend ci && ./iniciar.sh --compilar
```

O coletor `scripts/diagnostico.sh` foi validado só por simulação; rode-o numa máquina real e confira o `docs/AMBIENTE.md` gerado.

## Rodar

| O quê | Comando |
|---|---|
| Uso normal | `iniciar.bat` (ou `./iniciar.sh`) |
| Recompilar a interface e subir | `iniciar.bat --compilar` |
| Só o backend (porta 8765) | `.venv\Scripts\python scripts\servidor.py` |
| Interface em modo desenvolvimento (recarrega sozinha, proxy para o backend) | `npm --prefix frontend start`, abre em `http://127.0.0.1:4200` |
| Diagnóstico completo da máquina | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\diagnostico.ps1` |

## Deixar o servidor sempre no ar (serviço do Windows)

Para o servidor subir junto com o Windows e **subir de novo sozinho se cair**, instale o serviço `FabulimStudio`. Abra o `servico.bat` **como administrador** (botão direito, "Executar como administrador"):

```bash
servico.bat instalar
```

Ele instala o `pywin32` no `.venv` (`backend/requirements-servico.txt`, só para isso), cria o serviço (início automático, conta do sistema) e o liga. O serviço é um **supervisor**: roda o mesmo `scripts/servidor.py` do `iniciar.bat`, confere `/api/health` a cada 30 s e, se o servidor terminar ou parar de responder, sobe outro em segundos (espera 2, 5, 10 e 30 s se ficar caindo); se o próprio supervisor cair, o Windows o reinicia. O registro fica em `data/logs/servico-servidor.log`. Com o serviço ligado o app está sempre em http://127.0.0.1:8765 e o `iniciar.bat` só avisa que já está no ar.

| Comando (como administrador) | O que faz |
|---|---|
| `servico.bat status` | mostra se o serviço está rodando |
| `servico.bat parar` / `servico.bat iniciar` | desliga e liga (pare antes de mexer no código ou nas dependências) |
| `servico.bat remover` | para e apaga o serviço |

Depois de mudar o **backend** ou recompilar a interface, reinicie o servidor: `servico.bat parar` e `servico.bat iniciar`. Se você mudar a porta pelo `.env`, o serviço acompanha.

## Testar

```bash
py -3.12 scripts\testar.py
```

Roda lint e tipos (Python e TypeScript), testes do backend com cobertura, testes do frontend, build e os testes ponta a ponta. `--rapido` pula o build e o E2E; `--hw` inclui a suíte de hardware real (`pytest -m hw`, roda o coletor nesta máquina); `--auditoria` roda `pip-audit` e `npm audit`. Detalhes e resultados em [QA.md](QA.md).

Para o `testar --rapido` rodar sozinho antes de cada commit (opcional, recomendado):

```bash
git config core.hooksPath scripts/hooks
```

## Configuração (todas opcionais)

Copie [`.env.example`](../.env.example) para `.env` (na raiz do projeto), tire o `#` das linhas que quiser mudar e **reinicie o app**. O `.env` não vai para o git, só lê chaves `FABULIM_*`, e uma variável de ambiente de verdade, se existir, vence o arquivo. As principais: `FABULIM_PORT` (8765), `FABULIM_DATA_DIR`, `FABULIM_MODELS_DIR` e `FABULIM_TOOLS_DIR` (aponte para um disco com espaço), `FABULIM_OLLAMA_URL`. O servidor **recusa** qualquer `FABULIM_HOST` diferente de 127.0.0.1, também quando vem do `.env`.

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| A página abre mas diz que não consegue falar com o servidor | o servidor não está no ar: rode `iniciar.bat` e veja a janela minimizada "Fabulim Studio: servidor" |
| Porta 8765 ocupada | crie o `.env` com `FABULIM_PORT=8766` (ou, só nesta janela, `set FABULIM_PORT=8766`) e rode `iniciar.bat` de novo |
| Status mostra Ollama "Não respondeu" | abra o app Ollama (ícone na bandeja) ou rode `ollama serve` |
| Status mostra ffmpeg (ou outro motor) "Ainda não instalado" | abra **Modelos** e clique em **Instalar**; depois rode "Refazer diagnóstico" em Status › Sua máquina se o Status não atualizar sozinho |
| Uma instalação falhou | veja o motivo na **Fila** (o job fica como "Falhou", com a mensagem). Causas comuns: sem internet, pouco espaço em disco, ou o hash não conferiu (o arquivo é descartado); clique em Instalar de novo |
| Interface sem estilo ao abrir | recompile: `iniciar.bat --compilar` |
| Logs | `data\logs\app.jsonl` ou Status › Logs |
