/** Os 9 itens do menu, na ordem do briefing. O número (01 a 09) é parte da identidade visual e aparece nos títulos. */
export interface NavItem {
  path: string;
  key: string;
  index: string;
}

const ITEMS: Omit<NavItem, 'index'>[] = [
  { path: '/criar', key: 'nav.criar' },
  { path: '/personagens', key: 'nav.personagens' },
  { path: '/imagem', key: 'nav.imagem' },
  { path: '/clipes', key: 'nav.clipes' },
  { path: '/projetos', key: 'nav.projetos' },
  { path: '/fila', key: 'nav.fila' },
  { path: '/modelos', key: 'nav.modelos' },
  { path: '/status', key: 'nav.status' },
  { path: '/configuracoes', key: 'nav.config' },
];

export const NAV_ITEMS: NavItem[] = ITEMS.map((item, i) => ({ ...item, index: String(i + 1).padStart(2, '0') }));

/** Número do item de menu a que uma URL pertence (ex.: `/status/logs?x=1` → "08"), ou null. */
export function navIndexOf(url: string): string | null {
  const first = '/' + (url.split(/[?#]/)[0].split('/')[1] ?? '');
  return NAV_ITEMS.find((item) => item.path === first)?.index ?? null;
}
