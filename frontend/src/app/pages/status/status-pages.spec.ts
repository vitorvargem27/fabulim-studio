import { HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';

import { JobsService } from '../../core/jobs.service';
import { MachineService } from '../../core/machine.service';
import { MachineSnapshot } from '../../core/models';
import { StatusService } from '../../core/status.service';
import { installFakeEventSource, makeJob, SNAPSHOT_C, STATUS_REPORT, uninstallFakeEventSource } from '../../../testing/fixtures';
import { LogsPage } from './logs.page';
import { MaquinaPage } from './maquina.page';
import { ServicosPage } from './servicos.page';

const providers = () => [provideHttpClient(), provideHttpClientTesting(), provideRouter([])];
const texto = (f: ComponentFixture<unknown>): string => (f.nativeElement as HTMLElement).textContent ?? '';

describe('ServicosPage', () => {
  let fixture: ComponentFixture<ServicosPage>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [ServicosPage], providers: providers() }).compileComponents();
    fixture = TestBed.createComponent(ServicosPage);
  });

  it('mostra um cartão por serviço com estado em texto e ícone (não só cor)', async () => {
    TestBed.inject(StatusService).report.set(STATUS_REPORT);
    await fixture.whenStable();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelectorAll('article.svc')).toHaveLength(5);
    const badges = [...el.querySelectorAll('fab-badge')].map((b) => b.textContent?.trim());
    expect(badges).toContain('Funcionando');
    expect(badges).toContain('Com problema');
    expect(badges).toContain('Atenção');
    expect(badges).toContain('Inativo');
    expect(badges.filter(Boolean).length).toBeGreaterThanOrEqual(6); // 5 cartões + a etiqueta geral
    expect(el.querySelectorAll('article.svc fab-badge svg').length).toBe(5);
  });

  it('separa o que pede atenção, o que funciona e o que ainda não está ativo', async () => {
    TestBed.inject(StatusService).report.set(STATUS_REPORT);
    await fixture.whenStable();
    const grupos = [...(fixture.nativeElement as HTMLElement).querySelectorAll('section')].map((s) => ({
      titulo: s.querySelector('h2')?.textContent?.trim(),
      servicos: [...s.querySelectorAll('article.svc h3')].map((h) => h.textContent?.trim()),
    }));
    expect(grupos).toEqual([
      { titulo: 'Precisam de atenção', servicos: ['LLM local (Ollama)', 'ffmpeg (montagem de vídeo)'] },
      { titulo: 'Funcionando', servicos: ['Servidor do Fabulim', 'Claude (opcional)'] },
      { titulo: 'Ainda não ativos', servicos: ['Música (ACE-Step)'] },
    ]);
  });

  it('não mostra grupos vazios', async () => {
    TestBed.inject(StatusService).report.set({ ...STATUS_REPORT, overall: 'ok', services: STATUS_REPORT.services.filter((s) => s.state === 'ok') });
    await fixture.whenStable();
    const titulos = [...(fixture.nativeElement as HTMLElement).querySelectorAll('section h2')].map((h) => h.textContent?.trim());
    expect(titulos).toEqual(['Funcionando']);
  });

  it('resume o estado geral e mostra "Como corrigir" só onde há passos', async () => {
    TestBed.inject(StatusService).report.set(STATUS_REPORT);
    await fixture.whenStable();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('[role="status"]')?.textContent).toContain('Há avisos');
    const cartoes = [...el.querySelectorAll('article.svc')];
    const ollama = cartoes.find((c) => c.textContent?.includes('LLM local'))!;
    expect(ollama.querySelector('[ngAccordionTrigger]')?.textContent?.trim()).toBe('Como corrigir');
    expect(cartoes.find((c) => c.textContent?.includes('Servidor'))!.querySelector('[ngAccordionTrigger]')).toBeNull();
  });

  it('o "Como corrigir" é um acordeão acessível: começa fechado e abre pelo teclado', async () => {
    TestBed.inject(StatusService).report.set(STATUS_REPORT);
    await fixture.whenStable();
    const ollama = [...(fixture.nativeElement as HTMLElement).querySelectorAll('article.svc')].find((c) => c.textContent?.includes('LLM local'))!;
    const gatilho = ollama.querySelector<HTMLElement>('[ngAccordionTrigger]')!;
    expect(gatilho.getAttribute('role')).toBe('button');
    expect(gatilho.getAttribute('aria-expanded')).toBe('false');
    expect(ollama.textContent).not.toContain('ollama serve'); // fechado: o conteúdo só existe depois de aberto
    gatilho.focus();
    gatilho.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await fixture.whenStable();
    expect(gatilho.getAttribute('aria-expanded')).toBe('true');
    expect(ollama.textContent).toContain('ollama serve');
  });

  it('leva aos logs do serviço certo', async () => {
    TestBed.inject(StatusService).report.set(STATUS_REPORT);
    await fixture.whenStable();
    const link = (fixture.nativeElement as HTMLElement).querySelector<HTMLAnchorElement>('a[href*="/status/logs"]')!;
    expect(link.getAttribute('href')).toContain('service=app');
  });

  it('avisa em português quando não consegue falar com o servidor', async () => {
    TestBed.inject(StatusService).error.set('unreachable');
    await fixture.whenStable();
    expect(texto(fixture)).toContain('Não consegui falar com o servidor');
    expect((fixture.nativeElement as HTMLElement).querySelector('[role="alert"]')).not.toBeNull();
  });

  it('o botão Atualizar consulta /api/status', async () => {
    const http = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
    [...(fixture.nativeElement as HTMLElement).querySelectorAll('button')].find((b) => b.textContent?.includes('Atualizar'))!.click();
    http.expectOne('/api/status').flush(STATUS_REPORT);
    await fixture.whenStable();
    expect(TestBed.inject(StatusService).report()?.overall).toBe('warning');
  });
});

describe('MaquinaPage', () => {
  let fixture: ComponentFixture<MaquinaPage>;
  let http: HttpTestingController;
  const el = (): HTMLElement => fixture.nativeElement;

  async function abrir(snapshot: MachineSnapshot = SNAPSHOT_C): Promise<void> {
    fixture = TestBed.createComponent(MaquinaPage);
    fixture.detectChanges();
    http.expectOne('/api/machine').flush(snapshot);
    http.expectOne('/api/benchmark').flush({
      // o servidor devolve em ordem alfabética; a tela põe na ordem em que o benchmark mede
      results: [
        { task: 'cutout', status: 'ok', model: 'BiRefNet lite', seconds: 30, metrics: { infer_s: 20.4 }, detail: '≈ 20 s por imagem de 1024 px, no processador.', measured_at: '2026-09-29T10:00:00Z' },
        { task: 'image', status: 'ok', model: 'FLUX.2 klein 4B (Q4_0)', seconds: 82, metrics: { wall_s: 81.7 }, detail: '≈ 82 s por imagem de 512 px (4 passos), com a placa de vídeo (Vulkan).', measured_at: '2026-09-29T10:00:00Z' },
        { task: 'llm_ollama', status: 'ok', model: 'qwen3:4b', seconds: 40, metrics: { gen_tok_s: 10.8, prefill_tok_s: 35.4, processor: 'cpu' }, detail: null, measured_at: '2026-09-29T10:00:00Z' },
        { task: 'music', status: 'skipped', model: null, seconds: null, metrics: {}, detail: 'A medição da música ainda não está disponível nesta versão.', measured_at: '2026-09-29T10:00:00Z' },
        { task: 'tts', status: 'ok', model: 'Kokoro 82M', seconds: 15, metrics: { rtf: 0.88 }, detail: 'Falou 4,9 s de áudio em 4,3 s (≈ 53 s para cada minuto de fala), no processador.', measured_at: '2026-09-29T10:00:00Z' },
      ],
      measurements: {},
    });
    await fixture.whenStable();
  }

  beforeEach(async () => {
    installFakeEventSource();
    await TestBed.configureTestingModule({ imports: [MaquinaPage], providers: providers() }).compileComponents();
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => uninstallFakeEventSource());

  it('mostra o perfil com a letra, o nome e a justificativa', async () => {
    await abrir();
    expect(el().querySelector('.letter')?.textContent?.trim()).toBe('C');
    expect(el().querySelector('#perfil-titulo')?.textContent).toContain('Perfil C · Notebook ou GPU integrada');
    expect(texto(fixture)).toContain('sem VRAM dedicada');
    expect(texto(fixture)).toContain('Espaço apertado');
    expect(texto(fixture)).toContain('23,7 GB'); // 24283 MB de orçamento
  });

  it('lista o hardware detectado em pt-BR', async () => {
    await abrir();
    const t = texto(fixture);
    expect(t).toContain('LENOVO ThinkPad T14 Gen 2i · notebook');
    expect(t).toContain('AVX, AVX2, AVX-512');
    expect(t).toContain('31,7 GB');
    expect(t).toContain('128 MB dedicados');
    expect(t).toContain('SSD (NVMe)');
    expect(t).toContain('na tomada');
  });

  it('mostra a aceleração e o benchmark medido', async () => {
    await abrir();
    const t = texto(fixture);
    expect(t).toContain('Vulkan');
    expect(t).toContain('API 1.4.313');
    expect(t).toContain('10,8 tok/s');
    expect(t).toContain('qwen3:4b');
    expect(t).toContain('Não medido');
  });

  it('mostra o que cada medição encontrou, na ordem em que o benchmark mede', async () => {
    await abrir();
    const linhas = [...el().querySelectorAll('section[aria-labelledby="bench-titulo"] table tbody tr')];
    expect(linhas.map((l) => l.querySelector('td')?.textContent?.trim())).toEqual(['LLM local (Ollama)', 'Voz', 'Recorte de fundo', 'Imagem', 'Música']);
    const t = texto(fixture);
    expect(t).toContain('≈ 82 s por imagem de 512 px (4 passos), com a placa de vídeo (Vulkan).');
    expect(t).toContain('Falou 4,9 s de áudio em 4,3 s');
    expect(t).toContain('A medição da música ainda não está disponível nesta versão.');
  });

  it('a matriz filtra por estado e mostra as contagens', async () => {
    await abrir();
    const linhas = (): number => el().querySelectorAll('table.caps tbody tr').length;
    const chips = [...el().querySelectorAll<HTMLButtonElement>('.chips button')];
    expect(chips.map((c) => c.textContent?.replace(/\s+/g, ' ').trim())).toEqual(['Todas (6)', 'Disponível (2)', 'Lenta (2)', 'Indisponível (2)']);
    expect(linhas()).toBe(6);
    chips[3].click();
    await fixture.whenStable();
    expect(linhas()).toBe(2);
    expect(chips[3].getAttribute('aria-pressed')).toBe('true');
    expect(texto(fixture)).toContain('Animação por IA');
    chips[0].click();
    await fixture.whenStable();
    expect(linhas()).toBe(6);
  });

  it('diferencia tempo medido de estimado', async () => {
    await abrir();
    const t = texto(fixture);
    expect(t).toContain('≈ 2,9 min por roteiro (medido)');
    expect(t).toContain('2 a 8 min por imagem (estimado)');
  });

  it('avisa quando a máquina mudou desde a última coleta', async () => {
    await abrir({ ...SNAPSHOT_C, changed: true });
    expect(texto(fixture)).toContain('A máquina mudou desde a última coleta completa');
  });

  it('mostra estado vazio com botão quando ainda não há diagnóstico', async () => {
    await abrir({ exists: false, valid: false, errors: [], capabilities: [], measurements: {} });
    expect(texto(fixture)).toContain('Ainda não há diagnóstico');
    expect(el().querySelector('fab-empty button')?.textContent).toContain('Refazer diagnóstico');
  });

  it('lista os problemas quando o arquivo do diagnóstico é inválido', async () => {
    await abrir({ exists: true, valid: false, errors: ['cpu.model deve ser texto'], capabilities: [], measurements: {} });
    expect(el().querySelector('[role="alert"]')?.textContent).toContain('cpu.model deve ser texto');
  });

  it('"Refazer diagnóstico" cria o job, avisa e mostra o progresso ao vivo', async () => {
    await abrir();
    [...el().querySelectorAll('button')].find((b) => b.textContent?.includes('Refazer diagnóstico'))!.click();
    const req = http.expectOne((r) => r.url === '/api/machine/diagnostic');
    expect(req.request.method).toBe('POST');
    expect(req.request.params.get('light')).toBe('false');
    req.flush(makeJob({ kind: 'system.diagnostico', title: 'Diagnóstico da máquina', status: 'running', progress: 0.4, message: 'Coletando informações da máquina...' }));
    await fixture.whenStable();
    const barra = el().querySelector('[role="progressbar"]')!;
    expect(barra.getAttribute('aria-valuenow')).toBe('40');
    expect(texto(fixture)).toContain('Coletando informações da máquina');
    const botao = [...el().querySelectorAll('button')].find((b) => b.textContent?.includes('Refazer diagnóstico'))!;
    expect(botao.disabled).toBe(true);
  });

  it('quando o job termina, recarrega os dados e avisa', async () => {
    await abrir();
    const jobs = TestBed.inject(JobsService);
    const job = makeJob({ id: 'd'.repeat(32), kind: 'system.diagnostico', title: 'Diagnóstico da máquina', status: 'running', progress: 0.5 });
    jobs.merge(job);
    await fixture.whenStable();
    jobs.merge({ ...job, status: 'done', progress: 1, finished_at: '2026-09-29T10:01:00Z' });
    await fixture.whenStable();
    http.expectOne('/api/machine').flush(SNAPSHOT_C); // recarregou sozinho
    http.expectOne('/api/benchmark').flush({ results: [], measurements: {} });
  });
});

describe('LogsPage', () => {
  it('carrega, mostra mais novos primeiro e filtra pelo serviço da URL', async () => {
    await TestBed.configureTestingModule({ imports: [LogsPage], providers: providers() }).compileComponents();
    const http = TestBed.inject(HttpTestingController);
    TestBed.inject(StatusService).report.set(STATUS_REPORT);
    const fixture = TestBed.createComponent(LogsPage);
    fixture.componentRef.setInput('service', 'fila');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const req = http.match((r) => r.url === '/api/logs').at(-1)!;
    expect(req.request.params.get('service')).toBe('fila');
    req.flush([
      { ts: '2026-09-29T10:00:00.000+00:00', level: 'INFO', service: 'fila', msg: 'primeiro' },
      { ts: '2026-09-29T10:00:01.000+00:00', level: 'ERROR', service: 'fila', msg: 'segundo' },
    ]);
    await fixture.whenStable();
    const itens = [...(fixture.nativeElement as HTMLElement).querySelectorAll('.log-list li')];
    expect(itens).toHaveLength(2);
    expect(itens[0].textContent).toContain('segundo'); // mais recente primeiro
    expect(itens[1].textContent).toContain('primeiro');
  });

  it('a lista rola sozinha, então é alcançável pelo teclado e tem nome (WCAG 2.1.1)', async () => {
    await TestBed.configureTestingModule({ imports: [LogsPage], providers: providers() }).compileComponents();
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(LogsPage);
    fixture.detectChanges();
    await fixture.whenStable();
    http.match((r) => r.url === '/api/logs').forEach((r) => r.flush([{ ts: '2026-09-29T10:00:00.000+00:00', level: 'INFO', service: 'app', msg: 'x' }]));
    await fixture.whenStable();
    const lista = (fixture.nativeElement as HTMLElement).querySelector('ol.log-list')!;
    expect(lista.getAttribute('tabindex')).toBe('0');
    expect(lista.getAttribute('aria-label')).toBe('Logs');
  });

  it('mostra estado vazio quando não há registros', async () => {
    await TestBed.configureTestingModule({ imports: [LogsPage], providers: providers() }).compileComponents();
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(LogsPage);
    fixture.detectChanges();
    await fixture.whenStable();
    http.match((r) => r.url === '/api/logs').forEach((r) => r.flush([]));
    await fixture.whenStable();
    expect(texto(fixture)).toContain('Nenhum registro ainda');
  });
});

describe('MachineService', () => {
  it('expõe perfil e capacidades a partir do retrato', () => {
    TestBed.configureTestingModule({ providers: providers() });
    const machine = TestBed.inject(MachineService);
    machine.snapshot.set(SNAPSHOT_C);
    expect(machine.profile()?.letter).toBe('C');
    expect(machine.capability('animacao_ia')?.state).toBe('unavailable');
    expect(machine.capability('nao-existe')).toBeUndefined();
    expect(machine.capabilities()).toHaveLength(6);
  });
});
