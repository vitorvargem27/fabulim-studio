// Copia os arquivos oficiais da marca (../marca) para public/marca e grava o manifest.json que a interface consulta.
// Sem os arquivos, só grava o manifest com "false": a interface mostra o logotipo em texto e nada quebra.
import { copyFileSync, existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const aqui = dirname(fileURLToPath(import.meta.url));
const origem = resolve(aqui, '..', '..', 'marca');
const destino = resolve(aqui, '..', 'public', 'marca');

const ARQUIVOS = {
  icon: 'fabulim-icone.svg',
  icon_png: 'fabulim-icone-512.png',
  logo: 'fabulim-logo.svg',
  logo_dark: 'fabulim-logo-escuro.svg',
};

mkdirSync(destino, { recursive: true });
const manifest = {};
for (const [chave, nome] of Object.entries(ARQUIVOS)) {
  const arquivo = join(origem, nome);
  manifest[chave] = existsSync(arquivo);
  if (manifest[chave]) copyFileSync(arquivo, join(destino, nome));
}
writeFileSync(join(destino, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');

const faltam = Object.entries(manifest)
  .filter(([, ok]) => !ok)
  .map(([chave]) => ARQUIVOS[chave]);
if (faltam.length) {
  console.warn(`[marca] Faltam em marca/: ${faltam.join(', ')}. A interface usa o logotipo em texto até os arquivos oficiais chegarem.`);
} else {
  console.log('[marca] Arquivos oficiais copiados para public/marca/.');
}
