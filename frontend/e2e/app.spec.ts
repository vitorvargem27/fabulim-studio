import AxeBuilder from '@axe-core/playwright';
import { APIRequestContext, expect, Page, test } from '@playwright/test';

const PAGINAS: [caminho: string, titulo: string][] = [
  ['/criar', 'Criar vídeo'],
  ['/personagens', 'Personagens'],
  ['/imagem', 'Gerar imagem'],
  ['/clipes', 'Clipes'],
  ['/projetos', 'Projetos'],
  ['/fila', 'Fila'],
  ['/modelos', 'Modelos'],
  ['/status/servicos', 'Status'],
  ['/status/maquina', 'Status'],
  ['/status/logs', 'Status'],
  ['/configuracoes', 'Configurações'],
];

/** Registra tudo o que não devia acontecer numa página: erro no console, exceção e resposta de API com erro. */
function vigiar(page: Page): string[] {
  const problemas: string[] = [];
  page.on('console', (m) => {
    if (m.type() === 'error') problemas.push(`console: ${m.text()}`);
  });
  page.on('pageerror', (e) => problemas.push(`exceção: ${e.message}`));
  page.on('response', (r) => {
    if (r.url().includes('/api/') && r.status() >= 400) problemas.push(`API ${r.status()}: ${r.url()}`);
  });
  return problemas;
}

async function limparFila(request: APIRequestContext): Promise<void> {
  const jobs = (await (await request.get('/api/jobs')).json()) as { id: string; status: string }[];
  for (const job of jobs.filter((j) => ['queued', 'running', 'paused'].includes(j.status))) {
    await request.post(`/api/jobs/${job.id}/cancel`);
  }
  await expect
    .poll(async () => ((await (await request.get('/api/jobs')).json()) as { status: string }[]).filter((j) => ['queued', 'running', 'paused'].includes(j.status)).length, { timeout: 15_000 })
    .toBe(0);
  await request.delete('/api/jobs/finished');
}

test.describe('navegação e integridade', () => {
  for (const [caminho, titulo] of PAGINAS) {
    test(`${caminho}: abre sem erros, com título e sem rolagem horizontal`, async ({ page }) => {
      const problemas = vigiar(page);
      await page.goto(caminho);
      await expect(page.locator('h1')).toHaveText(titulo);
      await expect(page).toHaveTitle(/Fabulim Studio/);
      await page.waitForLoadState('networkidle');
      const largura = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth, janela: window.innerWidth }));
      expect(largura.doc, 'a página não pode ter rolagem horizontal').toBeLessThanOrEqual(largura.janela + 1);
      expect(problemas).toEqual([]);
    });
  }

  test('a rota raiz vai para Criar vídeo e um endereço inexistente mostra a página 404 com saída', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/criar$/);
    await page.goto('/isto-nao-existe');
    await expect(page.locator('h1')).toHaveText('Página não encontrada');
    await page.getByRole('link', { name: 'Ir para Criar vídeo' }).click();
    await expect(page).toHaveURL(/\/criar$/);
  });

  test('links diretos (deep link) recarregam sem quebrar', async ({ page }) => {
    await page.goto('/status/maquina');
    await page.reload();
    await expect(page.getByRole('link', { name: 'Sua máquina' }).first()).toBeVisible();
    await expect(page.locator('#perfil-titulo')).toContainText('Perfil C');
  });

  test('nenhuma página fala em "Fase" (é linguagem de quem desenvolve, não de quem usa)', async ({ page }) => {
    for (const [caminho] of PAGINAS) {
      await page.goto(caminho);
      await expect(page.locator('h1')).toBeVisible();
      await page.waitForLoadState('networkidle');
      expect(await page.locator('body').innerText(), caminho).not.toMatch(/\bFase\b/);
    }
  });

  test('cada página tem um único título principal e a numeração do menu (01 a 09) no cabeçalho', async ({ page }) => {
    for (const [caminho] of PAGINAS) {
      await page.goto(caminho);
      await expect(page.locator('h1')).toHaveCount(1);
      await expect(page.locator('main fab-page-header p').first()).toContainText('/ 09');
    }
  });
});

test.describe('Criar vídeo: o formulário e o caminho do enredo ao vídeo', () => {
  test('as sete etapas são links: a primeira leva ao formulário e as outras aos Projetos', async ({ page }) => {
    await page.goto('/criar');
    const etapas = page.locator('ol.flow li a');
    await expect(etapas).toHaveCount(7);
    const destinos = await etapas.evaluateAll((links) => links.map((a) => (a as HTMLAnchorElement).getAttribute('href')));
    expect(destinos).toEqual(['/criar#comecar', '/projetos', '/projetos', '/projetos', '/projetos', '/projetos', '/projetos']);
    await expect(etapas.first()).toContainText('Enredo e personagens');
    await expect(etapas.first()).toContainText('Começar agora');
  });

  test('clicar numa etapa leva à página dela', async ({ page }) => {
    await page.goto('/criar');
    await page.getByRole('link', { name: /Storyboard/ }).click();
    await expect(page).toHaveURL(/\/projetos$/);
    await expect(page.locator('h1')).toHaveText('Projetos');
    await page.goBack();
    await page.getByRole('link', { name: /Enredo e personagens/ }).click();
    await expect(page).toHaveURL(/\/criar#comecar$/);
    await expect(page.getByRole('heading', { name: 'Comece pelo enredo' })).toBeInViewport();
  });

  test('sem personagens prontos o formulário explica o que fazer, e criar o projeto continua desativado', async ({ page }) => {
    await page.goto('/criar');
    await expect(page.getByText('Ainda não há personagens prontos para escolher.')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Criar um personagem' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Criar o projeto' })).toBeDisabled();
  });

  test('a tela de Modelos abre direto no grupo das vozes', async ({ page }) => {
    await page.goto('/modelos#voz');
    await expect(page.locator('h1')).toHaveText('Modelos');
    await expect(page.locator('#voz')).toBeInViewport();
    await expect(page.locator('#voz h2')).toHaveText('Voz');
  });

  test('a etapa mostra o estado ao passar o mouse sem perder o texto (contraste)', async ({ page }, info) => {
    test.skip(info.project.name === 'mobile', 'passar o mouse não existe no celular');
    await page.goto('/criar');
    const etapa = page.locator('ol.flow li a').first();
    await etapa.hover();
    const fundo = await etapa.evaluate((e) => getComputedStyle(e).backgroundColor);
    expect(fundo).toBe('rgb(255, 201, 60)'); // Girassol
    const cor = await etapa.evaluate((e) => getComputedStyle(e).color);
    expect(cor).toBe('rgb(43, 45, 110)'); // Anil sobre Girassol
  });
});

test.describe('Modelos: instalar programas e modelos', () => {
  const JOB = {
    id: 'a'.repeat(32),
    kind: 'ferramentas.instalar',
    title: 'Instalar ffmpeg',
    params: { id: 'ffmpeg' },
    status: 'queued',
    priority: 0,
    position: 1,
    progress: 0,
    message: '',
    eta_seconds: null,
    result: null,
    error: null,
    heavy: true,
    attempts: 0,
    cancel_requested: false,
    pause_requested: false,
    created_at: '2026-09-29T10:00:00.000+00:00',
    started_at: null,
    finished_at: null,
    updated_at: '2026-09-29T10:00:00.000+00:00',
  };

  test('lista os grupos e cada item com para que serve, licença e tamanho', async ({ page }) => {
    await page.goto('/modelos');
    await expect(page.locator('section h2')).toHaveText(['Montagem de vídeo', 'Imagens', 'Voz', 'Recorte de fundo']);
    const itens = page.locator('article.tool');
    expect(await itens.count()).toBeGreaterThanOrEqual(8);
    for (const item of await itens.all()) {
      await expect(item).toContainText('Licença:');
      await expect(item).toContainText('Tamanho:');
    }
    // as pastas do teste começam vazias: nada instalado, e "Instalar tudo" está disponível
    await expect(page.getByRole('button', { name: 'Instalar tudo o que falta' })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Instalar', exact: true }).first()).toBeVisible();
  });

  test('clicar em Instalar coloca na fila e mostra o andamento no item (a instalação real é simulada aqui)', async ({ page }) => {
    let pedidos = 0;
    await page.route('**/api/tools/ffmpeg/install', async (route) => {
      pedidos++;
      await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(JOB) });
    });
    await page.goto('/modelos');
    const cartao = page.locator('article.tool', { hasText: 'ffmpeg' }).first();
    await cartao.getByRole('button', { name: 'Instalar', exact: true }).click();
    await expect.poll(() => pedidos).toBe(1);
    await expect(page.getByText('colocada na fila')).toBeVisible();
    await expect(cartao).toContainText('Instalando');
    await expect(cartao.getByRole('button', { name: 'Instalar', exact: true })).toHaveCount(0); // não dá para pedir duas vezes
  });

  test('o servidor só aceita instalar itens do catálogo (um id desconhecido é recusado)', async ({ request }) => {
    const r = await request.post('/api/tools/qualquer-coisa/install', { headers: { Origin: 'http://127.0.0.1:8877' } });
    expect(r.status()).toBe(404);
  });
});

test.describe('acessibilidade (axe, WCAG 2.1 A e AA)', () => {
  for (const tema of ['light', 'dark'] as const) {
    for (const [caminho] of PAGINAS) {
      test(`${caminho} no tema ${tema}`, async ({ page }, info) => {
        test.skip(info.project.name === 'tablet' && tema === 'dark', 'o tema escuro é conferido em desktop e celular');
        await page.emulateMedia({ colorScheme: tema });
        await page.goto(caminho);
        await expect(page.locator('h1')).toBeVisible();
        await page.waitForLoadState('networkidle');
        const resultado = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
        const resumo = resultado.violations.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.html.slice(0, 120)).join(' | ')}`);
        expect(resumo).toEqual([]);
      });
    }
  }
});

test.describe('responsivo', () => {
  test('desktop mostra a barra lateral completa; celular e tablet usam a gaveta', async ({ page }, info) => {
    await page.goto('/criar');
    const menu = page.getByRole('button', { name: 'Abrir menu' });
    const barra = page.locator('.sidebar');
    if (info.project.name === 'desktop') {
      await expect(barra).toBeVisible();
      await expect(menu).toBeHidden();
      await expect(page.locator('nav .label').first()).toBeVisible();
    } else {
      await expect(barra).toBeHidden(); // fora da tela e sem foco: os links não entram na tabulação
      await expect(menu).toBeVisible();
    }
  });

  test('a gaveta abre, prende o foco, fecha com Esc e ao navegar', async ({ page }, info) => {
    test.skip(info.project.name === 'desktop', 'só existe abaixo de 900 px');
    await page.goto('/criar');
    const menu = page.getByRole('button', { name: 'Abrir menu' });
    await menu.click();
    await expect(page.locator('.sidebar')).toBeVisible();
    await expect(menu).toHaveAttribute('aria-expanded', 'true');
    // o foco fica dentro da gaveta enquanto ela está aberta
    for (let i = 0; i < 14; i++) {
      await page.keyboard.press('Tab');
      expect(await page.evaluate(() => !!document.activeElement?.closest('.sidebar'))).toBe(true);
    }
    await page.keyboard.press('Escape');
    await expect(page.locator('.sidebar')).toBeHidden();
    await menu.click();
    await page.getByRole('link', { name: 'Fila' }).click();
    await expect(page).toHaveURL(/\/fila$/);
    await expect(page.locator('.sidebar')).toBeHidden();
    await expect(page.locator('h1')).toHaveText('Fila'); // e o foco foi para o conteúdo
  });

  test('a marca aparece uma vez só, em qualquer tamanho de tela', async ({ page }, info) => {
    await page.goto('/criar');
    if (info.project.name !== 'desktop') await page.getByRole('button', { name: 'Abrir menu' }).click();
    const marcas = await page.locator('.brand fab-logo').evaluateAll((els) => els.filter((e) => (e as HTMLElement).offsetParent !== null && e.getBoundingClientRect().width > 0).length);
    expect(marcas, 'só uma versão da marca (larga ou ícone) fica visível').toBe(1);
    await expect(page.locator('.brand').getByText('Fabulim', { exact: false }).first()).toBeVisible();
  });

  test('no trilho estreito (900 a 1279 px) só o ícone da marca aparece', async ({ page }, info) => {
    test.skip(info.project.name !== 'desktop', 'usa o projeto desktop redimensionado');
    await page.setViewportSize({ width: 1024, height: 800 });
    await page.goto('/criar');
    const marcas = await page.locator('.brand fab-logo').evaluateAll((els) => els.filter((e) => (e as HTMLElement).offsetParent !== null && e.getBoundingClientRect().width > 0).length);
    expect(marcas).toBe(1);
    const largura = await page.locator('.brand').evaluate((e) => Math.round(e.getBoundingClientRect().width));
    expect(largura).toBeLessThan(100);
  });

  test('o foco do teclado é visível dentro da barra lateral (não some sobre a tinta)', async ({ page }, info) => {
    test.skip(info.project.name !== 'desktop', 'a barra lateral fixa só existe no desktop');
    await page.goto('/criar');
    let achou = false;
    for (let i = 0; i < 6 && !achou; i++) {
      await page.keyboard.press('Tab');
      achou = await page.evaluate(() => !!document.activeElement?.closest('.sidebar'));
    }
    expect(achou, 'o Tab precisa chegar à barra lateral').toBe(true);
    const anel = await page.evaluate(() => {
      const e = document.activeElement as HTMLElement;
      const s = getComputedStyle(e);
      return { cor: s.outlineColor, largura: parseFloat(s.outlineWidth), estilo: s.outlineStyle };
    });
    expect(anel.estilo).toBe('solid');
    expect(anel.largura).toBeGreaterThanOrEqual(3);
    expect(anel.cor, 'girassol sobre a barra azul-anil').toBe('rgb(255, 201, 60)');
  });

  test('entre 900 e 1279 px a barra vira trilho de ícones, com os nomes acessíveis', async ({ page }, info) => {
    test.skip(info.project.name !== 'desktop', 'usa o projeto desktop redimensionado');
    await page.setViewportSize({ width: 1024, height: 800 });
    await page.goto('/criar');
    const largura = await page.locator('.sidebar').evaluate((e) => Math.round(e.getBoundingClientRect().width));
    expect(largura).toBeLessThan(100);
    const menu = page.getByRole('navigation', { name: 'Navegação principal' });
    await expect(menu.getByRole('link', { name: 'Personagens' })).toBeVisible(); // o nome continua acessível (texto só para leitores de tela)
    const larguraDoRotulo = await page.locator('nav .label').first().evaluate((e) => e.getBoundingClientRect().width);
    expect(larguraDoRotulo, 'o texto do item fica só para leitores de tela').toBeLessThanOrEqual(2);
  });

  test('os alvos de toque são grandes o bastante no celular', async ({ page }, info) => {
    test.skip(info.project.name !== 'mobile', 'só no celular');
    await page.goto('/fila');
    for (const botao of await page.locator('header button, header a').all()) {
      const caixa = await botao.boundingBox();
      if (caixa) {
        expect(caixa.width, 'largura do alvo de toque').toBeGreaterThanOrEqual(40);
        expect(caixa.height, 'altura do alvo de toque').toBeGreaterThanOrEqual(36);
      }
    }
  });

  test('tabelas viram cartões legíveis no celular (cada célula com o seu rótulo)', async ({ page }, info) => {
    test.skip(info.project.name !== 'mobile', 'só no celular');
    await page.goto('/status/maquina');
    await expect(page.locator('table.caps tbody tr').first()).toBeVisible();
    const cabecalho = await page.locator('table.caps thead').evaluate((e) => Math.round(e.getBoundingClientRect().height));
    expect(cabecalho).toBeLessThanOrEqual(2); // cabeçalho escondido visualmente; os rótulos vêm de data-label
    const rotulo = await page.locator('table.caps tbody tr:first-child td:nth-child(2)').evaluate((e) => getComputedStyle(e, '::before').content);
    expect(rotulo).toContain('Estado');
  });
});

test.describe('Sua máquina', () => {
  test('mostra o perfil C com justificativa e a matriz de capacidades filtrável', async ({ page }) => {
    await page.goto('/status/maquina');
    await expect(page.locator('#perfil-titulo')).toContainText('Perfil C · Notebook ou GPU integrada');
    await expect(page.getByText('sem VRAM dedicada')).toBeVisible();
    await expect(page.locator('.letter')).toHaveText('C');
    const linhas = page.locator('table.caps tbody tr');
    await expect(linhas).toHaveCount(21);
    await page.getByRole('button', { name: /^Indisponível \(/ }).click();
    const restantes = await linhas.count();
    expect(restantes).toBeGreaterThan(0);
    expect(restantes).toBeLessThan(21);
    await expect(page.locator('table.caps tbody')).toContainText('Animação por IA');
    await expect(page.locator('table.caps tbody')).not.toContainText('Formulários a partir de prompts');
    await page.getByRole('button', { name: /^Todas \(/ }).click();
    await expect(linhas).toHaveCount(21);
  });

  test('mostra o hardware detectado e o botão de refazer o diagnóstico', async ({ page }) => {
    await page.goto('/status/maquina');
    await expect(page.getByText('LENOVO ThinkPad T14 Gen 2i')).toBeVisible();
    await expect(page.getByText('i7-1185G7')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Refazer diagnóstico' })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Rodar benchmark de calibração' })).toBeEnabled();
  });
});

test.describe('Status dos serviços', () => {
  test('separa o que pede atenção, o que funciona e o que ainda não está ativo', async ({ page }) => {
    await page.goto('/status/servicos');
    await expect(page.locator('section h2')).toContainText(['Precisam de atenção', 'Funcionando', 'Ainda não ativos']);
    const atencao = page.locator('section', { has: page.getByRole('heading', { name: 'Precisam de atenção' }) });
    await expect(atencao).toContainText('ffmpeg (montagem de vídeo)');
    const funcionando = page.locator('section', { has: page.getByRole('heading', { name: 'Funcionando' }) });
    await expect(funcionando).toContainText('Servidor do Fabulim');
    await expect(funcionando).not.toContainText('ffmpeg (montagem de vídeo)');
  });

  test('lista cada serviço com estado em texto e a instrução de como corrigir', async ({ page }) => {
    await page.goto('/status/servicos');
    await expect(page.getByRole('heading', { name: 'Servidor do Fabulim' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'ffmpeg (montagem de vídeo)' })).toBeVisible();
    const cartaoFfmpeg = page.locator('article', { hasText: 'ffmpeg (montagem de vídeo)' });
    const gatilho = cartaoFfmpeg.getByRole('button', { name: 'Como corrigir' });
    await expect(gatilho).toHaveAttribute('aria-expanded', 'false');
    await expect(cartaoFfmpeg).not.toContainText('Abra «Modelos»'); // o passo a passo só aparece depois de aberto
    await gatilho.click();
    await expect(gatilho).toHaveAttribute('aria-expanded', 'true');
    await expect(cartaoFfmpeg).toContainText('Abra «Modelos» e clique em «Instalar»');
    await gatilho.click();
    await expect(gatilho).toHaveAttribute('aria-expanded', 'false');
    await expect(page.locator('article', { hasText: 'Servidor do Fabulim' })).toContainText('Funcionando');
  });

  test('o "Como corrigir" abre e fecha pelo teclado (Enter e Espaço)', async ({ page }, info) => {
    test.skip(info.project.name === 'mobile', 'teclado é conferido em desktop e tablet');
    await page.goto('/status/servicos');
    const cartaoFfmpeg = page.locator('article', { hasText: 'ffmpeg (montagem de vídeo)' });
    const gatilho = cartaoFfmpeg.getByRole('button', { name: 'Como corrigir' });
    await gatilho.focus();
    await page.keyboard.press('Enter');
    await expect(gatilho).toHaveAttribute('aria-expanded', 'true');
    await page.keyboard.press('Space');
    await expect(gatilho).toHaveAttribute('aria-expanded', 'false');
  });

  test('"Ver logs" abre os logs já filtrados pelo serviço', async ({ page }) => {
    await page.goto('/status/servicos');
    await page.locator('article', { hasText: 'Servidor do Fabulim' }).getByRole('link', { name: 'Ver logs' }).click();
    await expect(page).toHaveURL(/\/status\/logs\?service=app/);
    await expect(page.locator('#f-servico')).toHaveValue('app');
    await expect(page.locator('.log-list li').first()).toBeVisible();
  });

  test('o Claude logado na máquina não aparece como conectado ao app (o botão de conectar ainda não está ativo)', async ({ page }) => {
    await page.goto('/criar');
    const chip = page.locator('fab-claude-indicator a');
    await expect(chip).toContainText('Claude: desconectado');
    await chip.click();
    await expect(page).toHaveURL(/\/configuracoes#claude$/);
    const cartao = page.locator('#claude');
    await expect(cartao).toContainText('Claude: desconectado');
    await expect(cartao).toContainText('Encontrado e logado, ainda não conectado ao app');
    await expect(cartao.getByRole('button', { name: 'Conectar conta do Claude' })).toBeDisabled();
    await page.goto('/status/servicos');
    const cartaoServico = page.locator('article', { hasText: 'Claude (opcional)' });
    await expect(cartaoServico).toContainText('Inativo');
    await expect(cartaoServico).not.toContainText('Funcionando');
  });
});

test.describe('Fila', () => {
  test.beforeEach(async ({ request }) => {
    await limparFila(request);
  });
  test.afterEach(async ({ request }) => {
    await limparFila(request);
  });

  test('job de demonstração: aparece ao vivo, pausa, retoma e cancela', async ({ page }) => {
    await page.goto('/fila');
    await expect(page.getByText('Ao vivo').first()).toBeVisible();
    await page.getByRole('button', { name: 'Job de demonstração' }).first().click();
    const atual = page.locator('article.current');
    await expect(atual).toContainText('Executando');
    await expect(atual.getByRole('progressbar')).toBeVisible();
    await expect.poll(async () => Number(await atual.getByRole('progressbar').getAttribute('aria-valuenow'))).toBeGreaterThan(0);

    await atual.getByRole('button', { name: /^Pausar/ }).click();
    await expect(atual).toContainText('Pausado');
    await atual.getByRole('button', { name: /^Retomar/ }).click();
    await expect(atual).toContainText('Executando');

    await atual.getByRole('button', { name: /^Cancelar/ }).click();
    await expect(page.locator('article.finished').first()).toContainText('Cancelado');
    await expect(page.locator('article.current')).toHaveCount(0);
  });

  test('a ordem da fila muda pelos botões e continua depois de recarregar a página', async ({ page, request }) => {
    for (const titulo of ['Primeiro', 'Segundo', 'Terceiro']) {
      await request.post('/api/jobs', { data: { kind: 'demo.sleep', title: titulo, params: { seconds: 60, steps: 60 } } });
    }
    await page.goto('/fila');
    await expect(page.locator('.list article')).toHaveCount(2); // o primeiro já virou "executando"
    await page.getByRole('button', { name: 'Descer «Segundo» na fila' }).click();
    await expect.poll(async () => (await page.locator('.list article strong').allTextContents()).slice(0, 2)).toEqual(['Terceiro', 'Segundo']);
    await page.reload();
    await expect.poll(async () => (await page.locator('.list article strong').allTextContents()).slice(0, 2)).toEqual(['Terceiro', 'Segundo']);
  });

  test('o estado vazio convida a criar um job', async ({ page }) => {
    await page.goto('/fila');
    await expect(page.getByText('A fila está vazia')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Job de demonstração' }).first()).toBeVisible();
  });
});

test.describe('tema, idioma e teclado', () => {
  test('o tema escolhido vale na hora e continua depois de recarregar', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light' });
    await page.goto('/criar');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    await page.getByRole('button', { name: 'Mudar para o tema escuro' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await expect(page.getByRole('button', { name: 'Mudar para o tema claro' })).toBeVisible();
  });

  test('trocar para English traduz a interface e lembra a escolha', async ({ page }, info) => {
    await page.goto('/criar');
    await page.getByRole('button', { name: /Mudar idioma/ }).click();
    await expect(page.locator('h1')).toHaveText('Create video');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await expect(page).toHaveTitle('Create video · Fabulim Studio'); // o título da aba acompanha na hora, sem recarregar
    if (info.project.name !== 'desktop') {
      await page.getByRole('button', { name: 'Open menu' }).click(); // no tablet e no celular o menu fica na gaveta
    }
    await expect(page.getByRole('link', { name: 'Settings' })).toBeVisible();
    await page.reload();
    await expect(page.locator('h1')).toHaveText('Create video');
    await expect(page).toHaveTitle('Create video · Fabulim Studio');
  });

  test('o primeiro Tab mostra o link "Pular para o conteúdo" e Enter leva ao conteúdo', async ({ page }, info) => {
    test.skip(info.project.name === 'mobile', 'navegação por teclado é testada em desktop e tablet');
    await page.goto('/criar');
    await page.keyboard.press('Tab');
    const link = page.getByRole('link', { name: 'Pular para o conteúdo' });
    await expect(link).toBeFocused();
    const caixa = await link.boundingBox();
    expect(caixa!.y).toBeGreaterThanOrEqual(0); // aparece dentro da janela quando recebe foco
    await page.keyboard.press('Enter');
    expect(await page.evaluate(() => document.activeElement?.id)).toBe('conteudo');
  });

  test('todo elemento interativo mostra um anel de foco visível', async ({ page }, info) => {
    test.skip(info.project.name === 'mobile', 'foco visível vale para teclado');
    await page.goto('/configuracoes');
    let conferidos = 0;
    for (let i = 0; i < 40; i++) {
      await page.keyboard.press('Tab');
      const contorno = await page.evaluate(() => {
        const e = document.activeElement as HTMLElement;
        const s = getComputedStyle(e);
        return { largura: parseFloat(s.outlineWidth), estilo: s.outlineStyle, tag: e.tagName };
      });
      if (contorno.tag === 'BODY') break; // passou do último elemento: o foco saiu da página
      expect(contorno.estilo, `foco no elemento ${contorno.tag}`).not.toBe('none');
      expect(contorno.largura).toBeGreaterThanOrEqual(2);
      conferidos++;
    }
    expect(conferidos, 'o teste precisa percorrer vários elementos, senão não prova nada').toBeGreaterThanOrEqual(5);
  });

  test('respeita "reduzir movimento": as transições ficam desligadas', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/criar');
    const duracao = await page.locator('.btn, nav a').first().evaluate((e) => getComputedStyle(e).transitionDuration);
    expect(parseFloat(duracao)).toBeLessThan(0.01);
  });
});

test.describe('segurança no navegador', () => {
  test('a resposta traz política de segurança de conteúdo estrita e cabeçalhos de proteção', async ({ request }) => {
    const r = await request.get('/criar');
    const h = r.headers();
    expect(h['content-security-policy']).toContain("default-src 'self'");
    expect(h['content-security-policy']).toContain("frame-ancestors 'none'");
    expect(h['x-content-type-options']).toBe('nosniff');
    expect(h['x-frame-options']).toBe('DENY');
    expect(h['referrer-policy']).toBe('no-referrer');
    expect(h['server']).toBeUndefined();
  });

  test('a interface não carrega nada de fora (sem CDN, fontes ou scripts externos)', async ({ page }) => {
    const externos: string[] = [];
    page.on('request', (req) => {
      const url = new URL(req.url());
      if (!['127.0.0.1', 'localhost'].includes(url.hostname) && url.protocol.startsWith('http')) externos.push(req.url());
    });
    for (const [caminho] of PAGINAS) await page.goto(caminho);
    expect(externos).toEqual([]);
  });

  test('a folha de estilos e as fontes estão ativas (regressão: o CSS crítico inline era bloqueado pela CSP)', async ({ page }) => {
    await page.goto('/criar');
    await expect(page.locator('h1')).toBeVisible(); // a página carrega sob demanda: espera aparecer antes de olhar as fontes
    const medias = await page.evaluate(() => [...document.querySelectorAll('link[rel="stylesheet"]')].map((l) => (l as HTMLLinkElement).media));
    expect(medias.length).toBeGreaterThan(0);
    for (const m of medias) expect(['', 'all']).toContain(m); // "print" = folha nunca ativada
    const fontes = await page.evaluate(() => ({
      corpo: getComputedStyle(document.body).fontFamily,
      titulo: getComputedStyle(document.querySelector('h1')!).fontFamily,
      texto: getComputedStyle(document.querySelector('main fab-page-header p:not([aria-hidden])')!).fontFamily,
    }));
    expect(fontes.corpo).toContain('Nunito Sans');
    expect(fontes.titulo).toContain('Fredoka');
    expect(fontes.texto).toContain('Fraunces');
    // as três famílias carregaram de verdade (vêm do próprio app, não de um servidor de fontes); o navegador só busca
    // uma fonte quando o texto que a usa aparece, então espera até todas estarem prontas em vez de olhar uma vez só
    await expect
      .poll(
        () =>
          page.evaluate(async () => {
            await document.fonts.ready;
            return [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family.replace(/["']/g, ''));
          }),
        { timeout: 10_000, message: 'as três famílias de fonte precisam carregar' },
      )
      .toEqual(expect.arrayContaining(['Fredoka Variable', 'Fraunces Variable', 'Nunito Sans Variable']));
  });

  test('um site qualquer não consegue disparar ações no servidor local (CSRF)', async ({ page, request }) => {
    await limparFila(request);
    await page.route('http://site-malicioso.example/**', (route) => route.fulfill({ contentType: 'text/html', body: '<html><body>página de outro site</body></html>' }));
    await page.goto('http://site-malicioso.example/');
    await page.evaluate(async (alvo) => {
      try {
        await fetch(`${alvo}/api/benchmark/run`, { method: 'POST', mode: 'no-cors' });
        await fetch(`${alvo}/api/machine/diagnostic`, { method: 'POST', mode: 'no-cors' });
      } catch {
        /* bloqueado pelo navegador: também vale */
      }
    }, 'http://127.0.0.1:8877');
    const jobs = (await (await request.get('/api/jobs')).json()) as { kind: string }[];
    expect(jobs.filter((j) => j.kind !== 'demo.sleep')).toEqual([]);

    const pedido = { kind: 'demo.sleep', params: { seconds: 30, steps: 30 } };
    const direto = await request.post('/api/jobs', { headers: { Origin: 'http://site-malicioso.example' }, data: pedido });
    expect(direto.status()).toBe(403);
    const mesmoSite = await request.post('/api/jobs', { headers: { Origin: 'http://127.0.0.1:8877' }, data: pedido });
    expect(mesmoSite.status()).toBe(201);
    await limparFila(request);
  });

  test('a documentação interativa (que usaria CDN) não está exposta', async ({ request }) => {
    expect((await request.get('/docs')).headers()['content-type']).toContain('text/html'); // cai no app (rota do Angular), nunca no Swagger
    const html = await (await request.get('/docs')).text();
    expect(html).not.toContain('swagger');
    expect((await request.get('/api/openapi.json')).status()).toBe(200);
  });
});
