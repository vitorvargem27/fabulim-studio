import AxeBuilder from '@axe-core/playwright';
import { expect, Locator, Page, test } from '@playwright/test';
import { existsSync, statSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { crc32, deflateSync } from 'node:zlib';

// As ferramentas de criação, do personagem ao vídeo final, pela interface: Personagens, Gerar imagem, Clipes, Criar vídeo, Projetos
// (as sete etapas), a Fila noturna e o pacote .fabulim. Rodam num servidor com imagem, recorte e voz falsos (e2e/servidor_falso.py) e o
// ffmpeg de verdade, então cada passo leva segundos. Os testes andam em ordem e deixam pronto o que o próximo usa, como quem usa o estúdio.
test.describe.configure({ mode: 'serial' });

const RAIZ = path.resolve(__dirname, '..', '..');
const TEM_FFMPEG = existsSync(path.join(RAIZ, 'tools', 'ffmpeg', 'bin', process.platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg'));
const LONGO = 120_000;
const NAVEGAR = { timeout: 45_000 }; // ir para a página do que acabou de ser criado depende do servidor gravar arquivos: no notebook carregado passa dos 10 s padrão

let projeto = ''; // o caminho do projeto criado no teste do Criar vídeo, usado pelos testes seguintes
let pacote = ''; // o pacote .fabulim baixado na revisão, importado depois

/**
 * Tudo o que não devia acontecer numa página: erro no console, exceção e resposta de API com erro. O que o teste provoca de
 * propósito (por exemplo, pedir o modelo local que não está ligado) entra em `esperados` e não conta.
 */
function vigiar(page: Page, esperados: RegExp[] = []): string[] {
  const problemas: string[] = [];
  const esperado = (texto: string): boolean => esperados.some((e) => e.test(texto));
  page.on('console', (m) => {
    if (m.type() === 'error' && !esperado(m.text())) problemas.push(`console: ${m.text()}`);
  });
  page.on('pageerror', (e) => problemas.push(`exceção: ${e.message}`));
  page.on('response', (r) => {
    if (r.url().includes('/api/') && r.status() >= 400 && !esperado(`${r.status()} ${r.url()}`)) problemas.push(`API ${r.status()}: ${r.url()}`);
  });
  return problemas;
}

/** Um PNG de verdade (RGBA, um degradê), feito na hora: o servidor só aceita a imagem depois de decodificá-la. */
function png(largura: number, altura: number): Buffer {
  const linhas = Buffer.alloc((1 + largura * 4) * altura);
  for (let y = 0; y < altura; y++) {
    for (let x = 0; x < largura; x++) {
      linhas.set([Math.round((x * 255) / largura), Math.round((y * 255) / altura), 180, 255], y * (1 + largura * 4) + 1 + x * 4);
    }
  }
  const bloco = (tipo: string, dados: Buffer): Buffer => {
    const inicio = Buffer.alloc(4);
    inicio.writeUInt32BE(dados.length);
    const corpo = Buffer.concat([Buffer.from(tipo, 'ascii'), dados]);
    const fim = Buffer.alloc(4);
    fim.writeUInt32BE(crc32(corpo));
    return Buffer.concat([inicio, corpo, fim]);
  };
  const cabecalho = Buffer.alloc(13);
  cabecalho.writeUInt32BE(largura, 0);
  cabecalho.writeUInt32BE(altura, 4);
  cabecalho[8] = 8; // 8 bits por canal
  cabecalho[9] = 6; // RGBA
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    bloco('IHDR', cabecalho),
    bloco('IDAT', deflateSync(linhas)),
    bloco('IEND', Buffer.alloc(0)),
  ]);
}

/** Um bloco da página, pelo id do título (o `fab-section` põe o id no h2 e liga o bloco a ele por `aria-labelledby`). */
const secao = (page: Page, id: string): Locator => page.locator(`section[aria-labelledby="${id}"]`);

async function etapaAtual(page: Page, nome: string): Promise<void> {
  await expect(page.getByRole('navigation', { name: 'Etapas do projeto' }).locator('button[aria-current="step"]')).toContainText(nome);
}

/** Aprova a etapa: as com cenas têm o botão «Aprovar N cenas restantes e a etapa» (liberado quando tudo o que precisa está pronto). */
async function aprovarEtapa(page: Page): Promise<void> {
  const todas = page.getByRole('button', { name: /^Aprovar \d+ cenas? restantes? e a etapa$/ });
  if (await todas.count()) {
    await expect(todas).toBeEnabled({ timeout: LONGO });
    await todas.click();
  } else {
    const unica = page.getByRole('button', { name: 'Aprovar a etapa', exact: true });
    await expect(unica).toBeEnabled({ timeout: LONGO });
    await unica.click();
  }
}

test.describe('Personagens', () => {
  test('a biblioteca começa vazia; o prompt de exemplo preenche a ficha e cria a Lila', async ({ page }) => {
    const problemas = vigiar(page);
    await page.goto('/personagens');
    await expect(page.locator('h1')).toHaveText('Personagens');
    await expect(page.getByText('A biblioteca está vazia')).toBeVisible();

    await page.getByRole('button', { name: 'Exemplo estruturado' }).click();
    await page.getByRole('button', { name: 'Ler o prompt e preencher o formulário' }).click();
    await expect(page.getByRole('textbox', { name: 'Nome', exact: true })).toHaveValue('Lila');
    await expect(page.getByLabel('Tipo ou espécie')).toHaveValue('coelhinha');

    await page.getByRole('button', { name: 'Criar personagem', exact: true }).click();
    await expect(page).toHaveURL(/\/personagens\/[0-9a-f]{32}$/, NAVEGAR);
    await expect(page.locator('h1')).toHaveText('Lila', NAVEGAR);
    expect(problemas).toEqual([]);
  });

  test('gera variações, escolhe a principal (o fundo é recortado) e gera a folha de poses', async ({ page }) => {
    await page.goto('/personagens');
    await page.getByRole('link', { name: /Lila/ }).first().click();
    await expect(page.locator('h1')).toHaveText('Lila');
    await expect(page.getByText('Ainda não há variações')).toBeVisible();

    await page.locator('#var-count').selectOption('2');
    await page.locator('#var-quality').selectOption('rascunho');
    await page.getByRole('button', { name: 'Gerar 2 variações' }).click();
    const opcoes = secao(page, 'variacoes').locator('fab-media-tile');
    await expect(opcoes).toHaveCount(2, { timeout: LONGO });

    await opcoes.first().getByRole('button', { name: 'Escolher esta' }).click();
    await expect(opcoes.first().getByRole('button', { name: 'Escolhida' })).toBeDisabled();
    // o recorte do fundo roda sozinho; quando termina, o personagem fica pronto para vídeos
    await expect(page.getByText('Pronto para vídeos')).toBeVisible({ timeout: LONGO });

    await page.locator('#sheet-quality').selectOption('rascunho');
    await page.getByRole('button', { name: 'Gerar a folha de referência' }).click();
    const direcoes = secao(page, 'folha').locator('select[id^="facing-"]');
    await expect.poll(() => direcoes.count(), { timeout: LONGO }).toBeGreaterThanOrEqual(2);
  });

  test('ouve a voz do personagem (o áudio de teste fica guardado na página)', async ({ page }) => {
    await page.goto('/personagens');
    await page.getByRole('link', { name: /Lila/ }).first().click();
    await page.getByRole('button', { name: 'Ouvir a voz' }).click();
    await expect(secao(page, 'voz').locator('audio')).toHaveCount(1, { timeout: LONGO });
  });
});

test.describe('Personagens: outros jeitos de criar', () => {
  test('a versão 3D é outro personagem, criado a partir da imagem principal', async ({ page }) => {
    await page.goto('/personagens');
    await page.getByRole('link', { name: /Lila/ }).first().click();
    const antes = page.url();
    await page.getByRole('button', { name: 'Criar a versão 3D' }).click();
    await expect(page).not.toHaveURL(antes, NAVEGAR);
    await expect(page).toHaveURL(/\/personagens\/[0-9a-f]{32}$/, NAVEGAR);
    await expect(page.locator('main').getByText('3D', { exact: true }).first()).toBeVisible();
    await expect(secao(page, 'variacoes').locator('fab-media-tile')).toHaveCount(2, { timeout: LONGO }); // as opções da versão 3D
  });

  test('enviar uma imagem sua: o app recorta o fundo e usa como imagem principal', async ({ page }) => {
    await page.goto('/personagens');
    // o botão do topo abre o seletor de arquivos do sistema (o Explorer, no Windows) e já leva ao envio
    const [seletor] = await Promise.all([
      page.waitForEvent('filechooser'),
      page.getByRole('button', { name: 'Importar imagem do computador' }).click(),
    ]);
    await seletor.setFiles({ name: 'bia.png', mimeType: 'image/png', buffer: png(96, 128) });
    await expect(page.getByText('Arquivo escolhido: bia.png')).toBeVisible();
    await page.getByRole('textbox', { name: 'Nome', exact: true }).fill('Bia');
    await expect(page.getByRole('button', { name: 'Enviar e criar' })).toBeDisabled(); // falta dizer que tem o direito de usar
    await page.getByLabel('Tenho o direito de usar esta imagem').check();
    await page.getByRole('button', { name: 'Enviar e criar' }).click();
    await expect(page).toHaveURL(/\/personagens\/[0-9a-f]{32}$/, NAVEGAR);
    await expect(page.locator('h1')).toHaveText('Bia', NAVEGAR);
    await expect(page.getByText('Pronto para vídeos')).toBeVisible({ timeout: LONGO });
  });

  test('um arquivo que não é imagem é recusado', async ({ page }) => {
    await page.goto('/personagens');
    await page.getByRole('radio', { name: 'Enviar uma imagem' }).click();
    await page.locator('#upload-file').setInputFiles({ name: 'falsa.png', mimeType: 'image/png', buffer: Buffer.from('isto não é uma imagem') });
    await page.getByRole('textbox', { name: 'Nome', exact: true }).fill('Falsa');
    await page.getByLabel('Tenho o direito de usar esta imagem').check();
    await page.getByRole('button', { name: 'Enviar e criar' }).click();
    await expect(page.getByRole('alert').first()).toBeVisible();
    await expect(page).toHaveURL(/\/personagens$/);
  });
});

test.describe('Gerar imagem', () => {
  test('o prompt de exemplo preenche o formulário; gera variações lado a lado, abre em tela grande e apaga', async ({ page }) => {
    const problemas = vigiar(page);
    await page.goto('/imagem');
    await expect(page.locator('h1')).toHaveText('Gerar imagem');
    await expect(page.getByText('Nenhuma imagem ainda')).toBeVisible();

    await page.getByRole('button', { name: 'Exemplo estruturado' }).click();
    await page.getByRole('button', { name: 'Ler o prompt e preencher o formulário' }).click();
    await expect(page.getByRole('textbox', { name: 'Descrição', exact: true })).toHaveValue(/jardim florido de manhã/);

    await page.locator('#img-quality').selectOption('rascunho');
    await page.locator('#img-count').fill('2');
    await page.locator('#img-count').blur();
    await expect(page.getByText(/Estimativa neste computador: cerca de .* para 2 imagens/)).toBeVisible();
    await page.getByRole('button', { name: 'Gerar imagem', exact: true }).click();

    const resultados = secao(page, 'resultados').locator('fab-media-tile');
    await expect(resultados).toHaveCount(2, { timeout: LONGO });
    await expect(page.getByRole('heading', { name: 'Suas imagens (2)' })).toBeVisible();

    // abrir em tela grande: o visualizador mostra a descrição e fecha com Esc
    await resultados.first().getByRole('button', { name: /Abrir em tela grande/ }).click();
    const dialogo = page.locator('dialog[open]');
    await expect(dialogo).toBeVisible();
    await expect(dialogo).toContainText('jardim florido');
    await page.keyboard.press('Escape');
    await expect(dialogo).toHaveCount(0);

    // apagar da biblioteca pede confirmação e o contador acompanha
    page.once('dialog', (d) => void d.accept());
    await secao(page, 'biblioteca').locator('fab-media-tile').first().getByRole('button', { name: 'Apagar imagem' }).click();
    await expect(page.getByRole('heading', { name: 'Suas imagens (1)' })).toBeVisible();
    expect(problemas).toEqual([]);
  });

  test('sem descrição não dá para gerar', async ({ page }) => {
    await page.goto('/imagem');
    await expect(page.getByRole('button', { name: 'Gerar imagem', exact: true })).toBeDisabled();
  });
});

test.describe('Clipes', () => {
  test.skip(!TEM_FFMPEG, 'precisa do ffmpeg instalado em tools/ (instale pela tela Modelos)');

  test('clipe rápido: um personagem e uma frase viram um clipe na biblioteca; outro formato e unir', async ({ page }) => {
    const problemas = vigiar(page);
    await page.goto('/clipes');
    await expect(page.locator('h1')).toHaveText('Clipes');
    await expect(page.getByText('Nenhum clipe ainda')).toBeVisible();

    await page.locator('#quick-character').selectOption({ label: 'Lila (2D)' });
    await page.locator('#quick-duration').fill('3');
    await page.getByLabel('O que acontece no clipe').fill('pulando de alegria num jardim florido');
    await page.locator('#quick-quality').selectOption('rascunho');
    await page.getByRole('button', { name: 'Gerar clipe' }).click();
    await expect(page.getByRole('heading', { name: 'Biblioteca de clipes (1)' })).toBeVisible({ timeout: LONGO });
    const biblioteca = secao(page, 'biblioteca');
    await expect(biblioteca.locator('fab-media-tile').first()).toContainText('Clipe rápido');

    // outro formato: cria uma cópia ligada ao original
    await biblioteca.locator('fab-media-tile').first().getByRole('button', { name: 'Outro formato' }).click();
    await page.locator('#reframe-preset').selectOption('16:9');
    await page.getByRole('button', { name: 'Gerar o novo formato' }).click();
    await expect(page.getByRole('heading', { name: 'Biblioteca de clipes (2)' })).toBeVisible({ timeout: LONGO });
    await expect(biblioteca.locator('fab-media-tile', { hasText: '1920×1080' })).toHaveCount(1);

    // unir os dois: marca, confere a sequência e une
    for (const caixa of await biblioteca.getByLabel('Para unir').all()) await caixa.check();
    await page.getByRole('button', { name: 'Unir 2 vídeos' }).click();
    await expect(page.getByRole('heading', { name: 'Biblioteca de clipes (3)' })).toBeVisible({ timeout: LONGO });
    await expect(biblioteca.locator('fab-media-tile', { hasText: 'Unido' })).toHaveCount(1);
    expect(problemas).toEqual([]);
  });

  test('continuar a partir de um clipe cria um projeto que começa igual ao último quadro', async ({ page }) => {
    await page.goto('/clipes');
    const biblioteca = secao(page, 'biblioteca');
    await biblioteca.locator('fab-media-tile', { hasText: 'Clipe rápido' }).first().getByRole('button', { name: 'Continuar' }).click();
    await page.getByRole('textbox', { name: 'O que acontece a seguir' }).fill('Lila encontra um amigo no jardim. Os dois brincam juntos.');
    await page.getByRole('textbox', { name: 'O que aparece no final do clipe' }).fill('a Lila pulando num jardim florido');
    await page.getByRole('button', { name: 'Criar o projeto de continuação' }).click();
    await expect(page).toHaveURL(/\/projetos\/[0-9a-f]{32}$/, NAVEGAR);
    await expect(page.getByText('Ver o projeto de origem')).toBeHidden(); // o clipe não é um projeto: a continuação nasce do último quadro
    await expect(page.getByRole('navigation', { name: 'Etapas do projeto' })).toBeVisible();
  });

  test('um arquivo que não é vídeo é recusado na hora de enviar (o tipo é conferido de verdade)', async ({ page }) => {
    await page.goto('/clipes');
    await page.locator('#clip-file').setInputFiles({ name: 'falso.mp4', mimeType: 'video/mp4', buffer: Buffer.from('isto não é um vídeo') });
    await page.getByLabel('Tenho o direito de usar este vídeo.').check();
    await page.getByRole('button', { name: 'Enviar vídeo' }).click();
    await expect(page.getByRole('alert').first()).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Biblioteca de clipes (3)' })).toBeVisible();
  });
});

test.describe('Criar vídeo e o projeto, etapa por etapa', () => {
  test('o enredo de exemplo preenche o formulário e cria o projeto', async ({ page }) => {
    const problemas = vigiar(page);
    await page.goto('/criar');
    await page.getByRole('button', { name: 'Exemplo estruturado' }).click();
    await page.getByRole('button', { name: 'Ler o prompt e preencher o formulário' }).click();
    await expect(page.getByRole('textbox', { name: 'Título', exact: true })).toHaveValue('A Lila e a estrelinha que se perdeu');
    await expect(page.getByRole('textbox', { name: 'História', exact: true })).toHaveValue(/estrelinha pequenina/);
    // a Lila já tem o PNG transparente: aparece para escolher e vem marcada pelo nome que o enredo cita
    await expect(page.getByRole('button', { name: /^Lila/, pressed: true })).toBeVisible();

    await page.locator('#story-seconds').fill('15'); // curto: menos cenas, o teste anda mais rápido
    await page.getByRole('button', { name: 'Criar o projeto' }).click();
    await expect(page).toHaveURL(/\/projetos\/[0-9a-f]{32}$/, NAVEGAR);
    projeto = new URL(page.url()).pathname;
    await expect(page.locator('h1')).toHaveText('A Lila e a estrelinha que se perdeu');
    await etapaAtual(page, 'Enredo e personagens');
    expect(problemas).toEqual([]);
  });

  test('roteiro: sem o modelo local o app diz por quê; o roteiro simples divide a história em cenas', async ({ page }) => {
    await page.goto(projeto);
    await aprovarEtapa(page);
    await etapaAtual(page, 'Roteiro');

    await page.getByRole('button', { name: 'Gerar o roteiro com o modelo local' }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'O modelo de texto local não está ligado neste teste.' })).toBeVisible();
    await page.getByRole('button', { name: 'Roteiro simples (sem IA)' }).click();
    await expect(page.getByRole('heading', { name: /^Cenas \(\d+\)$/ })).toBeVisible();
    await expect(page.locator('fab-scene-editor').first()).toBeVisible({ timeout: LONGO });
    expect(await page.locator('fab-scene-editor').count()).toBeGreaterThanOrEqual(2);

    // editar uma cena cria uma versão nova (e dá para voltar)
    await page.locator('fab-scene-editor').first().getByRole('button', { name: 'Editar a cena' }).click();
    await page.getByLabel('Título da cena').fill('A descoberta');
    await page.getByRole('button', { name: 'Salvar a cena' }).click();
    await expect(page.locator('fab-scene-editor').first()).toContainText('A descoberta');
    await expect(page.locator('fab-scene-editor').first().getByRole('button', { name: 'Versões (v2)' })).toBeVisible();

    await aprovarEtapa(page);
    await etapaAtual(page, 'Storyboard');
  });

  test('storyboard: gera o cenário de cada cena (o personagem entra por cima) e aprova', async ({ page }) => {
    await page.goto(projeto);
    await etapaAtual(page, 'Storyboard');
    await page.locator('#sb-quality').selectOption('rascunho');
    await page.getByRole('button', { name: 'Gerar os cenários' }).click();
    const cenas = page.locator('fab-scene-storyboard');
    for (const cena of await cenas.all()) await expect(cena.getByRole('img').first()).toBeVisible({ timeout: LONGO });
    await aprovarEtapa(page);
    await etapaAtual(page, 'Animação');
  });

  test('animação por código: anima as cenas e explica por que a animação por IA não roda aqui', async ({ page }) => {
    test.skip(!TEM_FFMPEG, 'precisa do ffmpeg');
    await page.goto(projeto);
    await etapaAtual(page, 'Animação');
    await expect(page.getByText('Animação por IA (imagem em vídeo) não roda neste computador.')).toBeVisible();
    await page.getByLabel('Rascunho rápido (resolução menor, para conferir o movimento)').check();
    await page.getByRole('button', { name: 'Animar as cenas' }).click();
    await expect(page.locator('fab-etapa-animacao fab-badge', { hasText: 'Animada' }).first()).toBeVisible({ timeout: 180_000 });
    await aprovarEtapa(page);
    await etapaAtual(page, 'Áudio');
  });

  test('áudio: vozes, música instrumental e efeitos numa mistura só, com as legendas', async ({ page }) => {
    test.skip(!TEM_FFMPEG, 'precisa do ffmpeg');
    await page.goto(projeto);
    await etapaAtual(page, 'Áudio');
    await page.getByRole('button', { name: 'Gerar o áudio', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Áudio pronto' })).toBeVisible({ timeout: 180_000 });
    await expect(page.getByRole('link', { name: 'Baixar as legendas (SRT)' })).toBeVisible();
    await aprovarEtapa(page);
    await etapaAtual(page, 'Montagem');
  });

  test('montagem: junta clipes e áudio no vídeo final', async ({ page }) => {
    test.skip(!TEM_FFMPEG, 'precisa do ffmpeg');
    await page.goto(projeto);
    await etapaAtual(page, 'Montagem');
    await page.getByRole('button', { name: 'Montar o vídeo', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Vídeo montado' })).toBeVisible({ timeout: 180_000 });
    await expect(page.locator('fab-etapa-montagem video')).toBeVisible();
    await aprovarEtapa(page);
    await etapaAtual(page, 'Revisão e exportação');
  });

  test('revisão: checklist, miniaturas 1280×720, título e tags, e o pacote .fabulim', async ({ page }) => {
    test.skip(!TEM_FFMPEG, 'precisa do ffmpeg');
    const problemas = vigiar(page, [/^503 .*\/metadata$/, /status of 503/]); // o pedido ao modelo local (desligado) é de propósito
    await page.goto(projeto);
    await etapaAtual(page, 'Revisão e exportação');
    await expect(page.getByRole('heading', { name: 'Checklist de qualidade' })).toBeVisible();
    await expect(secao(page, 'checklist').locator('fab-badge').first()).toBeVisible();
    await expect(page.getByRole('link', { name: 'Baixar o vídeo (MP4)' })).toBeVisible();

    await page.locator('#thumb-count').selectOption('2');
    await page.getByRole('button', { name: 'Gerar miniaturas' }).click();
    const miniaturas = secao(page, 'miniaturas').locator('fab-media-tile');
    await expect(miniaturas).toHaveCount(2, { timeout: LONGO });
    await expect(miniaturas.first()).toContainText('1280×720');

    // o texto pelo modelo local avisa por que não dá; o modelo pronto (sem IA) preenche os dois idiomas
    await page.getByRole('button', { name: 'Sugerir com o modelo local' }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'O modelo de texto local não está ligado neste teste.' })).toBeVisible();
    await page.getByRole('button', { name: 'Usar o modelo pronto (sem IA)' }).click();
    await expect(page.getByText('Origem: modelo pronto')).toBeVisible({ timeout: LONGO });
    await expect(secao(page, 'textos').getByRole('textbox', { name: 'Título', exact: true }).first()).not.toHaveValue('');
    await secao(page, 'textos').getByRole('textbox', { name: 'Título', exact: true }).first().fill('A Lila e a estrelinha: um vídeo para crianças');
    await page.getByRole('button', { name: 'Salvar os textos' }).click();
    await expect(page.getByText('Textos salvos.')).toBeVisible();
    await expect(page.getByText('Origem: editado por você')).toBeVisible();

    // o pacote .fabulim
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('link', { name: 'Baixar o pacote .fabulim' }).click()]);
    pacote = path.join(os.tmpdir(), `e2e-${Date.now()}.fabulim`);
    await download.saveAs(pacote);
    expect(statSync(pacote).size).toBeGreaterThan(1000);
    expect(problemas).toEqual([]);
  });

  test('outras versões: criar sem traduzir (o modelo local não está ligado) e a versão em vídeo longo', async ({ page }) => {
    test.skip(!TEM_FFMPEG, 'precisa do ffmpeg');
    await page.goto(projeto);
    await etapaAtual(page, 'Revisão e exportação');
    const versoes = secao(page, 'versoes');
    await versoes.getByRole('button', { name: 'Criar traduzindo com o modelo local' }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'O modelo de texto local não está ligado neste teste.' })).toBeVisible();
    await versoes.getByRole('button', { name: 'Criar sem traduzir (eu traduzo)' }).click();
    await expect(versoes.getByRole('link', { name: /A Lila e a estrelinha/ })).toBeVisible({ timeout: LONGO });
    await expect(versoes).toContainText('EN');

    await versoes.getByRole('button', { name: 'Criar a versão Vídeo longo' }).click();
    await expect(page).toHaveURL(/\/projetos\/[0-9a-f]{32}$/, NAVEGAR);
    await expect(page.locator('h1')).toContainText('(vídeo longo)');
    await expect(page.getByText('Ver o projeto de origem')).toBeVisible();
  });
});

test.describe('Projetos: lista, importar e Fila noturna', () => {
  test('o projeto aparece na lista com a etapa e o progresso', async ({ page }) => {
    await page.goto('/projetos');
    await expect(page.locator('h1')).toHaveText('Projetos');
    const cartao = secao(page, 'lista').locator('li', { hasText: 'Vídeo pronto' }); // só o original chegou ao vídeo final
    await expect(cartao).toHaveCount(1);
    await expect(cartao).toContainText('A Lila e a estrelinha que se perdeu');
    await expect(cartao).toContainText('6 de 7 etapas aprovadas'); // falta só a revisão
    await expect(cartao).toContainText('2 cenas');
    await expect(secao(page, 'lista').locator('li')).toHaveCount(4); // o original, a continuação de um clipe, a versão sem traduzir e o vídeo longo
  });

  test('importar o pacote traz o projeto de volta (sem sobrescrever) e recusa o que não é um pacote', async ({ page }) => {
    test.skip(!pacote, 'o pacote vem do teste da revisão');
    await page.goto('/projetos');
    const importar = secao(page, 'importar');
    await importar.locator('input[type="file"]').setInputFiles({ name: 'ruim.fabulim', mimeType: 'application/zip', buffer: Buffer.from('não sou um zip') });
    await importar.getByRole('button', { name: 'Importar o pacote' }).click();
    await expect(importar.getByRole('alert')).toBeVisible();

    await importar.locator('input[type="file"]').setInputFiles(pacote);
    await importar.getByRole('button', { name: 'Importar o pacote' }).click();
    await expect(importar.getByText(/Projeto «.*» importado/)).toBeVisible({ timeout: LONGO });
    await expect(importar.getByRole('link', { name: 'Abrir o projeto' })).toBeVisible();
  });

  test('a Fila noturna mostra o próximo trabalho liberado pelas aprovações e nunca aprova nada sozinha', async ({ page }) => {
    await page.goto('/fila');
    const noturna = page.locator('fab-night-queue');
    await expect(noturna.getByRole('heading', { name: 'Fila noturna' })).toBeVisible();
    await expect(noturna).toContainText('nunca aprova nada por conta própria');
    await expect(noturna).toContainText('Próximo trabalho');
    await expect(noturna.getByRole('button', { name: /^Enfileirar \d+ trabalhos? para a noite$/ })).toBeVisible();
  });
});

test.describe('acessibilidade das ferramentas (axe, WCAG 2.1 A e AA)', () => {
  for (const tema of ['light', 'dark'] as const) {
    for (const [nome, caminho] of [
      ['Personagens', '/personagens'],
      ['Gerar imagem', '/imagem'],
      ['Clipes', '/clipes'],
      ['Projetos', '/projetos'],
      ['Criar vídeo', '/criar'],
      ['Fila', '/fila'],
    ] as const) {
      test(`${nome} no tema ${tema}`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: tema });
        await page.goto(caminho);
        await expect(page.locator('h1')).toBeVisible();
        await page.waitForLoadState('networkidle');
        const resultado = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
        expect(resultado.violations.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.html.slice(0, 120)).join(' | ')}`)).toEqual([]);
      });
    }

    test(`o projeto, em cada etapa liberada, no tema ${tema}`, async ({ page }) => {
      test.skip(!projeto, 'o projeto vem do teste do Criar vídeo');
      // sem transições: o axe olha logo depois do clique e não pode medir a cor no meio da troca de estado do botão
      await page.emulateMedia({ colorScheme: tema, reducedMotion: 'reduce' });
      await page.goto(projeto);
      await expect(page.locator('h1')).toBeVisible();
      const etapas = page.getByRole('navigation', { name: 'Etapas do projeto' }).locator('button:not([disabled])');
      const total = await etapas.count();
      expect(total).toBeGreaterThanOrEqual(1);
      for (let i = 0; i < total; i++) {
        await etapas.nth(i).click();
        await page.waitForLoadState('networkidle');
        const resultado = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
        expect(
          resultado.violations.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.html.slice(0, 120)).join(' | ')}`),
          `etapa ${i + 1}`,
        ).toEqual([]);
      }
    });
  }
});
