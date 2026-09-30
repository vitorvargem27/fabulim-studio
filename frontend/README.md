# Frontend do Fabulim Studio

Interface do estúdio, em **Angular 21 + TypeScript (strict)** com **Tailwind CSS v4 num tema exclusivo** e primitivos sem estilo (`@angular/aria`, `@angular/cdk`). Em uso normal ela é compilada e **servida pelo backend** (`iniciar.bat` → http://127.0.0.1:8765); em desenvolvimento roda em `ng serve` com proxy para o backend. Visão geral do projeto: [`../CLAUDE.md`](../CLAUDE.md) e [`../docs/`](../docs/).

## Comandos

| Comando | O que faz |
|---|---|
| `npm start` | servidor de desenvolvimento em http://127.0.0.1:4200 (recarrega sozinho; `/api` vai para o backend em 8765, veja `proxy.conf.json`) |
| `npm run build` | build de produção em `dist/frontend/browser` (é o que o backend serve) |
| `npm test` | testes unitários (Vitest + jsdom); `npm test -- --watch=false --coverage` mede a cobertura (mínimo 70%) |
| `npm run lint` | ESLint, com as regras de acessibilidade dos templates |
| `npm run e2e` | compila e roda o ponta a ponta (Playwright no **Edge instalado**, com axe) em desktop, tablet e celular; sobe um backend próprio na porta 8877 e outro, com imagem, recorte e voz falsos e o ffmpeg de verdade, na 8878 (`e2e/servidor_falso.py`), onde o projeto `ferramentas` percorre do personagem ao vídeo final. Só ele: `npx playwright test --project=ferramentas` |

Para rodar tudo junto com o backend: `testar.bat` na raiz do projeto.

## Estrutura (`src/app`)

| Pasta | Conteúdo |
|---|---|
| `core/` | serviços sem tela: `api`, `jobs` (fila + SSE), `status`, `machine`, `theme`, `toast`, `title.strategy`, `format`, `models` (tipos da API) e `i18n/` (`t` pipe, `pt-br.ts`, `en.ts`) |
| `ui/` | componentes de base, sem regra de negócio: `badge`, `progress`, `segmented`, `icon`, `empty-state`, `page-header`, `section`, `toast-host`, `field`, `media-tile`, `viewer-host` (visualizador em tela grande), `prompt-box`, `character-picker`, `job-progress`, `package-import` |
| `layout/` | `logo` (marca) e `claude-indicator` (chip fixo no topo) |
| `pages/` | uma pasta por tela: `criar-video`, `personagens` (lista e ficha), `imagem`, `clipes`, `projetos` (lista, o projeto e uma pasta `etapas/` com as sete etapas), `fila` (com a fila noturna), `modelos` (instalar programas e modelos), `status/` (serviços, sua máquina, logs), `configuracoes` e `not-found` |
| `../styles.css` e `../styles/` | ponto de entrada; `tokens.css` (cores da marca e dos temas claro e escuro), `theme.css` (o tema **exclusivo** do Tailwind: `--*: initial` apaga o padrão), `base.css` (tipografia, foco) e `components.css` (botão-carimbo, campos, tabelas, abas, avisos) |
| `../testing/` | dados de teste compartilhados (`fixtures.ts`, `FakeEventSource`) |

## Convenções

- Componentes **standalone**, com **signals**, `OnPush` e **zoneless** (sem zone.js). Todas as rotas carregam sob demanda.
- **Texto na tela sempre por chave**: `{{ 'fila.pause' | t }}`, com as chaves em `core/i18n/pt-br.ts` e `en.ts` (e `*.ferramentas.ts` para as ferramentas de criação). Plural: `{n#singular|plural}`. Um teste falha se faltar chave em algum idioma, se os `{marcadores}` divergirem ou se sobrar chave sem uso; chaves montadas por texto entram na lista `DINAMICAS` de `i18n.spec.ts`.
- **Estilo**: só as classes das escalas do Fabulim (cores, texto, espaçamento, quinas, sombra dura); `bg-blue-500`, `rounded-xl` e `shadow-md` **não existem** neste projeto. Classe montada por texto não é gerada: escreva o nome inteiro. Classes de `display` num host de componente brigam com as do pai: embrulhe o componente num `<span>`.
- **Cores só por token** (`var(--ink)`, `var(--accent)`, `bg-paper`...). `styles/contrast.spec.ts` lê `tokens.css` e confere o contraste WCAG AA dos pares de cores nos dois temas (e que o foco da barra lateral tem regra própria).
- **Linguagem de produto**: nada de "Fase N" em texto de tela; um teste falha se aparecer.
- **Acessibilidade em tudo**: rótulo em todo controle, estado em texto e ícone (nunca só cor), foco visível, alvo de toque de 44 px, região que rola tem foco de teclado. O E2E roda o axe em todas as páginas.
- **Responsivo**: barra lateral ≥ 1280 px, trilho de ícones de 900 a 1279 px, gaveta abaixo de 900 px; tabelas viram cartões no celular.
- Sem CDN, sem fonte externa, sem telemetria: a CSP do backend é estrita (`script-src 'self'`). Por isso `inlineCritical` está desligado em `angular.json` (o `onload` inline do CSS crítico seria bloqueado; há um teste para isso).

## Marca

Os 4 arquivos oficiais (`fabulim-icone.svg`, `fabulim-icone-512.png`, `fabulim-logo.svg`, `fabulim-logo-escuro.svg`) ficam em `../marca/` e são copiados para `public/marca/` por `scripts/copiar-marca.mjs` (no `npm start` e no `npm run build`). **Enquanto a pasta não existir**, o app usa um logo em texto (Fredoka) e um ícone provisório, sem redesenhar a marca.
