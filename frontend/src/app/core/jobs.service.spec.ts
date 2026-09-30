import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { FakeEventSource, installFakeEventSource, makeJob, provideTestHttp, uninstallFakeEventSource } from '../../testing/fixtures';
import { applyReorder, heldByWorker, isActive, JobsService, mergeJob, sortJobs } from './jobs.service';

describe('funções da fila', () => {
  it('ordena: executando, depois a fila por prioridade e posição, depois finalizados do mais novo ao mais antigo', () => {
    const velho = makeJob({ id: 'a1', status: 'done', finished_at: '2026-09-29T09:00:00Z' });
    const novo = makeJob({ id: 'a2', status: 'failed', finished_at: '2026-09-29T10:00:00Z' });
    const b = makeJob({ id: 'b', status: 'queued', position: 2 });
    const a = makeJob({ id: 'a', status: 'queued', position: 1 });
    const urgente = makeJob({ id: 'u', status: 'queued', priority: 5, position: 9 });
    const rodando = makeJob({ id: 'r', status: 'running' });
    const ids = sortJobs([velho, novo, b, a, urgente, rodando]).map((j) => j.id);
    expect(ids).toEqual(['r', 'u', 'a', 'b', 'a2', 'a1']);
  });

  it('mergeJob substitui pelo id sem duplicar e adiciona os novos', () => {
    const a = makeJob({ id: 'x', title: 'antes' });
    const lista = mergeJob([a], { ...a, title: 'depois' });
    expect(lista).toHaveLength(1);
    expect(lista[0].title).toBe('depois');
    expect(mergeJob(lista, makeJob({ id: 'y' }))).toHaveLength(2);
  });

  it('applyReorder aplica posição 1..n e zera a prioridade só nos ids informados', () => {
    const a = makeJob({ id: 'a', position: 1 });
    const b = makeJob({ id: 'b', position: 2 });
    const c = makeJob({ id: 'c', position: 3, priority: 4 });
    const r = applyReorder([a, b, c], ['c', 'a']);
    expect(r.map((j) => j.id)).toEqual(['c', 'a', 'b']);
    expect(r.find((j) => j.id === 'c')).toMatchObject({ position: 1, priority: 0 });
  });

  it('distingue ativo, finalizado e job segurado pelo worker', () => {
    expect(isActive(makeJob({ status: 'paused' }))).toBe(true);
    expect(isActive(makeJob({ status: 'done' }))).toBe(false);
    expect(heldByWorker(makeJob({ status: 'running' }))).toBe(true);
    expect(heldByWorker(makeJob({ status: 'paused', pause_requested: true }))).toBe(true);
    expect(heldByWorker(makeJob({ status: 'paused', pause_requested: false }))).toBe(false);
  });
});

describe('JobsService', () => {
  let service: JobsService;
  let http: HttpTestingController;

  beforeEach(() => {
    installFakeEventSource();
    TestBed.configureTestingModule({ providers: provideTestHttp() });
    service = TestBed.inject(JobsService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    uninstallFakeEventSource();
  });

  it('conecta uma vez só em /api/events e mostra o estado da conexão', () => {
    service.connect();
    service.connect();
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.instances[0].url).toBe('/api/events');
    expect(service.connected()).toBe(false);
    FakeEventSource.instances[0].onopen?.();
    expect(service.connected()).toBe(true);
    FakeEventSource.instances[0].onerror?.();
    expect(service.connected()).toBe(false);
  });

  it('recebe o retrato inicial e as atualizações ao vivo', () => {
    service.connect();
    const es = FakeEventSource.instances[0];
    const rodando = makeJob({ id: 'r', status: 'running', progress: 0.2 });
    const fila = makeJob({ id: 'q', status: 'queued' });
    es.emit('snapshot', { jobs: [fila, rodando] });
    expect(service.loaded()).toBe(true);
    expect(service.jobs().map((j) => j.id)).toEqual(['r', 'q']);
    expect(service.activeCount()).toBe(2);
    expect(service.running()?.id).toBe('r');

    es.emit('job.updated', { ...rodando, progress: 0.7 });
    expect(service.jobs()[0].progress).toBe(0.7);
    es.emit('job.updated', { ...rodando, status: 'done', progress: 1, finished_at: '2026-09-29T10:00:00Z' });
    expect(service.active().map((j) => j.id)).toEqual(['q']);
    expect(service.finished().map((j) => j.id)).toEqual(['r']);
  });

  it('desconecta e fecha a fonte de eventos', () => {
    service.connect();
    service.disconnect();
    expect(FakeEventSource.instances[0].closed).toBe(true);
    expect(service.connected()).toBe(false);
  });

  it('cria job de demonstração e mescla a resposta', () => {
    service.create('demo.sleep', { seconds: 5 });
    const req = http.expectOne('/api/jobs');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ kind: 'demo.sleep', params: { seconds: 5 } });
    req.flush(makeJob({ id: 'novo' }));
    expect(service.jobs().map((j) => j.id)).toEqual(['novo']);
  });

  it('pausa, retoma e cancela pelas rotas certas', () => {
    const job = makeJob({ id: 'j'.repeat(32), status: 'running' });
    for (const action of ['pause', 'resume', 'cancel'] as const) {
      service.act(job, action);
      const req = http.expectOne(`/api/jobs/${job.id}/${action}`);
      expect(req.request.method).toBe('POST');
      req.flush({ ...job, status: action === 'cancel' ? 'canceled' : 'paused' });
    }
  });

  it('reordena de forma otimista e avisa o backend', () => {
    const a = makeJob({ id: 'a', position: 1 });
    const b = makeJob({ id: 'b', position: 2 });
    service.merge(a);
    service.merge(b);
    service.reorder(['b', 'a']);
    expect(service.jobs().map((j) => j.id)).toEqual(['b', 'a']);
    const req = http.expectOne('/api/jobs/reorder');
    expect(req.request.body).toEqual({ ids: ['b', 'a'] });
    req.flush([]);
  });

  it('limpa os concluídos localmente depois do backend confirmar', () => {
    service.merge(makeJob({ id: 'v', status: 'done', finished_at: '2026-09-29T10:00:00Z' }));
    service.merge(makeJob({ id: 'q', status: 'queued' }));
    service.clearFinished();
    http.expectOne('/api/jobs/finished').flush({ removed: 1 });
    expect(service.jobs().map((j) => j.id)).toEqual(['q']);
  });
});
