# QA (Fabulim Studio)

Matriz de rastreabilidade (funcionalidade → testes → status) e relatório de QA de cada fase. **Nenhuma fase fecha com teste falhando.** Testes automáticos garantem o *comportamento* do app; a *qualidade artística* do que a IA gera é medida pelo benchmark de qualidade (briefing 12.6) e pela sua aprovação.

## Como rodar

| Comando | O que faz |
|---|---|
| `testar.bat` (ou `./testar.sh`) | **tudo**: lint, tipos, testes do backend e do frontend com cobertura, build e ponta a ponta no Edge (**~30 a 45 min** neste notebook: o backend tem 1.200 testes, vários com o ffmpeg de verdade, e o ponta a ponta percorre o app inteiro) |
| `testar.bat --rapido` | sem build e sem ponta a ponta (**~12 a 18 min**, quase tudo do pytest); é o que o hook de pre-commit roda. Se o hook incomodar, deixe de ativá-lo e rode o `testar` completo antes de commitar |
| `testar.bat --hw` | inclui a suíte de hardware real (`pytest -m hw`): roda o coletor e os motores de verdade nesta máquina (~3 a 4 min) |
| `testar.bat --auditoria` | inclui `pip-audit` e `npm audit` (precisa de internet) |
| `npm --prefix frontend run e2e` | só o ponta a ponta (compila antes) |

O que não puder rodar aparece como **PULOU**, com o motivo; nada é fingido. O comando sai com código 1 se algum passo **FALHOU**.

**Portões de qualidade** (todos automáticos): Ruff (lint e formatação) e mypy `strict` no Python; ESLint (com regras de acessibilidade dos templates) e TypeScript `strict` no frontend; cobertura mínima de **80%** no backend e **70%** no frontend (o passo falha abaixo disso); **hook de pre-commit** (`git config core.hooksPath scripts/hooks`) que roda o `testar --rapido` antes de cada commit.

---

## Relatório de QA: Fase 1 (Fundação)

<!-- relatorio:inicio -->
**Resultado do `testar` completo, com `--hw --auditoria`, em 2026-09-29: TUDO CERTO (9 de 9 passos, nenhum pulado).**

| Passo | Resultado | Detalhe | Tempo |
|---|---|---|---|
| Python: lint e formatação (Ruff) | Passou | | 3,0 s |
| Python: tipos (mypy `strict`) | Passou | 37 arquivos, sem problemas | 2,6 s |
| Python: testes e cobertura (pytest) | Passou | **299 testes**; cobertura **97%** (mínimo 80%) | 72 s |
| Frontend: lint (ESLint e acessibilidade dos templates) | Passou | | 14,3 s |
| Frontend: testes e cobertura (Vitest) | Passou | **140 testes**; cobertura **89%** das instruções (mínimo 70%) | 42 s |
| Frontend: build de produção | Passou | carregamento inicial de 347,9 kB (99,1 kB transferidos); build em 9,4 s | 17,4 s |
| Ponta a ponta (Playwright no Edge) | Passou | 174 execuções: **154 passaram, 20 pulados por desenho, 0 falharam** | 416 s |
| Hardware real (`pytest -m hw`) | Passou | o coletor rodou de verdade nesta máquina, completo e leve, e o JSON respeitou o contrato | 70,5 s |
| Auditoria de dependências | Passou | `pip-audit` (dependências de execução): nenhuma vulnerabilidade conhecida; `npm audit` (todo o frontend, todos os níveis): 0 vulnerabilidades | 73,9 s |

Esta é a execução **final**, feita depois de todas as mudanças de código da fase (a anterior serviu para achar o problema do hook, ver o bug 12).

**Cobertura.** Backend: 97% (linhas e ramos; o passo falha abaixo de 80%). Frontend: 88,9% das instruções, 88,9% dos ramos, 76,7% das funções e 90,0% das linhas (o passo falha se qualquer uma ficar abaixo de 70%; a trava foi provada, veja abaixo). Os arquivos de configuração e de rotas do Angular (`app.config.ts`, `app.routes.ts`) ficam de fora dos testes unitários e são exercitados pelo ponta a ponta.

**Testes criados nesta fase**

| Camada | Arquivos | Testes |
|---|---|---|
| Backend (pytest) | 12 em `backend/tests` | 299, mais 1 de hardware real (`-m hw`, fora da execução normal) |
| Frontend, unitários (Vitest) | 11 `*.spec.ts` | 140 (inclui 52 pares de contraste de cor) |
| Ponta a ponta (Playwright, Edge) | `frontend/e2e/app.spec.ts` | 58 cenários × 3 tamanhos de tela = 174 execuções |

Os **20 pulados** são por desenho, não por falha: o tema escuro não é repetido no tablet (11) e nove cenários só fazem sentido em um tamanho de tela (gaveta só abaixo de 900 px, trilho de ícones só entre 900 e 1279 px, alvos de toque e tabelas em cartões só no celular, teclado só no computador e no tablet).

**Provas de que as travas funcionam** (não basta o teste existir; ele precisa falhar quando o defeito volta):
- limite de cobertura: com o mínimo temporariamente em 99%, o passo terminou com código 1 e a mensagem "Coverage … does not meet global threshold";
- CSS crítico bloqueado pela CSP: religando o defeito no build, o teste "a folha de estilos e as fontes estão ativas" falhou com `media="print"`;
- acessibilidade da lista de logs: o axe falhou no celular antes da correção e passou depois.

**Avisos conhecidos (não impedem nada):** o Starlette avisa que `starlette.testclient` com `httpx` está obsoleto e pede `httpx2` (tratar quando atualizarmos as dependências); o Node avisa que `NO_COLOR` é ignorado quando `FORCE_COLOR` está definido (vem do Playwright).
<!-- relatorio:fim -->

### Bugs que os testes e a revisão acharam durante a fase (todos corrigidos, cada um com teste de regressão)

| # | Problema | Como foi achado | Teste que o segura |
|---|---|---|---|
| 1 | Rota do app aberta direto (`/status/maquina`) dava 404 ao recarregar | pytest | `test_api::TestFrontendEstatico::test_serve_o_build_e_cai_no_index_nas_rotas_do_app` |
| 2 | `/api/nao-existe` devolvia a página do app (no Windows o caminho vinha com `\`) | pytest | o mesmo teste |
| 3 | O log "Concluído" do job era gravado depois do estado final | pytest | `test_worker_events::TestWorker::test_executa_ate_o_fim`, `test_api::test_fluxo_completo_com_worker` |
| 4 | A página Status quebrava inteira se o banco falhasse | pytest | `test_status_capacidades::TestStatus::test_banco_com_problema_vira_erro` |
| 5 | Radeon 780M não era reconhecida como `gfx1103` (expressão regular) | pytest | `test_perfil::TestNormalizacao::test_estimar_gfx_amd` |
| 6 | A CSP estrita bloqueava o `onload` do CSS crítico inline do Angular: a folha de estilos nunca ativava (menu sem estilo, link "Pular" visível) | navegador (screenshot e E2E) | E2E "a folha de estilos e as fontes estão ativas" (**provado**: religando o defeito, o teste falha com `media="print"`) |
| 7 | Texto de erro com contraste 4,33:1 (< 4,5:1) | Vitest de contraste | `contrast.spec.ts` (52 pares) |
| 8 | A lista de logs rola sozinha e o teclado não chegava nela (axe: `scrollable-region-focusable`, no celular) | axe no E2E | E2E axe `/status/logs` e Vitest `LogsPage › a lista rola sozinha…` |
| 9 | O título da aba não acompanhava a troca de idioma (só na próxima navegação) | revisão | Vitest `title.strategy.spec` e E2E "trocar para English…" |
| 10 | "Claude: conectado" aparecia só porque o Claude Code estava logado na máquina, embora o app não se conecte a nada até a Fase 2 | revisão final contra o briefing 15.2 | `test_status_capacidades` (2 testes), `test_api::test_status_lista…` e E2E "o Claude logado na máquina não aparece como conectado" |
| 11 | Dois testes E2E estavam mal escritos (procuravam o menu escondido na gaveta; tabulavam além do último elemento da página) | E2E em tablet e celular | corrigidos; o de foco agora exige percorrer ao menos 5 elementos |
| 12 | O hook de pre-commit barrava tudo com 123 erros de fixture quando rodado pelo Git Bash: o `TEMP` virava `/tmp` e o pytest perdia a pasta temporária | ao testar o hook de verdade | `test_scripts::TestPastaTemporaria` (o `testar` usa `tmp/testar-<pid>` dentro do projeto) e o próprio hook passando no Git Bash |
| 13 | Foco do teclado **invisível** dentro da barra lateral: o anel comum é de tinta e a barra também (1:1 no tema claro) | teste de contraste (par foco × barra) | `contrast.spec` (a regra `.sidebar :focus-visible` existe e usa Girassol) e E2E "o foco do teclado é visível dentro da barra lateral" |
| 14 | O logo aparecia duas vezes na barra (a classe de exibição do componente vencia o `hidden`) | revisão das capturas | `app.spec` "mostra a marca uma vez só" e E2E "a marca aparece uma vez só" (3 tamanhos) |
| 15 | A página 404 repetia o título (h1 e h2) | Vitest | `pages.spec` "a página 404… uma vez só" |
| 16 | Linguagem de desenvolvimento na interface ("Chega na Fase N", campo `phase` na API, textos do benchmark com "Fase 3", "Fase 5") | pedido do Vitor e revisão do benchmark | `test_api::test_meta`, `test_medidores` ("sem falar de fase"), `pages.spec`, E2E "nenhuma página fala em Fase" (11 páginas × 3 tamanhos) |
| 17 | A tela Modelos só mostrava o tamanho depois de instalado: o usuário não sabia o que ia baixar | ao escrever o E2E | `test_ferramentas::test_antes_de_instalar_mostra_o_tamanho_aproximado_do_download`, `modelos.page.spec` |
| 18 | O link "Ver as vozes" abria Modelos mas **não rolava** até o grupo (a lista carrega depois da navegação) | E2E "a etapa de áudio leva direto ao grupo das vozes" (falhou nos 3 tamanhos) | o mesmo E2E e `modelos.page.spec` "chegada por link com âncora" |
| 19 | O diagnóstico não enxergava o ffmpeg instalado em `tools/` (só olhava o PATH) e o modo leve reaproveitava a coleta antiga: o Status continuaria "não instalado" | ao planejar a instalação pela tela | `test_coletores` (3 rápidos e a coleta real com `--hw`) |
| 20 | Uma barra invertida mal escapada num script gerador corrompeu o caminho `tools
fmpegin` do `.ps1` (`
` e ``) | conferência do resultado | `test_coletores::test_ps1_nao_tem_caracteres_de_controle` |
| 21 | "Instalação incompleta" aparecia para um motor que o usuário nunca instalou (as bibliotecas Python contavam como parte dele) | captura do Status | `test_ferramentas::TestMotoresNoStatusENasCapacidades` (4 testes novos) |
| 22 | A matriz mandava "abrir Modelos e instalar" para a música, que não existe na lista de Modelos | revisão | `test_medidores::test_musica_nao_manda_instalar_o_que_nao_existe_em_modelos` |
| 23 | O benchmark dizia "modelo de imagem ainda não instalado" com o modelo instalado; agora mede de verdade | revisão | `test_medidores` (medidores, runner e matriz) e a suíte real `--hw` |
| 24 | Dois testes dependiam de sorte no tempo: um corria contra o worker (criar e cancelar o job de demonstração) e o E2E das fontes olhava a lista de fontes uma vez só; cada um falhou uma vez sob carga | repetição sob carga | ambos passaram a **esperar a condição** (`test_benchmark_handlers` sem a corrida; E2E com `expect.poll`), sem pausa fixa |
| 25 | "Pendências do ambiente" mandava criar um ambiente virtual que já existe e trazia um aviso do Ollama que não pede nenhuma ação | captura da tela Sua máquina | `test_perfil::TestFerramentasPendentes` (lê o `pyvenv.cfg` do projeto; o aviso saiu da lista) |
| 26 | O benchmark aparecia em ordem alfabética (Recorte, Imagem, LLM, Música, Voz, Vídeo) | captura da tela Sua máquina | FE `status-pages.spec` "na ordem em que o benchmark mede" |
| 27 | Números do benchmark saíam com ponto decimal ("4.89 s") e a música dizia "ainda não instalado" sem existir na lista de Modelos | revisão do app real | `test_medidores` (vírgula decimal) e o texto "Ainda não disponível" do Status |

---

## Matriz de rastreabilidade: Fase 1

Status: **Passa** = coberto e verde no `testar` do dia; **Parcial** = coberto, com um limite dito na coluna; **Manual** = verificado à mão, com o resultado registrado.
Abreviações: `BT` = `backend/tests`, `FE` = testes unitários do frontend (Vitest), `E2E` = `frontend/e2e/app.spec.ts` (Playwright no Edge; roda em 3 tamanhos: desktop 1440 px, tablet 820 px e celular 375 px).

### Critérios de aceite da Fase 1 (briefing, seção 14)

| # | Requisito | Testes | Status |
|---|---|---|---|
| A1 | Backend FastAPI sobe **só em 127.0.0.1** e recusa outra configuração | BT `test_config_logging` (host, porta, Ollama local), `test_seguranca::TestServidorReal` (servidor de verdade: recusa subir fora do loopback e só responde em 127.0.0.1) | Passa |
| A2 | SQLite com migrações versionadas, WAL e chaves estrangeiras | BT `test_db_store::TestDatabase` | Passa |
| A3 | Fila de jobs: um por vez, prioridade e ordem, pausar, retomar, cancelar, reordenar | BT `test_db_store::TestJobStore`, `test_worker_events::TestWorker`, `test_api::TestJobs`; FE `jobs.service.spec`, `pages.spec › FilaPage`; E2E `Fila` | Passa |
| A4 | Fila **persistente**: sobrevive a reinício; job interrompido volta para a fila | BT `test_recuperar_apos_reinicio`, `test_sobrevive_a_um_novo_store_no_mesmo_banco`, `test_job_interrompido_por_reinicio_e_refeito`; E2E "a ordem da fila… continua depois de recarregar" | Passa |
| A5 | Progresso em tempo real (SSE) e ETA | BT `TestEventBus`, `TestStreamSse`, `test_progresso_calcula_eta_e_ignora_repeticao`; FE `JobsService`; E2E "job de demonstração: aparece ao vivo, pausa, retoma e cancela" | Passa |
| A6 | Logs estruturados por job e por serviço, com segredos mascarados | BT `test_config_logging::TestLogs`, `TestMascara`, `test_logs_do_job`, `test_logs_com_filtros_e_validacao`; FE `LogsPage`; E2E "Ver logs abre os logs já filtrados" | Passa |
| A7 | Shell do frontend com a **navegação da seção 10** (9 itens, logo no topo) e o indicador "Claude" fixo no topo | FE `app.spec` (menu na ordem do briefing, Claude, gaveta, tema, idioma); E2E "navegação e integridade" (11 rotas × 3 tamanhos: título, sem erro de console, sem rolagem horizontal) | Passa |
| A8 | **Marca aplicada**: tokens, Fredoka, Fraunces e Nunito Sans locais, favicon | FE `contrast.spec` (62 pares WCAG, 31 por tema); E2E "a folha de estilos e as fontes estão ativas", "não carrega nada de fora" | **Parcial**: os 4 arquivos oficiais de `marca/` não existem nesta máquina; o logo é um texto em Fredoka e o ícone é provisório (D-014, D-027). Não dá para testar o logo oficial |
| A9 | Status: cada serviço com estado em **texto e ícone** e "como corrigir" | BT `test_status_capacidades::TestStatus`, `test_api::TestSistema`; FE `ServicosPage`; E2E `Status dos serviços` | Passa |
| A10 | "Sua máquina": perfil, justificativa, hardware detectado, aceleração | BT `test_perfil` (perfis A, B, C e D; validação; normalização; ferramentas pendentes), `test_relatorio`, `test_cli_perfil`, `test_api::test_maquina_*`; FE `MaquinaPage`; E2E `Sua máquina` | Passa |
| A11 | **Matriz de capacidades** (21 funcionalidades) correta por perfil; indisponível aparece com o motivo, nunca quebrada | BT `test_status_capacidades::TestCapacidades` (perfis A, B, C, D; sem ffmpeg; sem Node; Claude; ETA medido × estimado), `TestEstadoDoHardware`; FE `MaquinaPage` (filtro e contagens); E2E `Sua máquina` (21 linhas, filtro) | Passa |
| A12 | **Benchmark de calibração** que ajusta a matriz | BT `test_benchmark_handlers` (`TestMedirLlm`, `TestBenchmarkStore`, `TestHandlers`, `TestOllamaClient`), `test_medidores` (medidores, runner e matriz), `test_api::test_benchmark_roda_e_alimenta_a_matriz`; suíte real `--hw` (voz, recorte e imagem de verdade) | Passa: mede **LLM, voz, recorte de fundo e uma imagem** de verdade (ver "Verificações manuais"). **Música e animação por IA** aparecem como "não medido" (o gerador de música não está instalado); os tempos variam com a carga do notebook |
| A13 | Diagnóstico da máquina em Windows, Linux e macOS | BT `test_coletores::TestSintaxeDosColetores` (sintaxe, BOM, fim de linha, ajuda), `test_perfil` (hardware **simulado** para cada perfil e sistema), suíte real `pytest -m hw` | **Parcial**: o `.ps1` roda de verdade no Windows; o `.sh` foi validado só por **simulação** (bash do Git imitando Linux e macOS), nunca numa máquina Linux ou macOS real |
| A14 | Script de inicialização que sobe tudo | teste manual de `iniciar.bat` (ver "Verificações manuais") | Manual |
| A15 | `testar` roda tudo e mostra um resumo claro | o próprio `testar` | Passa |

### Segurança (briefing, seções 11 e 12.4)

| # | Requisito | Testes | Status |
|---|---|---|---|
| B1 | Tudo só em 127.0.0.1; cabeçalho `Host` estranho é recusado | BT `test_seguranca::TestRedeEOrigem` (`test_host_estranho_e_recusado`, `test_hosts_locais_passam`), `TestServidorReal` | Passa |
| B2 | Outro site não consegue **disparar** ações no servidor local (CSRF) | BT `test_post_de_outro_site_e_barrado_mesmo_sem_cors`, `test_post_do_proprio_app_ou_de_ferramentas_locais_passa`; E2E "um site qualquer não consegue disparar ações no servidor local" (navegador de verdade) | Passa |
| B3 | CORS só para o frontend local; outro site não lê respostas | BT `test_cors_so_libera_o_frontend_local` | Passa |
| B4 | Cabeçalhos de segurança e **CSP estrita** (sem CDN) | BT `test_cabecalhos_de_seguranca`; E2E "a resposta traz política de segurança de conteúdo estrita" | Passa |
| B5 | Nenhum recurso externo, sem telemetria, sem documentação interativa com CDN | E2E "a interface não carrega nada de fora (11 páginas)", "a documentação interativa… não está exposta"; BT `test_openapi_existe_e_a_pagina_de_docs_com_cdn_nao` | Passa |
| B6 | Path traversal, zip slip, links simbólicos e nomes de arquivo maliciosos | BT `TestCaminhos`, `test_ferramentas::TestZip` | Passa (usado pelo instalador de modelos; uploads e pacotes `.fabulim` chegam depois) |
| B7 | Downloads só de fonte oficial, com SHA-256; só `.safetensors`/GGUF/ONNX, nunca pickle | BT `TestDownloads`, `test_ferramentas` (`TestCatalogo`, `TestResolucao`, `TestDownload`, `TestInstalar`) | Passa (usado pelo instalador; ver F1 a F6) |
| B8 | Uploads: tipo real pelo conteúdo, tamanho | BT `TestUploads` | Passa (idem) |
| B9 | Sem `shell=True`, `eval`, `exec`, `pickle`; os coletores não executam texto externo | BT `TestCodigoPerigoso` (varre o código do app e os scripts) | Passa |
| B10 | **Credenciais do Claude**: não ler arquivos de credencial, sem OAuth próprio, sem client ID; só `claude auth status` | BT `TestCredenciaisDoClaude` (varre backend, scripts e frontend) | Passa |
| B11 | Chaves e tokens mascarados em logs, erros e respostas | BT `TestMascara`, `TestLogs`, `test_falha_fica_registrada_e_sem_segredo`, `test_finalizar_done_failed_e_mascara_do_erro`, `test_erro_interno_nao_vaza_detalhes` | Passa |
| B12 | Dependências fixadas e sem vulnerabilidade alta ou crítica | `requirements*.txt` e `package-lock.json` fixados; `testar --auditoria` (`pip-audit` e `npm audit`) | Passa (2026-09-29): `pip-audit` sem vulnerabilidades conhecidas; `npm audit` com 0 vulnerabilidades. A auditoria roda com `testar --auditoria` e exige internet |
| B13 | Prompts e saídas de LLM tratados como dado não confiável; filtro de conteúdo; injeção de prompt | — | Pendente: **Fase 2** (não há LLM nem prompts ainda) |

### Resiliência (briefing 12.4)

| # | Requisito | Testes | Status |
|---|---|---|---|
| C1 | Serviço externo fora do ar (Ollama) não derruba o app | BT `test_status_com_ollama_fora_do_ar`, `test_calibracao_com_ollama_fora_do_ar_nao_falha`, `test_ollama_fora_do_ar_e_sem_modelos`, `TestOllamaClient` | Passa |
| C2 | Banco com problema vira "erro" em vez de derrubar a página | BT `test_banco_com_problema_vira_erro` | Passa |
| C3 | Subprocesso com tempo limite e cancelamento | BT `TestExecutarProcesso` | Passa |
| C4 | Falha de job fica registrada; tipo desconhecido não derruba o worker | BT `test_falha_fica_registrada_e_sem_segredo`, `test_tipo_desconhecido_falha_sem_derrubar_o_worker` | Passa |
| C5 | Servidor de eventos: cliente que desconecta, fila cheia, vários assinantes | BT `TestEventBus`, `TestStreamSse` | Passa |
| C6 | Falta de memória (OOM) com nova tentativa em configuração menor | — | Pendente: **Fase 3** (só existe com modelos de geração) |

### Acessibilidade e interface (briefing 12.5 e seção 10)

| # | Requisito | Testes | Status |
|---|---|---|---|
| D1 | **axe-core** (WCAG 2.1 A e AA) nas páginas, sem violações | E2E "acessibilidade": 11 páginas × tema claro e escuro × 3 tamanhos (55 verificações) | Passa |
| D2 | Contraste AA dos tokens, nos dois temas | FE `contrast.spec` (62 pares, 31 por tema, mais 3 verificações; Girassol e Menta nunca como texto no claro) | Passa |
| D3 | Teclado: "Pular para o conteúdo", foco visível de 3 px em todo elemento (**inclusive dentro da barra lateral**), gaveta com foco preso e `Esc`, seletores com setas, acordeão com Enter e Espaço | E2E "tema, idioma e teclado", "responsivo" e "Status dos serviços"; FE `ui.spec` (segmentado), `app.spec` (gaveta), `status-pages.spec` (acordeão) | Passa |
| D4 | Responsivo: barra lateral (≥ 1280 px), trilho de ícones (900 a 1279 px), gaveta (< 900 px); tabelas viram cartões; alvos de toque de 44 px; sem rolagem horizontal | E2E "responsivo" (5 testes) e "navegação e integridade" | Passa |
| D5 | "Reduzir movimento" respeitado | E2E "respeita 'reduzir movimento'" | Passa |
| D6 | Tema claro e escuro, lembrados | FE `theme.service.spec` (6); E2E "o tema escolhido vale na hora e continua depois de recarregar" | Passa |
| D7 | Idioma PT-BR e EN: toda chave existe nos dois dicionários, com os mesmos marcadores, sem chave sobrando; o título da aba acompanha | FE `i18n.spec` (9), `title.strategy.spec` (3); E2E "trocar para English" | Passa |
| D8 | Estados vazio, carregando e com erro em português simples | FE `pages.spec`, `status-pages.spec` | Passa |
| D9 | Regressão visual das telas principais | `e2e/capturas.spec.ts` só **gera** capturas (10 páginas × 3 tamanhos × 2 temas = 60, quando `FABULIM_CAPTURAS` aponta uma pasta) para olhar; não compara | **Parcial**: sem comparação automática (é opcional no briefing) |
| D10 | Atalhos de teclado do fluxo de criação (A, R, ← →, Espaço, Ctrl+V) | — | Pendente: **Fases 4 a 9** (dependem das telas de aprovação) |

### Instalador de programas e modelos, tela Modelos (D-034; pedido do Vitor em 2026-09-29)

| # | Requisito | Testes | Status |
|---|---|---|---|
| F1 | O catálogo só tem fontes oficiais (GitHub Releases, Hugging Face), com licença de uso comercial e o tamanho do download informado | BT `test_ferramentas::TestCatalogo`, `test_todo_item_do_catalogo_informa_o_tamanho_do_download` | Passa |
| F2 | O endereço, o tamanho e o **SHA-256** vêm da própria fonte; **sem hash publicado o item não é instalado**; o Hugging Face é fixado no commit | BT `TestResolucao` | Passa |
| F3 | Download seguro: só HTTPS, redirecionamento só para host oficial, retoma de onde parou (Range), progresso, checagem de espaço antes | BT `TestDownload`, `test_pouco_espaco_em_disco_avisa_antes_de_baixar` | Passa |
| F4 | Hash diferente apaga o arquivo e falha; formato perigoso (pickle) é recusado; as vozes do Kokoro provam ser dados puros | BT `test_hash_diferente_apaga_o_arquivo_e_falha`, `test_formato_perigoso_e_recusado`, `test_vozes_com_codigo_escondido_sao_barradas` | Passa |
| F5 | Extração segura de `.zip` (zip slip, link simbólico, bomba de descompressão) | BT `TestZip` | Passa (o de link simbólico é pulado onde o sistema não deixa criar link) |
| F6 | Só instala por clique do usuário, item do catálogo, id validado, sem duplicar o job, e nunca a pedido de outro site (CSRF) | BT `TestApiDasFerramentas`; E2E "o servidor só aceita instalar itens do catálogo" | Passa |
| F7 | A instalação é um job da Fila, com progresso; erro em português; roda o diagnóstico leve no fim | BT `TestHandlerDeInstalacao` | Passa |
| F8 | Os motores instalados aparecem no Status e na matriz; ausente ensina onde instalar; incompleto só quando já há arquivo do motor | BT `TestDeteccao`, `TestMotoresNoStatusENasCapacidades` | Passa |
| F9 | Tela **Modelos**: grupos, para que serve, licença, tamanho (aproximado antes de instalar), Instalar e Instalar tudo, progresso no item, avisos de pronto ou falha, rola até o grupo do link `#voz` | FE `modelos.page.spec` (15), `api.service.spec`, `format.spec`; E2E "Modelos" (3, com a instalação simulada), "a tela de Modelos abre direto no grupo das vozes" | Passa |
| F10 | O coletor de diagnóstico enxerga o ffmpeg de `tools/` (e o modo leve refaz essa detecção) | BT `test_coletores` (3 rápidos e a coleta real com `--hw`) | Passa |
| F11 | Instalação **de verdade** (download real, com hash) | feita à mão em 2026-09-29 pelo `scripts/instalar.py` (ver "Verificações manuais") | Manual: os testes automáticos usam servidor de mentira e nunca baixam nada |
| F12 | Os motores instalados **funcionam**: ffmpeg, voz, recorte e imagem rodam de verdade | suíte real `--hw` (`test_medidores::TestMedidoresNaMaquinaReal`); o benchmark do app | Passa (só nesta máquina; ver Limites) |

### Linguagem de produto, visual e páginas (D-032 e D-033; pedido do Vitor em 2026-09-29)

| # | Requisito | Testes | Status |
|---|---|---|---|
| G1 | **Nenhuma página fala em "Fase"** (é linguagem de quem desenvolve); o campo `phase` saiu da API | FE `pages.spec` (Configurações, recursos, Criar vídeo), `app.spec`; BT `test_api::test_meta`, `test_status_capacidades` ("Fase" não aparece nos motivos), `test_medidores`; E2E "nenhuma página fala em Fase" (11 páginas × 3 tamanhos) | Passa |
| G2 | As sete etapas de "Criar vídeo" são **links**: a primeira leva ao formulário do enredo e as outras aos Projetos, onde cada uma é feita | FE `pages.spec` ("cada etapa do caminho é um link", em português e em inglês); E2E "Criar vídeo: o formulário e o caminho do enredo ao vídeo" (5 cenários) | Passa |
| G3 | Cada página de recurso explica para que serve, como funciona e como se comporta neste computador | FE `pages.spec` ("páginas dos recursos") | Passa |
| G4 | Status agrupa "Precisam de atenção", "Funcionando" e "Ainda não ativos"; "Como corrigir" é um acordeão acessível (Angular Aria) | FE `status-pages.spec`; E2E "Status dos serviços" (mouse, toque e teclado) | Passa |
| G5 | Ao lado de cada tempo a tela diz se ele foi **medido** ou é **estimativa** | FE `pages.spec`, `status-pages.spec`; BT `test_medidores::TestCapacidadesMedidas` | Passa |
| G6 | O visual "papel e tinta" (Tailwind exclusivo, Angular Aria e CDK sem estilo, três famílias de fonte locais) | E2E "a folha de estilos e as fontes estão ativas" (as três famílias carregam do próprio app), "a marca aparece uma vez só", "o foco do teclado é visível dentro da barra lateral", "cada página tem um único título principal"; revisão das 60 capturas | Passa (a revisão visual é manual) |
| G7 | A lista de "Pendências do ambiente" só traz o que o usuário pode fazer (o Python do sistema não conta quando o app já roda no do projeto) | BT `test_perfil::TestFerramentasPendentes` | Passa |

### Fila e monitoramento (briefing 7.9): o que ficou de fora da Fase 1

| # | Requisito | Status |
|---|---|---|
| E1 | Indicador de uso de CPU, memória e GPU, conforme o que a máquina permitir medir | Pendente (proposta: Fase 2, junto com os primeiros jobs reais) |
| E2 | Notificação no navegador, com som opcional, quando um job terminar ou falhar | Pendente (proposta: Fase 2) |
| E3 | Fila noturna | **Feito** (H6): lista o próximo trabalho liberado pelas aprovações e enfileira um por projeto; nunca aprova |

---

### Ferramentas de criação (pedido do Vitor em 2026-09-30: "preciso que todas as ferramentas funcionem... e que funcione baseado na minha máquina")

Personagens, Gerar imagem, Clipes, Criar vídeo e Projetos (as sete etapas, miniaturas, textos do YouTube, versões, fila noturna e pacote `.fabulim`) funcionam de ponta a ponta neste notebook. Foram verificados em **quatro camadas**:

1. **Backend (pytest)**: os motores de IA são substituídos por falsos e determinísticos (`backend/tests/fakes_motores.py`); o **ffmpeg de verdade** roda nos testes que dependem dele (vídeo H.264 válido, duração, tamanho, som, legendas).
2. **Frontend (Vitest)**: cada página, cada etapa do projeto e cada componente novo.
3. **Ponta a ponta (Playwright no Edge)**: o projeto `ferramentas` sobe um **segundo servidor** (`frontend/e2e/servidor_falso.py`, porta 8878) com o app de verdade, o ffmpeg de verdade e imagem, recorte e voz falsos, e percorre pela interface **do personagem ao vídeo final**: cria a Lila com o prompt de exemplo, gera variações, escolhe a principal, gera a folha e ouve a voz; cria a versão 3D; envia uma imagem própria (e recusa um arquivo que não é imagem); gera imagens e as apaga; faz um clipe rápido, muda o formato, une e continua a partir dele (e recusa um "vídeo" falso); cria o projeto pelo enredo de exemplo e passa pelas sete etapas aprovando cada uma; gera as miniaturas, os textos e o pacote `.fabulim`; cria a versão sem traduzir e a versão em vídeo longo; importa o pacote (e recusa um arquivo que não é pacote); confere a fila noturna; e roda o **axe** em todas essas páginas e em cada etapa, nos dois temas.
4. **Uso real, à mão, com os motores de verdade** (FLUX.2 klein pela placa integrada, Kokoro, BiRefNet, `qwen3:4b` e ffmpeg): o mesmo percurso pela interface, com o projeto "A Lila e a estrelinha que se perdeu": roteiro de 3 cenas, três cenários, animação, áudio, montagem (vídeo 1080×1920 H.264 e AAC, 33 s, -14,4 LUFS, pico -1,4 dBFS), miniaturas, textos em PT e EN, pacote de 2,2 MB exportado e reimportado, versão em inglês traduzida pelo modelo local, versão em vídeo longo, clipe rápido, unir e outro formato. **Tempos medidos em [MODELOS.md](MODELOS.md#medido-no-uso-real-das-ferramentas-2026-09-30).** Os frames de cada animação e as miniaturas foram conferidos a olho.

| # | Requisito | Testes | Status |
|---|---|---|---|
| H1 | **Personagens**: criar por descrição, prompt ou imagem própria; 1 a 4 variações; escolher a principal (o fundo é recortado sozinho); folha de poses e expressões em PNG transparente com "Olha para"; voz de teste; versão 2D/3D; apagar; exportar e importar a biblioteca | BT `test_personagens`, `test_pacote`; FE `ferramentas-a.spec` (Personagens e Personagem); E2E "Personagens" (3) e "Personagens: outros jeitos de criar" (3) | Passa (real: variação 90 s, recorte 26 s, pose 3 min) |
| H2 | **Gerar imagem**: formulário e prompt técnico, até 3 personagens de referência, "gerar parecida", variações ao vivo, biblioteca com busca e apagar, tela grande | BT `test_imagens`, `test_midias`; FE `ferramentas-a.spec` (Imagem), `ui/ferramentas.spec` (visualizador e miniatura); E2E "Gerar imagem" (2) | Passa |
| H3 | **Prompts** (personagem, enredo, imagem) em formato estruturado e em texto livre, com histórico; tipo errado avisa; texto do usuário é dado, nunca ordem | BT `test_prompts`, `test_api_midias_prompts`, `test_conteudo`; FE `ui/ferramentas.spec` (caixa de prompt); E2E (exemplos das três páginas) | Passa (o texto livre depende do Ollama: só testado com o modelo falso e no uso real) |
| H4 | **Clipes**: rápido, unir com transição, outro formato, continuar, enviar vídeo conferido com ffprobe | BT `test_clipes`, `test_montagem`; FE `ferramentas-a.spec` (Clipes); E2E "Clipes" (3) | Passa (real: clipe de 4 s em 112 s, unir 52 s, outro formato 12 s) |
| H5 | **As sete etapas** com aprovação (nada avança sem aprovar; reabrir não apaga), roteiro pelo modelo local e simples, cenas com versões, storyboard por camadas com posição, animação por código, áudio (vozes, música por código, efeitos, SRT), montagem em -14 LUFS, revisão com checklist | BT `test_projetos`, `test_api_projetos`, `test_producao`, `test_animacao`, `test_audio`, `test_montagem`; FE `ferramentas-b.spec`; E2E "Criar vídeo e o projeto, etapa por etapa" (8) | Passa (real: vídeo final de 33 s; animação 125 s) |
| H6 | **Entrega**: miniaturas 1280×720 sem logo, título/descrição/tags em PT e EN dentro dos limites do YouTube, versão em outro idioma, versão Short/longo, **fila noturna** que nunca aprova | BT `test_entrega`; FE `ferramentas-b.spec` (revisão e fila noturna); E2E (revisão, versões e fila noturna) | Passa |
| H7 | **Pacote `.fabulim`**: exportar e importar projeto e personagens; zip slip, links, bomba de compressão, hash, tipo real, ids refeitos, nada sobrescrito, desfaz se falhar | BT `test_pacote`; FE `ui/ferramentas.spec` (importar); E2E "importar o pacote" (válido e inválido) | Passa (real: exportado e reimportado) |
| H8 | **Sem o modelo de texto tudo continua**: roteiro simples, modelo pronto, versão sem traduzir; o modo com IA mostra o motivo | BT (503 com a mensagem); E2E (o servidor de motores falsos não tem modelo de texto) | Passa |
| H9 | **Acessibilidade** das telas novas e de cada etapa, nos dois temas | E2E "acessibilidade das ferramentas" (6 telas × 2 temas, mais o percurso por todas as etapas do projeto em cada tema) | Passa |
| H10 | O que o notebook **não faz** diz por quê e oferece a saída (animação por IA: exportar para o desktop) | BT `test_medidores` (matriz); E2E ("Animação por IA (imagem em vídeo) não roda neste computador") | Passa |

**Bugs que os testes e o uso real acharam nesta rodada** (todos corrigidos, cada um com o teste que o segura):

| # | Problema | Como foi achado | Teste que o segura |
|---|---|---|---|
| 28 | O roteiro pelo modelo local dava o **título do vídeo a todas as cenas** | uso real | BT `test_projetos::TestNormalizarRoteiro` (4 testes de título) |
| 29 | Ao apagar uma imagem ou um clipe o **contador da biblioteca caía duas vezes** (o evento do servidor chega antes da resposta do pedido) | E2E "Gerar imagem" | FE `apagar não conta duas vezes quando o evento do servidor chega antes da resposta do pedido` (imagens e clipes) |
| 30 | No **tema escuro**, passar o mouse na etapa atual do projeto deixava o texto ilegível (o `hover` vencia o estilo da etapa atual: Anil sobre `--wash`) | axe no E2E | `contrast.spec` (a etapa atual mantém o texto legível com o mouse) e o axe por etapa nos dois temas |
| 31 | A animação levava **269 s** para 33 s de vídeo em 1080p: a câmera usava uma transformação afim por quadro e os quadros eram desenhados um de cada vez | medição no uso real | BT `test_animacao` (a câmera por recorte equivale à transformação afim; vários desenhistas dão os mesmos quadros na mesma ordem; parar solta os desenhistas). Agora **125 s** |
| 32 | "3 cena(s)", "Gerar 1 variações", "Aprovar as 1 cenas" na tela | uso real | FE `i18n.spec` (plural `{n#singular\|plural}`) e as páginas |
| 33 | O job da versão em outro idioma se chamava "Versão em EN"; as tarefas de miniaturas, textos e versão apareciam sem nome na Fila | uso real | BT `test_entrega`; FE `i18n.spec` (chaves dinâmicas) |
| 34 | O ffmpeg **falso** dos testes deixava um arquivo `-` na pasta do projeto (o `-f null -` da medição de volume) | `git status` | `fakes_motores` não grava quando a saída é `-` |
| 35 | Os testes E2E antigos de "Criar vídeo" seguiam o desenho da fase anterior | rodada do E2E | reescritos em `e2e/app.spec.ts` |
| 36 | Dois testes de tempo do worker dependiam do relógio de verdade: `test_pausa_segura_o_progresso_e_retoma` esperava só 15 s pelo fim de 120 passos que, com o computador carregado, passam disso, e `test_progresso_calcula_eta_e_ignora_repeticao` dormia 1,1 s e exigia um ETA menor que 3 s. Um deles derrubou uma bateria completa (1 de 1.205) e passou na repetição | a bateria completa sob carga (um agente de inventário do Windows ocupa ~1 núcleo) | o de progresso agora usa um **relógio falso** (e confere também que passados 0,1 s ele regrava); o da pausa espera até 120 s pelo fim; `test_so_responde_em_127_0_0_1` espera até 120 s pelo servidor subir |
| 37 | O passo "enviar uma imagem sua" do E2E das ferramentas estourou os 10 s padrão para ir à página do personagem criado (o servidor gravou arquivos com o notebook ocupado) | a bateria completa | o projeto `ferramentas` espera 20 s por padrão e 45 s ao navegar depois de criar |
| 38 | Quando um passo do `testar` falhava, a **tabela de cobertura** ocupava o fim da saída e o teste que falhou não aparecia (nem constava do resumo do pytest, porque o `-rs` tirava o `fE` do padrão) | a bateria completa | `test_scripts::TestSaidaDosPassosQueFalharam`: o pytest roda com `-rfEs --tb=short`, a tabela é cortada e a saída completa fica em `tmp/testar-ultimo/` |

---

## O que ainda não existe (briefing, seção 12.3)

Estas linhas **não têm testes porque ainda não foram construídas**; entram na matriz quando forem, e a fase só fecha com elas verdes.

| Área | Situação |
|---|---|
| **Claude** (conectar e desconectar, `AIRouter` com preferência por tarefa, fallback para o local, selo de origem "Claude" ou "Local", contador de uso) | Não construído (Fase 2). O botão de conectar está desativado e o chip diz "desconectado" |
| Monitor de CPU, memória e GPU e **notificação do navegador** quando um job termina (briefing 7.9, itens E1 e E2) | Não construído (Fase 2) |
| **Atalhos de teclado** do fluxo de criação (A, R, ← →, Espaço, Ctrl+V) e a **similaridade de personagem entre cenas** por embeddings (briefing 12.3) | Não construídos. A consistência vem da construção (o mesmo PNG em toda cena), mas não é medida por similaridade |
| **Modelo de visão** (descrever a imagem enviada) | Não instalado: a imagem enviada não é descrita sozinha |
| **Música com letra cantada** (ACE-Step) | Não instalada (pesada, licença a conferir): a música é instrumental por código |
| **Animação por IA** | Indisponível neste perfil (sem GPU dedicada): a saída é a animação por código ou exportar o `.fabulim` para o desktop |
| Auditoria de segurança final e revisão de acessibilidade com leitor de tela | Prevista para o fechamento (o `--auditoria` roda `pip-audit` e `npm audit`) |

---

## Verificações manuais

Coisas que o `testar` não cobre e que eu executei à mão em 2026-09-29, com o resultado:

| Verificação | Como | Resultado |
|---|---|---|
| `iniciar.bat` com o servidor já no ar | rodei `iniciar.bat --sem-navegador` com o servidor da porta 8765 ligado | reconheceu ("O Fabulim já está no ar em http://127.0.0.1:8765"), não subiu um segundo servidor, código 0 |
| `iniciar.bat` subindo do zero | porta 8768 e pasta de dados temporária por variáveis de ambiente, sem diagnóstico automático | servidor no ar em **10,8 s**; `/api/health` ok; `/api/meta` com a porta e a pasta configuradas; a rota `/status/maquina` do app respondeu 200 com a interface; nenhuma mensagem de erro; servidor encerrado e pasta removida no fim |
| Leitura do `.env` | `.env` temporário com `FABULIM_PORT=8767`, `FABULIM_DATA_DIR` e `FABULIM_AUTO_DIAGNOSTICO=0` | o `iniciar.bat` perguntou a porta ao servidor (`servidor.py --porta`), subiu em 8767 com a pasta de dados do `.env` e sem atrapalhar o servidor da 8765; `.env` removido depois |
| `.env` inválido | `FABULIM_HOST=0.0.0.0` | o `iniciar.bat` recusou com "só escuta em 127.0.0.1" e código 1, sem subir nada |
| Hook de pre-commit | ativei com `git config core.hooksPath scripts/hooks` e tentei commitar um arquivo com `import` não usado | o commit foi **barrado em 3 s** (Ruff F401) e o `testar` parou no primeiro erro (`-x`); arquivo de teste removido |
| Revisão visual da versão final | 60 capturas (10 páginas × 3 tamanhos × 2 temas) e o app no navegador, depois do redesenho | layout, estados e textos como projetado; achou o filete duplo abaixo do cabeçalho (corrigido) e o texto "Instalação incompleta" para motor nunca instalado (corrigido, bug 21) |
| Instalação real dos 9 itens do catálogo | `scripts/instalar.py --tudo` (downloads de verdade) | os 9 itens instalados (~5,6 GB), cada um com o **SHA-256 conferido contra o que a fonte publica**; `manifesto.json` de `tools/` e `models/` com origem, hash, tamanho, licença e data |
| ffmpeg instalado | `ffmpeg -version` | n9.0.2 roda; compilação com `--enable-gpl --enable-version3` (licença registrada em `LICENCAS.md`) |
| Voz de verdade | Kokoro em português (`pf_dora`) | 3 vozes em português encontradas; 4,9 s de fala sintetizados em 3,6 s (máquina quieta) e em 4,3 s pelo benchmark do app |
| Recorte de verdade | BiRefNet lite por ONNX Runtime | carrega e recorta uma imagem de 1024 px em ≈ 20 s na CPU |
| Imagem de verdade | FLUX.2 klein 4B + Qwen3-4B + small-decoder por stable-diffusion.cpp | 512×512, 4 passos: **99 s** pela placa integrada (Vulkan) e **764 s** só pela CPU; a imagem (coelho azul num campo de girassóis) saiu correta |
| Benchmark pelo app | "Rodar benchmark de calibração" (duas vezes) | terminou em 3 min 34 s e 4 min; LLM 5,7 e 5,9 tok/s, voz, recorte e imagem "medidos"; matriz passou a mostrar os tempos como medidos; música e vídeo "não medidos" |
| Status depois de instalar | reiniciei o servidor e abri o Status | ffmpeg, motores de imagem, voz e recorte e animação por código "Funcionando" (o diagnóstico leve automático enxergou o ffmpeg); música e Claude "Ainda não ativos"; disco em atenção (57,6 GB livres, abaixo dos 100 GB de conforto) |
| `iniciar.sh` e o hook em shell | `bash -n` (só a sintaxe) | ok; **nunca executados em Linux ou macOS reais** |

**Sobre "todos os serviços funcionando" (critério de aceite da Fase 1):** hoje 10 dos 13 serviços estão "Funcionando" (servidor, banco, fila, diagnóstico, Ollama, ffmpeg e os motores de imagem, voz, recorte e animação por código). Os outros dizem a verdade: a **música** não está instalada (não faz parte da lista de Modelos), o **Claude** ainda não está conectado ao app (Fase 2) e o **disco** está em atenção porque os modelos ocuparam ~5,6 GB dos 57,6 GB livres. Fingir "verde" nesses casos seria mentir; o Status mostra o que falta e como resolver.

## Limites: o que não foi possível testar automaticamente, e por quê

- **Logo e ícone oficiais**: a pasta `marca/` não existe nesta máquina (procurei em Downloads, Desktop, Documents, Pictures, OneDrive e G:). Não há como testar um arquivo que não está aqui.
- **`diagnostico.sh` em Linux e macOS reais**: só foi validado com o bash do Git imitando esses sistemas. A classificação de perfil para Linux e macOS é testada com dados **simulados**, mas a coleta em si nunca rodou nessas plataformas.
- **Benchmark de música e de animação por IA**: não existem (o gerador de música não está instalado e a animação por IA não roda neste computador). A matriz mostra "estimado" nesses casos, nunca um número inventado. **Os tempos medidos variam com a carga do notebook** (o Windows mantém processos de fundo pesados: o LLM deu 10,8 tok/s na Fase 0 e 5,7 a 5,9 pelo app; a imagem, de 78 a 112 s): cada medição é uma amostra, com data.
- **Instalação de verdade nos testes automáticos**: nenhum teste baixa nada (servidor de mentira e, no E2E, a instalação é simulada). A instalação real dos 9 itens foi feita e conferida à mão; o que roda de verdade no `testar --hw` são os motores já instalados.
- **O instalador só tem pacotes de Windows x64** (ffmpeg e stable-diffusion.cpp em `.exe`). Os modelos (`.gguf`, `.onnx`) servem em qualquer sistema, mas em Linux e macOS os programas precisariam de outro catálogo.
- **As bibliotecas Python vêm do PyPI com a versão fixada, sem hash por arquivo**: o `pip-audit` confere vulnerabilidades conhecidas, mas o `pip` só garante a origem pelo HTTPS do PyPI. Os modelos e programas, esses sim, têm o SHA-256 conferido.
- **Licença GPL na voz em português** (espeak-ng e phonemizer): aceita para uso local e registrada em `LICENCAS.md` (D-039); precisa ser tratada se o estúdio for distribuído.
- **Skills e plugins de design**: os plugins que o Vitor ativou na conta (Design, frontend-design, Context7, 21st) aparecem como ativos, mas **não foram carregados na sessão** que fez o redesenho (só entram ao abrir uma sessão nova). O redesenho seguiu as três normas que ele colou, e a qualidade foi checada por axe, contraste, teclado e revisão das capturas, não por essas skills.
- **Testes em outros navegadores e em aparelhos reais**: o ponta a ponta usa o **Edge** com tamanhos de tela emulados (no celular, com toque). Não rodei em Firefox, Safari nem em um telefone de verdade.
- **Leitores de tela de verdade** (NVDA, VoiceOver): o axe confere as regras automáticas do WCAG, mas não substitui ouvir a interface. Uma revisão manual de acessibilidade está prevista na Fase 9.
- **Regressão visual por comparação de imagens**: não implementada (é opcional no briefing); as capturas são só para olhar.
- **Interface em 4200 (modo desenvolvimento)**: `ng serve` não é coberto pelo E2E, que testa o build de produção servido pelo backend (o caminho de uso normal).
- **Teste de link simbólico**: `test_link_simbolico_para_fora_e_barrado` é **pulado** em ambientes sem privilégio para criar links simbólicos (foi o caso do Git Bash isolado). O `testar` mostra o pulo e o motivo no resumo; no PowerShell normal ele roda e passa.
- **Carga e desempenho**: a fila foi testada quanto ao comportamento, não com centenas de jobs.
- **As ferramentas de criação com os motores de verdade só foram exercitadas à mão** (2026-09-30): os testes automáticos usam imagem, recorte e voz **falsos** (rápidos e determinísticos) e o ffmpeg de verdade; a qualidade do que o FLUX, o Kokoro, o BiRefNet e o `qwen3:4b` produzem é julgada por quem olha (conferi os quadros da animação, os cenários e as miniaturas) e o tempo de cada tarefa está em [MODELOS.md](MODELOS.md), uma execução cada. O `testar --hw` continua rodando os motores de verdade só no nível de cada motor.
- **O modelo de texto (Ollama) não roda no E2E**: o roteiro, os textos do YouTube e a tradução pelo modelo local foram testados com um modelo falso (o formato do JSON, a validação, o filtro e o plano B) e **uma vez de verdade** com o `qwen3:4b`. A qualidade da escrita de um modelo de 4B é limitada: falas longas (o checklist avisa "cenas de 3 a 8 s fora do ritmo"), tradução literal e tags nem sempre boas; o usuário revisa tudo antes de aprovar.
- **Pacotes `.fabulim` entre máquinas diferentes**: exportar e importar foi testado na mesma máquina e com pacotes malformados; um pacote vindo do desktop (com renders de outra resolução) nunca foi aberto aqui.
- **Um Short de 60 s ou um vídeo longo de 5 min** não foram renderizados de ponta a ponta: o maior projeto real tem 3 cenas e 33 s. Os tempos maiores são cálculo a partir do medido (`PLANO.md`).

