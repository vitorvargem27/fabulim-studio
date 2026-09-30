import { expect, test } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

// Gera capturas de tela de cada página nos três tamanhos e nos dois temas (só quando FABULIM_CAPTURAS aponta uma pasta).
const pasta = process.env['FABULIM_CAPTURAS'];
const PAGINAS = ['criar', 'personagens', 'imagem', 'projetos', 'fila', 'modelos', 'status/servicos', 'status/maquina', 'status/logs', 'configuracoes'];

test.describe('capturas de tela', () => {
  test.skip(!pasta, 'defina FABULIM_CAPTURAS para gerar as capturas');

  for (const tema of ['light', 'dark'] as const) {
    for (const pagina of PAGINAS) {
      test(`${pagina} (${tema})`, async ({ page }, info) => {
        await page.emulateMedia({ colorScheme: tema });
        await page.goto(`/${pagina}`);
        await expect(page.locator('h1')).toBeVisible();
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(400);
        mkdirSync(pasta as string, { recursive: true });
        const arquivo = path.join(pasta as string, `${info.project.name}-${tema}-${pagina.replace('/', '_')}.png`);
        await page.screenshot({ path: arquivo, fullPage: true });
      });
    }
  }
});
