import { ViewportScroller } from '@angular/common';
import { HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute } from '@angular/router';

import { makeJob, provideTestHttp } from '../../../testing/fixtures';
import { JobsService } from '../../core/jobs.service';
import { Job, ToolItem, ToolsReport } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { ModelosPage } from './modelos.page';

const GB = 1024 ** 3;
const MB = 1024 ** 2;

function item(id: string, group: string, parcial: Partial<ToolItem> = {}): ToolItem {
  return { id, name: `Item ${id}`, purpose: `Serve para ${id}.`, group, license: 'MIT', installed: false, size_bytes: 50 * MB, size_estimated: true, job_id: null, ...parcial };
}

const ITENS: ToolItem[] = [
  item('ffmpeg', 'ffmpeg', { name: 'ffmpeg', installed: true, license: 'LGPL-2.1+', size_bytes: 120 * MB, size_estimated: false }),
  item('flux2-klein-4b', 'imagem', { name: 'FLUX.2 klein 4B', license: 'Apache-2.0', size_bytes: Math.round(2.3 * GB) }),
  item('kokoro-modelo', 'voz', { name: 'Kokoro (modelo)' }),
  item('birefnet-lite', 'recorte', { name: 'BiRefNet lite' }),
];

const relatorio = (itens: ToolItem[]): ToolsReport => ({ items: itens, tools_dir: 'C:\\programas', models_dir: 'C:\\modelos' });
/** O job de instalação de um item; o id do job é estável para que dois `merge` sejam o mesmo job em momentos diferentes. */
const instalacao = (id: string, parcial: Partial<Job> = {}): Job =>
  makeJob({ id: id.padEnd(32, 'x'), kind: 'ferramentas.instalar', params: { id }, status: 'running', ...parcial });

describe('ModelosPage', () => {
  let fixture: ComponentFixture<ModelosPage>;
  let http: HttpTestingController;
  let jobs: JobsService;
  const el = (): HTMLElement => fixture.nativeElement as HTMLElement;
  const botoes = (rotulo: string): HTMLButtonElement[] => [...el().querySelectorAll<HTMLButtonElement>('button')].filter((b) => b.textContent?.trim() === rotulo);

  async function abrir(itens: ToolItem[] = ITENS): Promise<void> {
    fixture = TestBed.createComponent(ModelosPage);
    fixture.detectChanges();
    http.expectOne('/api/tools').flush(relatorio(itens));
    await fixture.whenStable();
  }

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [ModelosPage], providers: provideTestHttp() });
    http = TestBed.inject(HttpTestingController);
    jobs = TestBed.inject(JobsService);
  });

  afterEach(() => http.verify());

  it('agrupa por finalidade, na ordem do fluxo, e cada grupo é um destino de âncora', async () => {
    await abrir();
    expect([...el().querySelectorAll('section h2')].map((h) => h.textContent?.trim())).toEqual(['Montagem de vídeo', 'Imagens', 'Voz', 'Recorte de fundo']);
    expect(el().querySelector('#voz section')).not.toBeNull(); // o link "Ver as vozes" da página inicial aponta para /modelos#voz
    expect(el().querySelectorAll('article.tool')).toHaveLength(4);
  });

  it('mostra para que serve, a licença e o tamanho de cada item', async () => {
    await abrir();
    const flux = [...el().querySelectorAll('article.tool')].find((a) => a.textContent?.includes('FLUX.2 klein 4B'))!;
    expect(flux.textContent).toContain('Serve para flux2-klein-4b.');
    expect(flux.textContent).toContain('Licença: Apache-2.0');
    expect(flux.textContent).toMatch(/Tamanho:\s*cerca de 2,3 GB para baixar/); // ainda não instalado: é o tamanho do download
    const ffmpeg = el().querySelector('article.tool')!;
    expect(ffmpeg.textContent).toMatch(/Tamanho:\s*120 MB/); // instalado: é o espaço que ocupa no disco
    expect(ffmpeg.textContent).not.toContain('para baixar');
  });

  it('diferencia instalado de não instalado (texto, não só cor) e só oferece instalar o que falta', async () => {
    await abrir();
    const ffmpeg = el().querySelector('article.tool')!;
    expect(ffmpeg.textContent).toContain('Instalado');
    expect(ffmpeg.querySelector('button')).toBeNull();
    expect(botoes('Instalar')).toHaveLength(3);
    expect(el().textContent).toContain('Não instalado');
  });

  it('não mostra grupos vazios', async () => {
    await abrir([ITENS[1]]);
    expect([...el().querySelectorAll('section h2')].map((h) => h.textContent?.trim())).toEqual(['Imagens']);
  });

  it('instalar coloca a instalação na fila, avisa e mostra o andamento no próprio item', async () => {
    await abrir();
    botoes('Instalar')[0].click();
    const req = http.expectOne('/api/tools/flux2-klein-4b/install');
    expect(req.request.method).toBe('POST');
    req.flush(instalacao('flux2-klein-4b', { status: 'queued' }));
    await fixture.whenStable();
    expect(TestBed.inject(ToastService).toasts().at(-1)?.text).toBe('Instalação de «FLUX.2 klein 4B» colocada na fila.');
    const flux = [...el().querySelectorAll('article.tool')].find((a) => a.textContent?.includes('FLUX.2 klein 4B'))!;
    expect(flux.textContent).toContain('Instalando');
    expect(flux.textContent).toContain('Na fila');
    expect(flux.querySelector('button')).toBeNull(); // não dá para pedir duas vezes

    jobs.merge(instalacao('flux2-klein-4b', { status: 'running', progress: 0.4, message: 'Baixando 920 MB de 2,3 GB' }));
    await fixture.whenStable();
    expect(flux.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('40');
    expect(flux.textContent).toContain('Baixando 920 MB de 2,3 GB');
  });

  it('"Instalar tudo o que falta" pede só o que falta e desliga quando não falta mais nada', async () => {
    await abrir();
    const todos = botoes('Instalar tudo o que falta')[0];
    expect(todos.disabled).toBe(false);
    todos.click();
    const pedidos = http.match((r) => r.url.endsWith('/install'));
    expect(pedidos.map((r) => r.request.url)).toEqual(['/api/tools/flux2-klein-4b/install', '/api/tools/kokoro-modelo/install', '/api/tools/birefnet-lite/install']);
    for (const r of pedidos) r.flush(instalacao(r.request.url.split('/')[3], { status: 'queued' }));
    await fixture.whenStable();
    expect(botoes('Instalar tudo o que falta')[0].disabled).toBe(true);
  });

  it('com tudo instalado, "Instalar tudo" fica desligado', async () => {
    await abrir(ITENS.map((i) => ({ ...i, installed: true })));
    expect(botoes('Instalar tudo o que falta')[0].disabled).toBe(true);
    expect(botoes('Instalar')).toHaveLength(0);
  });

  it('quando a instalação termina, recarrega a lista e avisa que ficou pronto', async () => {
    await abrir();
    jobs.merge(instalacao('kokoro-modelo', { status: 'running', progress: 0.5 }));
    await fixture.whenStable();
    http.expectNone('/api/tools');
    jobs.merge(instalacao('kokoro-modelo', { status: 'done', progress: 1, finished_at: '2026-09-29T10:05:00Z' }));
    await fixture.whenStable();
    http.expectOne('/api/tools').flush(relatorio(ITENS.map((i) => (i.id === 'kokoro-modelo' ? { ...i, installed: true } : i))));
    await fixture.whenStable();
    expect(TestBed.inject(ToastService).toasts().at(-1)).toEqual(expect.objectContaining({ tone: 'success', text: '«Kokoro (modelo)» instalado.' }));
    expect(botoes('Instalar')).toHaveLength(2);
  });

  it('quando a instalação falha, avisa e manda olhar a Fila', async () => {
    await abrir();
    jobs.merge(instalacao('birefnet-lite', { status: 'running' }));
    await fixture.whenStable();
    jobs.merge(instalacao('birefnet-lite', { status: 'failed', error: 'hash diferente', finished_at: '2026-09-29T10:05:00Z' }));
    await fixture.whenStable();
    http.expectOne('/api/tools').flush(relatorio(ITENS));
    await fixture.whenStable();
    expect(TestBed.inject(ToastService).toasts().at(-1)).toEqual(
      expect.objectContaining({ tone: 'error', text: 'Não consegui instalar «BiRefNet lite». Veja o motivo na Fila.' }),
    );
  });

  it('cancelar a instalação recarrega a lista sem alarme', async () => {
    await abrir();
    jobs.merge(instalacao('birefnet-lite', { status: 'running' }));
    await fixture.whenStable();
    jobs.merge(instalacao('birefnet-lite', { status: 'canceled', finished_at: '2026-09-29T10:05:00Z' }));
    await fixture.whenStable();
    http.expectOne('/api/tools').flush(relatorio(ITENS));
    await fixture.whenStable();
    expect(TestBed.inject(ToastService).toasts()).toHaveLength(0);
  });

  it('só cuida de jobs de instalação (os outros da fila não recarregam a lista)', async () => {
    await abrir();
    jobs.merge(makeJob({ kind: 'demo.sleep', status: 'running' }));
    await fixture.whenStable();
    jobs.merge(makeJob({ id: 'f'.repeat(32), kind: 'demo.sleep', status: 'done', finished_at: '2026-09-29T10:05:00Z' }));
    await fixture.whenStable();
    http.expectNone('/api/tools');
  });

  it('avisa quando o servidor não devolve a lista', async () => {
    fixture = TestBed.createComponent(ModelosPage);
    fixture.detectChanges();
    http.expectOne('/api/tools').flush('erro', { status: 500, statusText: 'Erro' });
    await fixture.whenStable();
    expect(el().querySelector('[role="alert"]')?.textContent).toContain('Não consegui carregar a lista de ferramentas.');
    expect(el().querySelectorAll('article.tool')).toHaveLength(0);
  });

  it('avisa quando o pedido de instalação falha', async () => {
    await abrir();
    botoes('Instalar')[0].click();
    http.expectOne('/api/tools/flux2-klein-4b/install').flush('erro', { status: 500, statusText: 'Erro' });
    await fixture.whenStable();
    expect(TestBed.inject(ToastService).toasts().at(-1)).toEqual(expect.objectContaining({ tone: 'error' }));
  });
});

describe('ModelosPage: chegada por link com âncora', () => {
  function montar(fragment: string | null): { scrollToAnchor: ReturnType<typeof vi.fn>; http: HttpTestingController; fixture: ComponentFixture<ModelosPage> } {
    const scrollToAnchor = vi.fn();
    TestBed.configureTestingModule({
      imports: [ModelosPage],
      providers: [...provideTestHttp(), { provide: ActivatedRoute, useValue: { snapshot: { fragment } } }, { provide: ViewportScroller, useValue: { scrollToAnchor } }],
    });
    const fixture = TestBed.createComponent(ModelosPage);
    fixture.detectChanges();
    return { scrollToAnchor, http: TestBed.inject(HttpTestingController), fixture };
  }

  it('rola até o grupo pedido (#voz) só depois que a lista carrega', async () => {
    const { scrollToAnchor, http, fixture } = montar('voz');
    await fixture.whenStable();
    expect(scrollToAnchor).not.toHaveBeenCalled(); // a lista ainda não chegou: não há para onde rolar
    http.expectOne('/api/tools').flush(relatorio(ITENS));
    await fixture.whenStable();
    expect(scrollToAnchor).toHaveBeenCalledExactlyOnceWith('voz');
    http.verify();
  });

  it('sem âncora, a página não rola sozinha', async () => {
    const { scrollToAnchor, http, fixture } = montar(null);
    http.expectOne('/api/tools').flush(relatorio(ITENS));
    await fixture.whenStable();
    expect(scrollToAnchor).not.toHaveBeenCalled();
    http.verify();
  });
});
