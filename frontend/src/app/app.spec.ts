import { HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { installFakeEventSource, makeJob, provideTestHttp, SNAPSHOT_C, STATUS_REPORT, uninstallFakeEventSource, FakeEventSource } from '../testing/fixtures';
import { App } from './app';

describe('App (casca)', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<App>;
  const el = (): HTMLElement => fixture.nativeElement as HTMLElement;
  const all = <T extends Element>(selector: string): T[] => [...el().querySelectorAll<T>(selector)];

  async function iniciar(status = STATUS_REPORT): Promise<void> {
    fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    http.match('/api/status').forEach((r) => r.flush(status));
    http.match('/api/machine').forEach((r) => r.flush(SNAPSHOT_C));
    http.match('/api/benchmark').forEach((r) => r.flush({ results: [], measurements: {} }));
    http.match('/api/meta').forEach((r) => r.flush({ name: 'Fabulim Studio', version: '0.1.0', host: '127.0.0.1', port: 8765, data_dir: 'x', models_dir: 'y', tools_dir: 'z' }));
    http.match('marca/manifest.json').forEach((r) => r.flush({ icon: false, icon_png: false, logo: false, logo_dark: false }));
    await fixture.whenStable();
  }

  beforeEach(async () => {
    localStorage.clear();
    installFakeEventSource();
    await TestBed.configureTestingModule({ imports: [App], providers: provideTestHttp() }).compileComponents();
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => uninstallFakeEventSource());

  it('mostra os nove itens do menu, na ordem do briefing', async () => {
    await iniciar();
    const nomes = all<HTMLElement>('nav .label').map((n) => n.textContent?.trim());
    expect(nomes).toEqual(['Criar vídeo', 'Personagens', 'Gerar imagem', 'Clipes', 'Projetos', 'Fila', 'Modelos', 'Status', 'Configurações']);
  });

  it('tem link para pular ao conteúdo, região principal e navegação rotulada', async () => {
    await iniciar();
    expect(el().querySelector('a.skip-link')?.getAttribute('href')).toBe('#conteudo');
    expect(el().querySelector('main#conteudo')?.getAttribute('tabindex')).toBe('-1');
    expect(el().querySelector('nav')?.getAttribute('aria-label')).toBe('Navegação principal');
  });

  it('mostra o perfil da máquina e o estado do Claude no topo', async () => {
    await iniciar();
    expect(el().querySelector('.profile-chip')?.textContent).toContain('Perfil');
    expect(el().querySelector('.profile-chip .prof-letter')?.textContent?.trim()).toBe('C');
    expect(el().querySelector('fab-claude-indicator')?.textContent).toContain('Claude: conectado');
  });

  it('mostra "desconectado" quando o Claude não está ok', async () => {
    const semClaude = { ...STATUS_REPORT, services: STATUS_REPORT.services.map((s) => (s.id === 'claude' ? { ...s, state: 'inactive' as const } : s)) };
    await iniciar(semClaude);
    expect(el().querySelector('fab-claude-indicator')?.textContent).toContain('Claude: desconectado');
  });

  it('abre e fecha a gaveta pelo botão, por Esc e pelo fundo escuro', async () => {
    await iniciar();
    const botao = el().querySelector<HTMLButtonElement>('.menu-btn')!;
    const menu = el().querySelector('.sidebar')!;
    expect(botao.getAttribute('aria-expanded')).toBe('false');
    expect(menu.getAttribute('data-open')).toBe('false');
    expect(el().querySelector('.backdrop')).toBeNull();
    botao.click();
    await fixture.whenStable();
    expect(botao.getAttribute('aria-expanded')).toBe('true');
    expect(menu.getAttribute('data-open')).toBe('true');
    expect(el().querySelector('.backdrop')).not.toBeNull();

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await fixture.whenStable();
    expect(menu.getAttribute('data-open')).toBe('false');

    botao.click();
    await fixture.whenStable();
    el().querySelector<HTMLElement>('.backdrop')!.click();
    await fixture.whenStable();
    expect(menu.getAttribute('data-open')).toBe('false');
    expect(el().querySelector('.backdrop')).toBeNull();
  });

  it('o botão de fechar da gaveta também a fecha', async () => {
    await iniciar();
    const menu = el().querySelector('.sidebar')!;
    el().querySelector<HTMLButtonElement>('.menu-btn')!.click();
    await fixture.whenStable();
    expect(menu.getAttribute('data-open')).toBe('true');
    el().querySelector<HTMLButtonElement>('.close-nav')!.click();
    await fixture.whenStable();
    expect(menu.getAttribute('data-open')).toBe('false');
  });

  it('mostra a marca uma vez só (a versão larga e a de ícone ficam em invólucros que a tela escolhe)', async () => {
    await iniciar();
    expect(all('.brand fab-logo')).toHaveLength(2); // um por invólucro: `.logo-full` e `.logo-icon`
    expect(el().querySelector('.brand .logo-full')!.classList).toContain('lg:max-xl:hidden');
    expect(el().querySelector('.brand .logo-icon')!.classList).toContain('hidden');
  });

  it('a barra lateral não fala de fases de desenvolvimento', async () => {
    await iniciar();
    expect(el().textContent).not.toMatch(/\bFase\b/);
  });

  it('alterna o tema claro/escuro e atualiza o rótulo do botão', async () => {
    await iniciar();
    const botao = all<HTMLButtonElement>('header button').find((b) => /tema/i.test(b.getAttribute('aria-label') ?? ''))!;
    const antes = document.documentElement.getAttribute('data-theme');
    botao.click();
    await fixture.whenStable();
    TestBed.tick();
    expect(document.documentElement.getAttribute('data-theme')).not.toBe(antes);
  });

  it('troca o idioma para inglês e traduz o menu', async () => {
    await iniciar();
    el().querySelector<HTMLButtonElement>('.lang-btn')!.click();
    await fixture.whenStable();
    fixture.detectChanges();
    const nomes = all<HTMLElement>('nav .label').map((n) => n.textContent?.trim());
    expect(nomes[0]).toBe('Create video');
    expect(nomes.at(-1)).toBe('Settings');
    expect(document.documentElement.lang).toBe('en');
  });

  it('mostra quantas tarefas estão na fila ao lado de "Fila"', async () => {
    await iniciar();
    FakeEventSource.instances[0].emit('snapshot', { jobs: [makeJob({ status: 'running' }), makeJob({ status: 'queued' })] });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(el().querySelector('nav .count')?.textContent?.trim()).toBe('2');
  });

  it('conecta ao fluxo de eventos e consulta status, máquina e versão ao iniciar', async () => {
    await iniciar();
    expect(FakeEventSource.instances[0].url).toBe('/api/events');
    expect(el().querySelector('.side-foot')?.textContent?.trim()).toBe('Versão 0.1.0');
  });
});
