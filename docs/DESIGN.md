# Design do Fabulim Studio

Interface de **revista de papel e tinta**: tipografia grande, filetes de tinta, numeração de seção, sombra dura de carimbo e quinas retas. A energia lúdica fica no **conteúdo** (personagens, prévias, miniaturas) e na paleta da marca, não em cartões arredondados. Implementada em **Angular 21** (signals, sem zone.js) com **Tailwind CSS v4 num tema exclusivo**, primitivos **sem estilo** (`@angular/aria`, `@angular/cdk`) e componentes próprios. Fonte única das cores: [`frontend/src/styles/tokens.css`](../frontend/src/styles/tokens.css).

## Por que não tem "cara de app feito por IA"

O visual padrão de um app gerado (cartões brancos iguais com sombra suave, cantos muito redondos, gradiente roxo, ícone dentro de círculo, tudo centralizado) vem de três coisas: kit de componentes com aparência própria, tema padrão do Tailwind e falta de identidade. Aqui cada uma foi trocada, de propósito:

1. **Primitivos sem estilo (headless).** O comportamento e a acessibilidade vêm de `@angular/aria` (o "Como corrigir" do Status é um acordeão do Aria: `role`, `aria-expanded`, teclado) e de `@angular/cdk` (arrastar e soltar da Fila, foco preso na gaveta). **Nenhum** kit com visual pronto (nada de Material, PrimeNG ou similares): toda a aparência é do projeto.
2. **Configuração exclusiva do Tailwind, com as escalas do Fabulim antes das telas.** [`styles/theme.css`](../frontend/src/styles/theme.css) começa com `--*: initial`, que **apaga o tema padrão**. Só existem as cores (Anil, Girassol, Coral, Menta, Nuvem e os papéis `paper`, `ink`, `accent`…), as fontes, a escala de texto, o espaçamento (base de 4 px + `gutter`, `rail`), as larguras, os pontos de quebra, as quinas (`2px`) e a sombra dura. Classes genéricas como `bg-blue-500`, `rounded-xl` ou `shadow-md` **não geram nada**.
3. **Sistema com forte personalidade: editorial com um toque brutalista.** Veja abaixo.

## A linguagem "papel e tinta"

| Elemento | Como é |
|---|---|
| **Papel e tinta** | fundo Nuvem, texto Anil; o tema escuro inverte para um azul-noite. Sem gradientes, sem vidro fosco. |
| **Seção** (`fab-section`) | filete de tinta de 2 px em cima (a primeira, logo abaixo do cabeçalho, não repete o filete dele); título e explicação numa coluna estreita à esquerda, conteúdo na larga à direita. Substitui os "cartões": a página se lê como uma matéria. |
| **Cabeçalho de página** | numeral da seção (`03 / 09`, o mesmo número do menu), título enorme em Fredoka, texto de apoio em Fraunces e um filete de tinta; faixa pontilhada decorativa à direita. |
| **Numerais vazados** | os passos do caminho e os "como funciona" usam números só com contorno de tinta; no *hover* ficam Anil sobre Girassol. |
| **Botão-carimbo** | contorno de 2 px, quinas de 2 px e sombra dura deslocada que "afunda" ao clicar. O botão principal é Girassol com texto Anil (8,0:1). |
| **Menu numerado** | 01 a 09 em fonte monoespaçada; o item ativo vira um bloco Girassol. A barra é sempre Anil (no escuro, azul-noite). |
| **Estado** | forma **e** palavra, nunca só cor: círculo com check, triângulo, quadrado com X, losango, círculo tracejado. |
| **Avisos** | faixa lateral de 8 px na cor do estado, fundo em papel. |
| **Sombra** | só a dura (`3px 3px 0`), nunca sombra suave. |

## Marca e cores

Paleta oficial (briefing 10.1): **Anil** `#2B2D6E`, **Girassol** `#FFC93C`, **Coral** `#FF7A8A`, **Menta** `#4FD1C5`, **Nuvem** `#F6F4FF`. Girassol e Menta ficam só em **fundos e formas**: como texto sobre fundo claro não passam em contraste (o teste garante isso).

| Token | Claro | Escuro | Uso |
|---|---|---|---|
| `--paper` | `#F6F4FF` (Nuvem) | `#15163A` | fundo da página |
| `--panel` / `--wash` | `#FFFFFF` / `#ECE8FA` | `#1E2050` / `#262962` | superfícies e realces |
| `--ink` | `#2B2D6E` (Anil, 11,3:1) | `#F6F4FF` | texto principal e contornos |
| `--ink-soft` | `#4F5187` | `#BDBBE6` | texto secundário (≥ 4,5:1 sobre todas as superfícies) |
| `--accent` / `--on-accent` | `#FFC93C` / `#2B2D6E` (8,0:1) | igual | ação principal, item ativo, marca-texto |
| `--ok-ink` / `--warn-ink` / `--bad-ink` | `#0B6B62` / `#8A5A00` / `#B3324A` | `#6EE7DA` / `#FFD666` / `#FF9DAA` | texto de estado (a forma e a palavra dizem o estado) |
| `--rail` … `--rail-accent` | Anil, Nuvem, Girassol | azul-noite | barra lateral (sempre escura) |
| `--focus` | `#2B2D6E` | `#FFC93C` | anel de foco de 3 px; **dentro da barra lateral** o anel é Girassol (Anil no item ativo), porque tinta sobre tinta some |

`frontend/src/styles/contrast.spec.ts` lê o arquivo de tokens (o bloco escuro sobrescreve o claro, como no navegador) e valida **31 pares por tema** (texto ≥ 4,5:1; foco, contornos e formas ≥ 3:1). Mudar uma cor que quebre o AA falha o teste. Ele também confere que o anel de foco da barra lateral existe no CSS: o teste achou o defeito de o foco comum ser invisível ali.

O logo vem de `marca/` (copiado por `frontend/scripts/copiar-marca.mjs`) e **não é redesenhado**. Sem os arquivos, a interface mostra o nome em texto. A pasta `marca/` ainda **não foi entregue** (falta o logo, o ícone e o mascote). Abaixo de 120 px de largura usa só o ícone; a barra tem um invólucro para cada versão e a tela mostra uma só.

## Tipografia

- **Fredoka** (variável, OFL): títulos e itens do menu; vem do logo da marca.
- **Fraunces** (variável, OFL): texto explicativo (subtítulos, "para que serve", passos). É a voz de revista; contrasta com a Fredoka e dá ritmo de leitura.
- **Nunito Sans** (variável, OFL): controles, tabelas e dados; mais legível em tamanho pequeno.
- Empacotadas localmente (`@fontsource-variable`): **nada é carregado de CDN** (o teste E2E confere que as três famílias carregam do próprio app). Tamanhos em `rem` (respeitam o tamanho de texto do usuário); título de página fluido (`clamp`).

## Layout e responsividade

| Largura | Barra lateral | Topo | Conteúdo |
|---|---|---|---|
| **≥ 1280 px** | completa (numeral + nome, 240 px) | Claude, Perfil, tema, idioma | até 1216 px, seções em duas colunas |
| **900 a 1279 px** | **trilho** de 76 px só com os numerais; o nome fica no `title` e para leitores de tela; só o ícone da marca | igual | igual |
| **< 900 px** | **gaveta** (`data-open`): botão de menu no topo, foco preso, `Esc`, botão de fechar e toque no fundo fecham, fecha ao navegar | itens só com ícone (o perfil mantém a letra) | uma coluna; tabelas viram cartões com o rótulo de cada célula |
| **ponteiro grosso** (toque) | — | — | alvos de toque de 48 px |

## Telas

- **Criar vídeo** (inicial): a caixa de **colar o enredo**, o formulário do vídeo (título, formato, duração, idioma, estilo, personagens, história) e o caminho do enredo ao vídeo em 7 etapas. **Cada etapa é um link** (a primeira leva ao formulário; as outras, aos Projetos), com o texto do que ela faz. Abaixo, como o computador se sai nas tarefas principais.
- **Personagens**: a biblioteca (busca e filtro por estilo) e a ficha de cada um em blocos na ordem do trabalho: variações e imagem principal, folha de poses em **PNG transparente sobre xadrez** (com o campo "Olha para"), ficha, voz (ouvir antes de salvar) e a versão em outro estilo. **Gerar imagem**: prompt, formulário, estimativa de tempo, prompt técnico avançado, variações lado a lado e a biblioteca. **Clipes**: clipe rápido, biblioteca com filtros, unir (arrastar ou ↑ ↓), outro formato, continuar e enviar vídeo.
- **Projetos**: a lista (progresso e etapa) e o projeto, com a **barra das sete etapas** (aprovada ✓, atual ●, bloqueada; a atual é Girassol e mantém o texto legível com o mouse em cima, no tema escuro também) e o conteúdo da etapa abaixo, cada uma terminando no rodapé de **aprovação** (aprovar tudo o que falta e a etapa, ou reabrir). Cena com editor, versões e posição dos personagens por controles (sem arrastar, para funcionar com teclado e toque). Cada página explica para que serve e como se comporta neste computador; nenhuma fala de fases de desenvolvimento.
- **Modelos**: os programas e modelos de IA que o estúdio usa, agrupados (Montagem de vídeo, Imagens, Voz, Recorte de fundo), cada um com para que serve, licença, tamanho do download (aproximado) e o botão **Instalar** (ou **Instalar tudo o que falta**). Instalar vira um job da Fila, com barra de progresso no próprio item.
- **Fila**: uma tarefa por vez, ao vivo (SSE), pausar/retomar/cancelar, reordenar **arrastando ou pelos botões** (alternativa de teclado), sobrevive a reinícios.
- **Status**: *Serviços* (agrupados em "Precisam de atenção", "Funcionando" e "Ainda não ativos"; "Como corrigir" num acordeão acessível; atalho para os logs), *Sua máquina* (perfil A a D com justificativa, hardware, aceleração, benchmark e matriz de capacidades filtrável) e *Logs*.
- **Configurações**: tema, idioma, pastas (dados, modelos, programas) e o card "Conta do Claude".
- **Indicador "Claude" no topo**: "conectado" significa que **o app** foi conectado (botão Conectar + chamada de teste, seção 15.2). Ter o Claude Code logado na máquina **não conta**: o chip mostra "desconectado" e o Status explica "encontrado e logado, ainda não conectado ao app".

## Componentes e estados

Etiqueta de estado (5 tons, com forma), barra de progresso (`role=progressbar`), estado vazio que convida a agir, controle segmentado (`radiogroup` com setas, Home e End), avisos (`aria-live`), acordeão (Angular Aria), seção e cabeçalho de página (um `h1` por tela), **miniatura de mídia** (`fab-media-tile`: imagem, recorte sobre xadrez, vídeo com o tempo, áudio com tocador; clicar abre em **tela grande** num `<dialog>` nativo, com Esc e foco preso), campo com rótulo e dica, **caixa de colar prompt** (exemplos, histórico e o formulário volta preenchido), escolha de personagens (botões que ligam e desligam), progresso do job no próprio lugar (`fab-job-progress`) e importar pacote. Estados de **carregando**, **vazio** e **erro** (em linguagem simples, dizendo o que fazer) existem em todas as telas com dados.

## Acessibilidade (verificada por teste)

- axe WCAG 2.1 A e AA em **11 páginas × 2 temas × 3 tamanhos** e, no percurso das ferramentas, em **Personagens, Gerar imagem, Clipes, Projetos, Criar vídeo, Fila e em cada etapa do projeto, nos dois temas**; foco visível de 3 px em todo elemento interativo (inclusive dentro da barra lateral); link "Pular para o conteúdo"; foco vai para o conteúdo a cada troca de página; título da aba traduzido por página.
- Teclado completo: menu, abas, filtros, fila, acordeão (Enter e Espaço), gaveta com foco preso.
- `prefers-reduced-motion` desliga transições. Movimento só responde a ações.
- Sem rolagem horizontal em nenhuma página; tabelas largas rolam dentro do próprio bloco.
- Toda região que rola sozinha e não tem link ou botão dentro (a lista de logs) recebe `tabindex="0"` (WCAG 2.1.1).

## Onde o mascote entra

O triângulo de "play" com rostinho (mascote) só entra em estados vazios, carregamento, fila noturna e confirmações importantes, **quando os arquivos de `marca/` chegarem**: as variações de expressão precisam partir do desenho oficial, e o briefing proíbe redesenhá-lo.

## O que evitamos de propósito

Cartões idênticos com sombra suave, gradientes decorativos, pílulas e cantos muito redondos, fundo creme com acento terracota, fundo preto com acento verde-ácido, rótulos em CAIXA ALTA e ícone dentro de círculo como enfeite. Aqui: filetes, numeração, tipografia grande, sombra dura e a paleta oficial.

## Internacionalização

PT-BR é o padrão; inglês já está preparado (`pt-br.ts` e `en.ts`, troca em tempo de execução, sem novo build). Um teste garante que **nenhuma chave usada no código falta** em nenhum idioma e que não sobra chave sem uso. Os textos vindos do backend (capacidades, detalhes de serviços, catálogo de modelos) ainda são só em português.
