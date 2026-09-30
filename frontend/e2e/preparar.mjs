// Prepara os dados do E2E: pastas limpas e o hardware.json da fixture (ThinkPad, perfil C), para o resultado ser determinístico.
import { copyFileSync, mkdirSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const aqui = dirname(fileURLToPath(import.meta.url));
const raiz = resolve(aqui, '..', '..');

for (const nome of ['e2e', 'e2e-ferramentas']) {
  const dados = join(raiz, 'data', nome);
  rmSync(dados, { recursive: true, force: true });
  mkdirSync(dados, { recursive: true });
  copyFileSync(join(raiz, 'backend', 'tests', 'fixtures', 'thinkpad_t14_gen2i.json'), join(dados, 'hardware.json'));
  console.log('[e2e] dados preparados em', dados);
}
