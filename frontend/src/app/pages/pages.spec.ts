import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { I18nService } from '../core/i18n/i18n.service';
import { JobsService } from '../core/jobs.service';
import { MachineService } from '../core/machine.service';
import { StatusService } from '../core/status.service';
import { ThemeService } from '../core/theme.service';
import { installFakeEventSource, makeJob, SNAPSHOT_C, STATUS_REPORT, uninstallFakeEventSource } from '../../testing/fixtures';
import { ConfiguracoesPage } from './configuracoes/configuracoes.page';
import { CriarVideoPage } from './criar-video/criar-video.page';
import { FilaPage } from './fila/fila.page';
import { NotFoundPage } from './not-found.page';

const providers = () => [provideHttpClient(), provideHttpClientTesting(), provideRouter([])];
const html = (f: ComponentFixture<unknown>): HTMLElement => f.nativeElement as HTMLElement;

describe('FilaPage', () => {
  let fixture: ComponentFixture<FilaPage>;
  let http: HttpTestingController;
  let jobs: JobsService;

  beforeEach(async () => {
    installFakeEventSource();
    await TestBed.configureTestingModule({ imports: [FilaPage], providers: providers() }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    jobs = TestBed.inject(JobsService);
    fixture = TestBed.createComponent(FilaPage);
  });

  afterEach(() => uninstallFakeEventSource());

  const seed = async (): Promise<void> => {
    jobs.loaded.set(true);
    jobs.merge(makeJob({ id: 'r'.repeat(32), title: 'Render do Short', status: 'running', progress: 0.5, message: 'Passo 10 de 20', eta_seconds: 95 }));
    jobs.merge(makeJob({ id: 'a'.repeat(32), title: 'Cenário A', status: 'queued', position: 1 }));
    jobs.merge(makeJob({ id: 'b'.repeat(32), title: 'Cenário B', status: 'queued', position: 2 }));
    jobs.merge(makeJob({ id: 'd'.repeat(32), title: 'Já feito', status: 'done', progress: 1, finished_at: '2026-09-29T09:00:00Z' }));
    await fixture.whenStable();
  };

  it('mostra o job em execução com barra, porcentagem e tempo restante', async () => {
    await seed();
    const agora = html(fixture).querySelector('article.current')!;
    expect(agora.textContent).toContain('Render do Short');
    expect(agora.textContent).toContain('Executando');
    expect(agora.textContent).toContain('50%');
    expect(agora.textContent).toContain('faltam ~1 min 35 s');
    expect(agora.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('50');
  });

  it('separa executando, na fila e concluídos', async () => {
    await seed();
    const secoes = [...html(fixture).querySelectorAll('h2')].map((h) => h.textContent?.trim());
    expect(secoes).toEqual(['Fila noturna', 'Executando agora', 'Na fila (2)', 'Concluídos (1)']);
    expect(html(fixture).querySelectorAll('.list article')).toHaveLength(3);
  });

  it('pausa, retoma e cancela chamando as rotas certas, com rótulos acessíveis', async () => {
    await seed();
    const botao = (rotulo: string): HTMLButtonElement =>
      [...html(fixture).querySelectorAll<HTMLButtonElement>('button')].find((b) => b.getAttribute('aria-label') === rotulo)!;
    botao('Pausar «Render do Short»').click();
    http.expectOne(`/api/jobs/${'r'.repeat(32)}/pause`).flush(makeJob({ id: 'r'.repeat(32), title: 'Render do Short', status: 'running', pause_requested: true }));
    await fixture.whenStable();
    expect(botao('Retomar «Render do Short»')).toBeTruthy();
    botao('Cancelar «Cenário A»').click();
    http.expectOne(`/api/jobs/${'a'.repeat(32)}/cancel`).flush(makeJob({ id: 'a'.repeat(32), title: 'Cenário A', status: 'canceled', finished_at: '2026-09-29T10:00:00Z' }));
  });

  it('reordena com os botões de subir e descer (alternativa ao arrastar)', async () => {
    await seed();
    const descer = [...html(fixture).querySelectorAll<HTMLButtonElement>('button')].find((b) => b.getAttribute('aria-label') === 'Descer «Cenário A» na fila')!;
    const subirPrimeiro = [...html(fixture).querySelectorAll<HTMLButtonElement>('button')].find((b) => b.getAttribute('aria-label') === 'Subir «Cenário A» na fila')!;
    expect(subirPrimeiro.disabled).toBe(true); // já é o primeiro
    descer.click();
    const req = http.expectOne('/api/jobs/reorder');
    expect(req.request.body).toEqual({ ids: ['b'.repeat(32), 'a'.repeat(32)] });
    req.flush([]);
    await fixture.whenStable();
    const titulos = [...html(fixture).querySelectorAll('.list article strong')].map((s) => s.textContent);
    expect(titulos.slice(0, 2)).toEqual(['Cenário B', 'Cenário A']);
  });

  it('mostra estado vazio que convida a criar um job de demonstração', async () => {
    jobs.loaded.set(true);
    await fixture.whenStable();
    const vazio = html(fixture).querySelector('fab-empty')!;
    expect(vazio.textContent).toContain('A fila está vazia');
    vazio.querySelector<HTMLButtonElement>('button')!.click();
    const req = http.expectOne('/api/jobs');
    expect(req.request.body).toEqual({ kind: 'demo.sleep', params: { seconds: 20, steps: 20 } });
    req.flush(makeJob());
  });

  it('indica se a conexão ao vivo está ativa', async () => {
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Reconectando');
    jobs.connected.set(true);
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Ao vivo');
  });

  it('mostra o erro do job que falhou', async () => {
    jobs.loaded.set(true);
    jobs.merge(makeJob({ title: 'Quebrou', status: 'failed', error: 'RuntimeError: falha', finished_at: '2026-09-29T10:00:00Z' }));
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('RuntimeError: falha');
    expect(html(fixture).textContent).toContain('Falhou');
  });
});

describe('ConfiguracoesPage', () => {
  let fixture: ComponentFixture<ConfiguracoesPage>;
  let http: HttpTestingController;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({ imports: [ConfiguracoesPage], providers: providers() }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ConfiguracoesPage);
    fixture.detectChanges();
    http.expectOne('/api/meta').flush({ name: 'Fabulim Studio', version: '0.1.0', host: '127.0.0.1', port: 8765, data_dir: 'C:\\dados', models_dir: 'C:\\modelos', tools_dir: 'C:\\programas' });
    await fixture.whenStable();
  });

  it('mostra pastas, versão e o endereço local', () => {
    const t = html(fixture).textContent!;
    expect(t).toContain('C:\\dados');
    expect(t).toContain('C:\\modelos');
    expect(t).toContain('C:\\programas');
    expect(t).toContain('127.0.0.1:8765');
    expect(t).toContain('Fabulim Studio 0.1.0');
  });

  it('trocar o tema pelo controle segmentado aplica e guarda', async () => {
    const escuro = [...html(fixture).querySelectorAll<HTMLButtonElement>('[role="radio"]')].find((b) => b.textContent?.trim() === 'Escuro')!;
    escuro.click();
    await fixture.whenStable();
    expect(TestBed.inject(ThemeService).preference()).toBe('dark');
    expect(localStorage.getItem('fabulim.theme')).toBe('dark');
  });

  it('trocar o idioma para English traduz a página', async () => {
    const ingles = [...html(fixture).querySelectorAll<HTMLButtonElement>('[role="radio"]')].find((b) => b.textContent?.trim() === 'English')!;
    ingles.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(TestBed.inject(I18nService).lang()).toBe('en');
    expect(html(fixture).querySelector('h1')?.textContent).toBe('Settings');
  });

  it('o card do Claude explica a privacidade e ainda não deixa conectar', () => {
    const card = html(fixture).querySelector('#claude')!;
    expect(card.textContent).toContain('O que é enviado ao Claude');
    expect(card.textContent).toContain('nunca lê as suas credenciais');
    expect(card.textContent).toContain('ainda não está disponível nesta versão');
    expect(card.querySelector<HTMLButtonElement>('button.btn-primary')!.disabled).toBe(true);
    expect(card.textContent).toContain('Claude: desconectado'); // ainda sem status carregado
  });

  it('a página não tem linguagem de desenvolvimento ("Fase")', () => {
    expect(html(fixture).textContent).not.toMatch(/\bFase\b/);
  });

  it('mostra "conectado" quando o status diz que o Claude está ok', async () => {
    TestBed.inject(StatusService).report.set(STATUS_REPORT);
    await fixture.whenStable();
    expect(html(fixture).querySelector('#claude')?.textContent).toContain('Claude: conectado');
  });
});

describe('páginas dos recursos', () => {
  beforeEach(async () => {
    localStorage.clear(); // o idioma escolhido fica guardado: cada teste começa em português
    await TestBed.configureTestingModule({ imports: [CriarVideoPage, NotFoundPage], providers: providers() }).compileComponents();
    TestBed.inject(MachineService).snapshot.set(SNAPSHOT_C);
  });

  afterEach(() => localStorage.clear());

  it('Criar vídeo começa pelo enredo, mostra as 7 etapas e o estado real da máquina', async () => {
    const fixture = TestBed.createComponent(CriarVideoPage);
    await fixture.whenStable();
    const el = html(fixture);
    expect(el.querySelector('fab-prompt-box')).not.toBeNull();
    expect(el.querySelectorAll('ol.flow li')).toHaveLength(7);
    expect(el.textContent).toContain('Perfil C · Notebook ou GPU integrada');
    expect(el.textContent).toContain('Animação por IA');
    expect(el.textContent).toContain('Indisponível');
    expect(el.textContent).not.toMatch(/\bFase\b/);
  });

  it('ao lado de cada tempo diz se ele foi medido ou é uma estimativa', async () => {
    const fixture = TestBed.createComponent(CriarVideoPage);
    await fixture.whenStable();
    const texto = html(fixture).textContent!.replace(/\s+/g, ' ');
    expect(texto).toContain('≈ 2,9 min por roteiro (medido)');
    expect(texto).toContain('2 a 8 min por imagem (estimado)');
    expect(texto).not.toContain('estimado: '); // sem o prefixo antigo, que repetia a palavra
  });

  it('cada etapa do caminho é um link: a primeira volta ao enredo, as outras abrem os projetos', async () => {
    const fixture = TestBed.createComponent(CriarVideoPage);
    await fixture.whenStable();
    const etapas = [...html(fixture).querySelectorAll<HTMLAnchorElement>('ol.flow li a')];
    expect(etapas.map((a) => a.getAttribute('href'))).toEqual(['/criar#comecar', ...Array<string>(6).fill('/projetos')]);
    expect(etapas[0].textContent).toContain('Enredo e personagens');
    expect(etapas[0].textContent).toContain('Começar agora');
    expect(etapas[6].textContent).toContain('Revisão e exportação');
  });

  it('em inglês as etapas continuam links e o texto muda', async () => {
    TestBed.inject(I18nService).set('en');
    const fixture = TestBed.createComponent(CriarVideoPage);
    await fixture.whenStable();
    const etapas = [...html(fixture).querySelectorAll<HTMLAnchorElement>('ol.flow li a')];
    expect(etapas).toHaveLength(7);
    expect(etapas[0].textContent).toContain('Plot and characters');
    expect(etapas[4].getAttribute('href')).toBe('/projetos');
  });

  it('a página 404 oferece o caminho de volta e fala o título uma vez só', async () => {
    const fixture = TestBed.createComponent(NotFoundPage);
    await fixture.whenStable();
    expect(html(fixture).querySelector('h1')?.textContent?.trim()).toBe('Página não encontrada');
    expect(html(fixture).textContent?.match(/Página não encontrada/g)).toHaveLength(1);
    expect(html(fixture).querySelector('a')?.getAttribute('href')).toBe('/criar');
  });
});
