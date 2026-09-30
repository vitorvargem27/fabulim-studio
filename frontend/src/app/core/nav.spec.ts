import { routes } from '../app.routes';
import { PT_BR } from './i18n/pt-br';
import { NAV_ITEMS, navIndexOf } from './nav';

describe('menu', () => {
  it('tem os nove itens do briefing, numerados de 01 a 09', () => {
    expect(NAV_ITEMS.map((i) => i.index)).toEqual(['01', '02', '03', '04', '05', '06', '07', '08', '09']);
    expect(NAV_ITEMS.map((i) => i.path)).toEqual([
      '/criar',
      '/personagens',
      '/imagem',
      '/clipes',
      '/projetos',
      '/fila',
      '/modelos',
      '/status',
      '/configuracoes',
    ]);
  });

  it('cada item aponta para uma rota que existe e tem nome em português', () => {
    const caminhos = routes.map((r) => '/' + r.path);
    for (const item of NAV_ITEMS) {
      expect(caminhos, item.path).toContain(item.path);
      expect(PT_BR[item.key], item.key).toBeTruthy();
    }
  });

  it('descobre o número do item pela URL, ignorando subpáginas, busca e âncora', () => {
    expect(navIndexOf('/criar')).toBe('01');
    expect(navIndexOf('/status/logs?service=app')).toBe('08');
    expect(navIndexOf('/modelos#voz')).toBe('07');
    expect(navIndexOf('/configuracoes')).toBe('09');
    expect(navIndexOf('/')).toBeNull();
    expect(navIndexOf('/nao-existe')).toBeNull();
  });
});
