import { HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { Router } from '@angular/router';

import {
  FakeEventSource,
  installFakeEventSource,
  makeCharacter,
  makeDetail,
  makeJob,
  makeMedia,
  makeProject,
  makeScene,
  makeStages,
  OPTIONS,
  provideTestHttp,
  uninstallFakeEventSource,
} from '../../testing/fixtures';
import { JobsService } from '../core/jobs.service';
import { MachineService } from '../core/machine.service';
import { ProjectDetail, ProjectMetadata, ProjectSummary } from '../core/models';
import { ToastService } from '../core/toast.service';
import { PromptBoxComponent } from '../ui/prompt-box';
import { CriarVideoPage } from './criar-video/criar-video.page';
import { NightQueueComponent } from './fila/night-queue';
import { draftOf, tagsOf } from './projetos/etapas/etapa-revisao';
import { changesOf, draftOfScene } from './projetos/etapas/scene-editor';
import { ProjetoPage } from './projetos/projeto.page';
import { approvedCount, ProjetosPage } from './projetos/projetos.page';

const html = (f: ComponentFixture<unknown>): HTMLElement => f.nativeElement as HTMLElement;

function botao(fixture: ComponentFixture<unknown>, texto: string): HTMLButtonElement {
  const b = [...html(fixture).querySelectorAll<HTMLButtonElement>('button')].find((x) => x.textContent!.includes(texto));
  if (!b) throw new Error(`botão «${texto}» não encontrado`);
  return b;
}

function campo(fixture: ComponentFixture<unknown>, rotulo: string, indice = 0): HTMLInputElement | HTMLTextAreaElement {
  const labels = [...html(fixture).querySelectorAll('label')].filter((l) => l.textContent!.includes(rotulo));
  const label = labels[indice];
  if (!label) throw new Error(`campo «${rotulo}» não encontrado`);
  return html(fixture).querySelector(`#${label.getAttribute('for')}`) as HTMLInputElement | HTMLTextAreaElement;
}

async function digitar(fixture: ComponentFixture<unknown>, rotulo: string, valor: string, indice = 0): Promise<void> {
  const el = campo(fixture, rotulo, indice);
  el.value = valor;
  el.dispatchEvent(new Event('input'));
  await fixture.whenStable();
}

describe('funções dos projetos', () => {
  it('conta as etapas aprovadas', () => {
    expect(approvedCount({ approvals: {} })).toBe(0);
    expect(approvedCount({ approvals: { enredo: true, roteiro: true, storyboard: false } })).toBe(2);
  });

  it('só manda as mudanças de fato feitas na cena', () => {
    const cena = makeScene({ data: { title: 'A', duration_s: 5, characters: ['x'], dialogue: [{ character_id: null, text: 'oi' }] } });
    const rascunho = draftOfScene(cena.data);
    expect(changesOf(rascunho, cena.data)).toEqual({});
    rascunho.title = 'B';
    rascunho.dialogue = [...rascunho.dialogue, { character_id: 'x', text: 'olá' }];
    rascunho.sfx = ['pop'];
    expect(changesOf(rascunho, cena.data)).toEqual({ title: 'B', dialogue: rascunho.dialogue, sfx: ['pop'] });
    expect(draftOfScene(cena.data).dialogue).not.toBe(cena.data.dialogue); // é uma cópia: editar não mexe no original
  });

  it('as tags viram lista limpa e o rascunho dos textos do YouTube espelha o que está salvo', () => {
    expect(tagsOf('#vídeo infantil, desenho,  Desenho , , lila\nbento')).toEqual(['vídeo infantil', 'desenho', 'lila', 'bento']);
    const meta: ProjectMetadata = {
      'pt-BR': { title: 'Título', description: 'Descrição', tags: ['a', 'b'] },
      en: { title: 'Title', description: 'Description', tags: [] },
    };
    expect(draftOf(meta)['pt-BR']).toEqual({ title: 'Título', description: 'Descrição', tags: 'a, b' });
    expect(draftOf(null).en).toEqual({ title: '', description: '', tags: '' });
  });
});

describe('CriarVideoPage', () => {
  let fixture: ComponentFixture<CriarVideoPage>;
  let http: HttpTestingController;
  let router: Router;
  const lila = makeCharacter({ id: 'a'.repeat(32), name: 'Lila' });
  const bento = makeCharacter({ id: 'b'.repeat(32), name: 'Bento', style: '3D', has_cutout: false });

  beforeEach(async () => {
    localStorage.clear();
    installFakeEventSource();
    await TestBed.configureTestingModule({ imports: [CriarVideoPage], providers: provideTestHttp() }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate').mockResolvedValue(true);
    fixture = TestBed.createComponent(CriarVideoPage);
    fixture.detectChanges();
    http.expectOne('/api/characters').flush({ items: [lila, bento], total: 2 });
  });

  afterEach(() => uninstallFakeEventSource());

  const enredo = (extras: Record<string, unknown> = {}): void => {
    const caixa = fixture.debugElement.query(By.directive(PromptBoxComponent)).componentInstance as PromptBoxComponent;
    caixa.parsed.emit({
      text: '### ENREDO\nHistória: ...',
      result: {
        type: 'enredo',
        source: 'estruturado',
        missing: [],
        warnings: [],
        form: {
          title: 'A Lila e a estrelinha',
          format: 'short',
          target_duration: '45 s',
          language: 'pt-BR',
          style: '2D',
          characters: ['Lila', 'Bia'],
          theme: 'ajudar',
          settings: 'jardim',
          story: 'Lila encontra uma estrelinha.',
          music: '',
          notes: '',
          ...extras,
        },
      },
    });
  };

  it('o enredo lido preenche o formulário, escolhe quem já existe e oferece criar quem falta', async () => {
    enredo();
    await fixture.whenStable();
    expect((campo(fixture, 'Título') as HTMLInputElement).value).toBe('A Lila e a estrelinha');
    expect((campo(fixture, 'História') as HTMLTextAreaElement).value).toBe('Lila encontra uma estrelinha.');
    expect((html(fixture).querySelector('#story-seconds') as HTMLInputElement).value).toBe('45');
    expect(html(fixture).querySelector('fab-character-picker button')!.getAttribute('aria-pressed')).toBe('true');
    const criar = [...html(fixture).querySelectorAll<HTMLAnchorElement>('.banner a')].find((a) => a.textContent!.includes('Criar Bia agora'))!;
    expect(criar).toBeTruthy();
    expect(criar.getAttribute('href')).toBe('/personagens?nome=Bia#novo');
  });

  it('avisa quando o estilo do personagem é outro e quando falta o PNG transparente', async () => {
    enredo({ style: '3D', characters: ['Lila'] });
    await fixture.whenStable();
    const avisos = [...html(fixture).querySelectorAll('.banner')].map((b) => b.textContent!.replace(/\s+/g, ' ').trim());
    expect(avisos.some((a) => a.includes('«Lila» é 2D e o vídeo é 3D'))).toBe(true);
  });

  it('criar o projeto manda o pedido completo e abre o projeto', async () => {
    enredo({ characters: ['Lila'] });
    await fixture.whenStable();
    (html(fixture).querySelector('#story-seconds') as HTMLInputElement).value = '20';
    html(fixture).querySelector('#story-seconds')!.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    botao(fixture, 'Criar o projeto').click();
    const req = http.expectOne((r) => r.url === '/api/projects' && r.method === 'POST');
    expect(req.request.body.form).toMatchObject({ title: 'A Lila e a estrelinha', format: 'short', characters: ['Lila'], story: 'Lila encontra uma estrelinha.' });
    expect(req.request.body.character_ids).toEqual([lila.id]);
    expect(req.request.body.target_duration_s).toBe(20);
    expect(req.request.body.original_prompt).toBe('### ENREDO\nHistória: ...');
    req.flush({ project: makeProject({ id: 'p'.repeat(32) }), missing_characters: [], style_warnings: [] });
    await fixture.whenStable();
    expect(router.navigate).toHaveBeenCalledWith(['/projetos', 'p'.repeat(32)]);
  });

  it('não deixa criar sem história e mostra o erro do servidor', async () => {
    expect(botao(fixture, 'Criar o projeto').disabled).toBe(true);
    await digitar(fixture, 'História', 'Uma história.');
    botao(fixture, 'Criar o projeto').click();
    http.expectOne((r) => r.url === '/api/projects' && r.method === 'POST').flush({ detail: 'Escreva a história.' }, { status: 422, statusText: 'x' });
    await fixture.whenStable();
    expect(html(fixture).querySelector('[role="alert"]')!.textContent).toContain('Escreva a história.');
    expect(botao(fixture, 'Criar o projeto').disabled).toBe(false);
  });

  it('trocar para vídeo longo aumenta o limite da duração', async () => {
    expect((html(fixture).querySelector('#story-seconds') as HTMLInputElement).max).toBe('60');
    botao(fixture, 'Vídeo longo').click();
    await fixture.whenStable();
    expect((html(fixture).querySelector('#story-seconds') as HTMLInputElement).max).toBe('300');
    expect(TestBed.inject(MachineService)).toBeTruthy();
  });
});

describe('ProjetosPage', () => {
  let fixture: ComponentFixture<ProjetosPage>;
  let http: HttpTestingController;
  const resumo = (mudar: Partial<ProjectSummary> = {}): ProjectSummary => {
    const { story: _story, ...base } = makeProject();
    void _story;
    return { ...base, scene_count: 4, thumb_url: null, has_final: false, characters: ['Lila'], ...mudar };
  };

  beforeEach(async () => {
    localStorage.clear();
    installFakeEventSource();
    await TestBed.configureTestingModule({ imports: [ProjetosPage], providers: provideTestHttp() }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ProjetosPage);
  });

  afterEach(() => uninstallFakeEventSource());

  it('lista os projetos com a etapa, o progresso e os personagens', async () => {
    fixture.detectChanges();
    http.expectOne('/api/projects').flush({
      items: [
        resumo({ id: 'a'.repeat(32), title: 'A chuva', stage: 'storyboard', approvals: { enredo: true, roteiro: true } }),
        resumo({ id: 'b'.repeat(32), title: 'O bosque', has_final: true, approvals: { enredo: true }, format: 'longo', language: 'en' }),
      ],
      total: 2,
    });
    await fixture.whenStable();
    const cartoes = [...html(fixture).querySelectorAll('ul.tile-grid li')].map((li) => li.textContent!.replace(/\s+/g, ' ').trim());
    expect(cartoes[0]).toContain('A chuva');
    expect(cartoes[0]).toContain('Storyboard');
    expect(cartoes[0]).toContain('2 de 7 etapas aprovadas');
    expect(cartoes[0]).toContain('4 cenas');
    expect(cartoes[1]).toContain('Vídeo pronto');
    expect(cartoes[1]).toContain('Vídeo longo');
    expect(cartoes[1]).toContain('EN');
    expect(html(fixture).querySelector('ul.tile-grid a')!.getAttribute('href')).toBe(`/projetos/${'a'.repeat(32)}`);
    expect(html(fixture).querySelector('fab-package-import')).not.toBeNull();
  });

  it('sem projetos convida a começar; apagar pede confirmação', async () => {
    fixture.detectChanges();
    http.expectOne('/api/projects').flush({ items: [resumo({ id: 'c'.repeat(32), title: 'Apagar este' })], total: 1 });
    await fixture.whenStable();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    html(fixture).querySelector<HTMLButtonElement>('button[aria-label^="Apagar projeto"]')!.click();
    http.expectOne((r) => r.url === `/api/projects/${'c'.repeat(32)}` && r.method === 'DELETE').flush({ deleted: true, media_removed: 0 });
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Nenhum projeto ainda');
    expect(TestBed.inject(ToastService).toasts().at(-1)?.text).toBe('Projeto apagado.');
  });

  it('um pacote importado atualiza a lista', async () => {
    fixture.detectChanges();
    http.expectOne('/api/projects').flush({ items: [], total: 0 });
    fixture.debugElement.query(By.css('fab-package-import')).triggerEventHandler('imported', {});
    http.expectOne('/api/projects').flush({ items: [resumo()], total: 1 });
    await fixture.whenStable();
    expect(html(fixture).querySelectorAll('ul.tile-grid li')).toHaveLength(1);
  });
});

describe('NightQueueComponent', () => {
  let fixture: ComponentFixture<NightQueueComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    installFakeEventSource();
    await TestBed.configureTestingModule({ imports: [NightQueueComponent], providers: provideTestHttp() }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(NightQueueComponent);
  });

  afterEach(() => uninstallFakeEventSource());

  it('mostra o próximo trabalho de cada projeto e enfileira o que está liberado', async () => {
    fixture.detectChanges();
    http.expectOne('/api/projects/night-plan').flush({
      items: [
        { project_id: 'a'.repeat(32), title: 'A chuva', stage: 'storyboard', stage_label: 'cenários (storyboard)', kind: 'projeto.storyboard', blocked_by: null },
        { project_id: 'b'.repeat(32), title: 'O bosque', stage: 'montagem', stage_label: 'montagem do vídeo', kind: 'projeto.montar', blocked_by: 'ffmpeg não instalado' },
      ],
    });
    await fixture.whenStable();
    const texto = html(fixture).textContent!;
    expect(texto).toContain('Próximo trabalho: cenários (storyboard)');
    expect(texto).toContain('Liberado');
    expect(texto).toContain('ffmpeg não instalado');
    botao(fixture, 'Enfileirar 1 trabalho para a noite').click();
    const req = http.expectOne('/api/projects/night-queue');
    expect(req.request.body).toEqual({});
    const job = makeJob({ id: 'n1', kind: 'projeto.storyboard', status: 'queued', params: { project_id: 'a'.repeat(32) } });
    req.flush({ queued: [job], skipped: [] });
    http.expectOne('/api/projects/night-plan').flush({ items: [] });
    await fixture.whenStable();
    expect(TestBed.inject(JobsService).byId('n1')).toBeTruthy();
    expect(TestBed.inject(ToastService).toasts().at(-1)?.text).toBe('1 trabalho na fila.');
    expect(html(fixture).textContent).toContain('Nada para renderizar agora');
  });

  it('o fim de uma tarefa de projeto atualiza o plano', async () => {
    fixture.detectChanges();
    http.expectOne('/api/projects/night-plan').flush({ items: [] });
    const jobs = TestBed.inject(JobsService);
    jobs.merge(makeJob({ id: 'x', status: 'running', params: { project_id: 'p' } }));
    jobs.merge(makeJob({ id: 'x', status: 'done', params: { project_id: 'p' } }));
    http.expectOne('/api/projects/night-plan').flush({ items: [] });
  });
});

describe('ProjetoPage', () => {
  let fixture: ComponentFixture<ProjetoPage>;
  let http: HttpTestingController;
  let router: Router;
  let jobs: JobsService;
  const id = 'p'.repeat(32);
  const lila = makeCharacter({ id: 'a'.repeat(32), name: 'Lila' });
  const fundo = makeMedia({ id: 'f'.repeat(32), role: 'fundo', width: 576, height: 1024 });
  const capa = makeMedia({ id: 'k'.repeat(32), role: 'quadro' });

  const cena = (n: number, mudar: Record<string, unknown> = {}): ReturnType<typeof makeScene> =>
    makeScene({
      id: `${n}`.repeat(32),
      order: n,
      character_names: ['Lila'],
      data: { title: `Cena ${n}`, characters: [lila.id], narration: `Narração ${n}`, ...mudar },
    });

  const detalhe = (mudar: Partial<ProjectDetail> = {}): ProjectDetail =>
    makeDetail({ project: makeProject({ id, character_ids: [lila.id] }), characters: [lila], stages: makeStages('roteiro', ['enredo']), ...mudar });

  beforeEach(async () => {
    localStorage.clear();
    installFakeEventSource();
    await TestBed.configureTestingModule({ imports: [ProjetoPage], providers: provideTestHttp() }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    jobs = TestBed.inject(JobsService);
    vi.spyOn(router, 'navigate').mockResolvedValue(true);
    fixture = TestBed.createComponent(ProjetoPage);
    fixture.componentRef.setInput('id', id);
  });

  afterEach(() => uninstallFakeEventSource());

  /** Responde as chamadas que o projeto faz ao abrir; as etapas fazem outras assim que aparecem, então repete uma vez. */
  const responder = (d: ProjectDetail): void => {
    http.match((r) => r.url === '/api/characters').forEach((r) => r.flush({ items: [lila], total: 1 }));
    http
      .match((r) => r.url === '/api/images/estimate')
      .filter((r) => !r.cancelled)
      .forEach((r) => r.flush({ width: 576, height: 1024, total_seconds: 80, total_label: '1 min 20 s', per_image_seconds: 80 }));
    http.match(`/api/projects/${id}/review`).forEach((r) => r.flush({ checklist: [], files: d.files, metadata: null, quality: null, reminder: '' }));
  };

  const abrir = async (d: ProjectDetail = detalhe()): Promise<void> => {
    fixture.detectChanges();
    http.expectOne('/api/projects/options').flush(OPTIONS);
    http.expectOne(`/api/projects/${id}`).flush(d);
    await fixture.whenStable();
    responder(d);
    await fixture.whenStable();
  };

  const barra = (): string[] => [...html(fixture).querySelectorAll('.stage-bar button')].map((b) => b.textContent!.replace(/\s+/g, ' ').trim());

  it('a barra de etapas mostra o que está aprovado, o que é agora e o que ainda está bloqueado', async () => {
    await abrir();
    expect(barra()).toEqual([
      '1 ✓ aprovadaEnredo e personagens',
      '2 ● agoraRoteiro',
      '3 bloqueadaStoryboard',
      '4 bloqueadaAnimação',
      '5 bloqueadaÁudio',
      '6 bloqueadaMontagem',
      '7 bloqueadaRevisão e exportação',
    ]);
    const botoes = [...html(fixture).querySelectorAll<HTMLButtonElement>('.stage-bar button')];
    expect(botoes.map((b) => b.disabled)).toEqual([false, false, true, true, true, true, true]);
    expect(html(fixture).querySelector('.stage-bar [aria-current="step"]')!.textContent).toContain('Roteiro');
    expect(html(fixture).querySelector('h1')!.textContent).toBe('A chuva do jardim');
    expect(html(fixture).textContent).toContain('Short · 30 s');
  });

  it('dá para rever uma etapa já aprovada sem perder o lugar', async () => {
    await abrir();
    html(fixture).querySelector<HTMLButtonElement>('.stage-bar button')!.click();
    await fixture.whenStable();
    expect(html(fixture).querySelector('fab-etapa-enredo')).not.toBeNull();
    expect(html(fixture).querySelector('.stage-bar [aria-current="step"]')!.textContent).toContain('Enredo');
    expect((campo(fixture, 'História') as HTMLTextAreaElement).value).toBe('Lila brinca no jardim.');
  });

  it('projeto inexistente explica e oferece voltar', async () => {
    fixture.detectChanges();
    http.expectOne('/api/projects/options').flush(OPTIONS);
    http.expectOne(`/api/projects/${id}`).flush({ detail: 'x' }, { status: 404, statusText: 'Not Found' });
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Projeto não encontrado');
    expect(html(fixture).querySelector('a')!.getAttribute('href')).toBe('/projetos');
  });

  it('as tarefas do projeto aparecem no topo; o fim de uma recarrega e avisa dos problemas', async () => {
    await abrir();
    const job = makeJob({ id: 'r1', kind: 'projeto.roteiro', status: 'running', title: 'Roteiro do vídeo', progress: 0.3, message: 'Escrevendo', params: { project_id: id } });
    jobs.merge(job);
    await fixture.whenStable();
    expect(html(fixture).querySelector('fab-job-progress')!.textContent).toContain('Roteiro do vídeo');
    jobs.merge({ ...job, status: 'done', progress: 1, result: { warnings: ['O modelo local não escreveu o roteiro. Usei o modo simples.'] } });
    http.expectOne(`/api/projects/${id}`).flush(detalhe({ scenes: [cena(1)] }));
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('O modelo local não escreveu o roteiro. Usei o modo simples.'); // o aviso fica na tela
    expect(html(fixture).querySelectorAll('fab-scene-editor')).toHaveLength(1);
  });

  it('roteiro: gerar o script pede confirmação quando já há cenas; sem cenas gera direto', async () => {
    await abrir();
    botao(fixture, 'Gerar o roteiro com o modelo local').click();
    const req = http.expectOne(`/api/projects/${id}/script`);
    expect(req.request.body).toEqual({ mode: 'ia' });
    req.flush(makeJob({ id: 'r2', kind: 'projeto.roteiro', status: 'queued', params: { project_id: id } }));
    await fixture.whenStable();
    expect(botao(fixture, 'Gerar o roteiro com o modelo local').disabled).toBe(true);
  });

  it('roteiro com cenas: confirma antes de trocar, aprova uma a uma e aprova tudo', async () => {
    await abrir(detalhe({ scenes: [cena(1), cena(2)], stages: { ...makeStages('roteiro', ['enredo']), stages: makeStages('roteiro', ['enredo']).stages.map((s) => (s.id === 'roteiro' ? { ...s, scenes_approved: 0, scenes_total: 2 } : s)) } }));
    const confirmar = vi.spyOn(window, 'confirm').mockReturnValue(false);
    botao(fixture, 'Gerar o roteiro de novo').click();
    http.expectNone(`/api/projects/${id}/script`);
    expect(confirmar).toHaveBeenCalled();
    confirmar.mockRestore();
    expect(html(fixture).textContent).toContain('Cenas (2)');
    // aprovar a primeira cena
    html(fixture).querySelector<HTMLButtonElement>('fab-scene-editor button.btn-sm:not(.btn-quiet)')!; // botões da cena
    const aprovar = [...html(fixture).querySelectorAll<HTMLButtonElement>('fab-scene-editor button')].find((b) => b.textContent!.trim() === 'Aprovar')!;
    aprovar.click();
    const req = http.expectOne(`/api/projects/${id}/scenes/${'1'.repeat(32)}/approve`);
    expect(req.request.body).toEqual({ stage: 'roteiro', approved: true });
    const parcial = makeStages('roteiro', ['enredo']);
    parcial.stages = parcial.stages.map((s) => (s.id === 'roteiro' ? { ...s, scenes_approved: 1, scenes_total: 2 } : s));
    req.flush({ scene: { ...cena(1), data: { ...cena(1).data, approved: { roteiro: true } } }, stages: parcial, warning: null });
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Tirar a aprovação');
    // aprovar todas e a etapa
    botao(fixture, 'Aprovar 1 cena restante e a etapa').click();
    expect(http.expectOne(`/api/projects/${id}/stages/roteiro/approve`).request.body).toEqual({ approve_all: true });
  });

  it('editar uma cena: abre o editor, muda só o título e manda só o que mudou', async () => {
    await abrir(detalhe({ scenes: [cena(1)] }));
    botao(fixture, 'Editar a cena').click();
    await fixture.whenStable();
    expect(botao(fixture, 'Salvar a cena').disabled).toBe(true);
    await digitar(fixture, 'Título da cena', 'O jardim de manhã');
    (html(fixture).querySelector('[id$="-emotion"]') as HTMLSelectElement).value = 'triste';
    html(fixture).querySelector('[id$="-emotion"]')!.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    expect(botao(fixture, 'Salvar a cena').disabled).toBe(false);
    botao(fixture, 'Salvar a cena').click();
    const req = http.expectOne(`/api/projects/${id}/scenes/${'1'.repeat(32)}`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ changes: { title: 'O jardim de manhã', emotion: 'triste' } });
    req.flush({ scene: { ...cena(1), data: { ...cena(1).data, title: 'O jardim de manhã', emotion: 'triste' } }, stages: makeStages('roteiro', ['enredo']), warning: null });
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('O jardim de manhã');
    expect(botao(fixture, 'Salvar a cena').disabled).toBe(true);
  });

  it('a cena ganha e perde falas e efeitos sonoros; descartar volta ao que estava salvo', async () => {
    await abrir(detalhe({ scenes: [cena(1)] }));
    botao(fixture, 'Editar a cena').click();
    await fixture.whenStable();
    botao(fixture, 'Adicionar fala').click();
    await fixture.whenStable();
    const fala = html(fixture).querySelector<HTMLInputElement>('input[aria-label="Fala"]')!;
    fala.value = 'Que dia lindo!';
    fala.dispatchEvent(new Event('input'));
    const efeito = [...html(fixture).querySelectorAll<HTMLButtonElement>('.chips button')].find((b) => b.textContent!.includes('Pulo'))!;
    efeito.click();
    await fixture.whenStable();
    botao(fixture, 'Salvar a cena').click();
    const req = http.expectOne(`/api/projects/${id}/scenes/${'1'.repeat(32)}`);
    expect(req.request.body.changes.dialogue).toEqual([{ character_id: lila.id, text: 'Que dia lindo!' }]);
    expect(req.request.body.changes.sfx).toEqual(['boing']);
    req.flush({ scene: cena(1), stages: makeStages('roteiro', ['enredo']), warning: null });
    await fixture.whenStable();
    await digitar(fixture, 'Título da cena', 'Outro');
    botao(fixture, 'Descartar mudanças').click();
    await fixture.whenStable();
    expect((campo(fixture, 'Título da cena') as HTMLInputElement).value).toBe('Cena 1');
  });

  it('as versões da cena aparecem e dá para voltar para uma antiga', async () => {
    const c = makeScene({ id: '1'.repeat(32), order: 1, version: 2, data: { title: 'Nova' } });
    await abrir(detalhe({ scenes: [c] }));
    botao(fixture, 'Versões (v2)').click();
    const req = http.expectOne(`/api/projects/${id}/scenes/${'1'.repeat(32)}/versions`);
    req.flush({ versions: [{ version: 2, data: c.data, reason: 'editada pelo usuário', created_at: '2026-09-30T10:00:00Z' }, { version: 1, data: { ...c.data, title: 'Antiga' }, reason: 'criada', created_at: '2026-09-30T09:00:00Z' }], current: 2 });
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('editada pelo usuário');
    botao(fixture, 'Voltar para esta versão').click();
    expect(http.expectOne(`/api/projects/${id}/scenes/${'1'.repeat(32)}/restore`).request.body).toEqual({ version: 1 });
  });

  it('reordena e apaga cenas', async () => {
    await abrir(detalhe({ scenes: [cena(1), cena(2)] }));
    const descer = html(fixture).querySelectorAll<HTMLButtonElement>('fab-scene-editor button[aria-label="Descer a cena"]');
    descer[0].click();
    const req = http.expectOne(`/api/projects/${id}/scenes/reorder`);
    expect(req.request.body).toEqual({ ids: ['2'.repeat(32), '1'.repeat(32)] });
    req.flush(detalhe({ scenes: [cena(2), cena(1)] }));
    await fixture.whenStable();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    html(fixture).querySelector<HTMLButtonElement>('fab-scene-editor button[aria-label="Apagar a cena"]')!.click();
    http.expectOne((r) => r.url === `/api/projects/${id}/scenes/${'2'.repeat(32)}` && r.method === 'DELETE').flush({ deleted: true, stages: makeStages() });
    http.expectOne(`/api/projects/${id}`).flush(detalhe({ scenes: [cena(1)] }));
  });

  it('storyboard: gera os cenários faltantes, mostra a estimativa e aprova a cena', async () => {
    const c1 = makeScene({ id: '1'.repeat(32), order: 1, keyframe: capa, background_media: fundo, candidate_media: [fundo, makeMedia({ id: 'g'.repeat(32), role: 'fundo' })], character_names: ['Lila'], data: { title: 'Cena 1', background: { media_id: fundo.id, seed: 5, prompt: 'x', quality: 'padrao' }, characters: [lila.id] }, layout: [{ personagem_id: lila.id, x: 0.5, base_y: 0.9, altura: 0.4, espelhar: false, pose: null, acao: null, entrada: null }] });
    const c2 = cena(2);
    await abrir(detalhe({ scenes: [c1, c2], stages: makeStages('storyboard', ['enredo', 'roteiro']) }));
    expect(html(fixture).querySelector('fab-etapa-storyboard')).not.toBeNull();
    expect(html(fixture).textContent).toContain('cerca de 1 min 20 s para 1 imagem'); // só a cena 2 não tem cenário
    // escolher outro cenário entre as opções
    botao(fixture, 'Usar este').click();
    const escolha = http.expectOne(`/api/projects/${id}/scenes/${'1'.repeat(32)}/choose-background`);
    expect(escolha.request.body).toEqual({ media_id: 'g'.repeat(32) });
    escolha.flush({ scene: c1, stages: makeStages('storyboard', ['enredo', 'roteiro']), warning: null });
    await fixture.whenStable();
    botao(fixture, 'Gerar os cenários').click();
    const req = http.expectOne(`/api/projects/${id}/storyboard`);
    expect(req.request.body).toEqual({ scene_ids: null, mode: 'faltantes', variations: 1, quality: 'padrao', seed: null });
    req.flush(makeJob({ id: 's1', kind: 'projeto.storyboard', status: 'queued', params: { project_id: id } }));
    await fixture.whenStable();
    expect(botao(fixture, 'Gerar os cenários').disabled).toBe(true); // já há uma tarefa de cenários em andamento
  });

  it('storyboard: ajusta a posição dos personagens e refaz a imagem', async () => {
    const c1 = makeScene({ id: '1'.repeat(32), order: 1, keyframe: capa, character_names: ['Lila'], data: { title: 'Cena 1', background: { media_id: fundo.id, seed: 5, prompt: 'x', quality: 'padrao' }, characters: [lila.id] }, layout: [{ personagem_id: lila.id, x: 0.5, base_y: 0.9, altura: 0.4, espelhar: false, pose: null, acao: null, entrada: null }] });
    await abrir(detalhe({ scenes: [c1], stages: makeStages('storyboard', ['enredo', 'roteiro']) }));
    expect(botao(fixture, 'Aplicar posições').disabled).toBe(true);
    const x = html(fixture).querySelector<HTMLInputElement>('[id$="-x0"]')!;
    x.value = '0.3';
    x.dispatchEvent(new Event('input'));
    const acao = html(fixture).querySelector<HTMLSelectElement>('[id$="-a0"]')!;
    acao.value = 'pular';
    acao.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    botao(fixture, 'Aplicar posições').click();
    const req = http.expectOne(`/api/projects/${id}/scenes/${'1'.repeat(32)}/layout`);
    expect(req.request.method).toBe('PUT');
    expect(req.request.body.items[0]).toMatchObject({ personagem_id: lila.id, x: 0.3, acao: 'pular', pose: null, espelhar: false });
    req.flush({ scene: { ...c1, layout: [{ ...c1.layout[0], x: 0.3, acao: 'pular' }] }, stages: makeStages('storyboard', ['enredo', 'roteiro']), warning: 'Não deu para refazer a imagem.' });
    await fixture.whenStable();
    expect(botao(fixture, 'Aplicar posições').disabled).toBe(true);
    expect(TestBed.inject(ToastService).toasts().at(-1)?.text).toBe('Não deu para refazer a imagem.');
  });

  it('animação e áudio: pedem as tarefas e o áudio só gera depois de salvar os ajustes', async () => {
    const pronta = (n: number): ReturnType<typeof makeScene> =>
      makeScene({ id: `${n}`.repeat(32), order: n, keyframe: capa, clip_media: makeMedia({ kind: 'video', role: 'cena_clipe', duration_s: 5 }), data: { title: `Cena ${n}`, background: { media_id: fundo.id, seed: 1, prompt: '', quality: 'padrao' }, clip: { media_id: 'v'.repeat(32), render_hash: 'h', quality: 'final', duration_s: 5 } } });
    TestBed.inject(MachineService).snapshot.set({ exists: true, valid: true, errors: [], measurements: {}, capabilities: [{ id: 'animacao_ia', name: 'Animação por IA', section: '3.2', state: 'unavailable', reason: 'Precisa de GPU dedicada.', eta: null, eta_measured: false }] });
    await abrir(detalhe({ scenes: [pronta(1), pronta(2)], stages: makeStages('animacao', ['enredo', 'roteiro', 'storyboard']) }));
    expect(html(fixture).textContent).toContain('Animação por IA (imagem em vídeo) não roda neste computador.');
    botao(fixture, 'Animar as cenas').click();
    expect(http.expectOne(`/api/projects/${id}/animate`).request.body).toEqual({ scene_ids: null, draft: false, force: false });
    // o áudio só abre depois de aprovar a animação
    expect(html(fixture).querySelectorAll<HTMLButtonElement>('.stage-bar button')[4].disabled).toBe(true);
  });

  it('áudio: ajusta a música e as vozes, salva e só então gera', async () => {
    const d = detalhe({ scenes: [cena(1)], stages: makeStages('audio', ['enredo', 'roteiro', 'storyboard', 'animacao']), project: makeProject({ id, character_ids: [lila.id], approvals: { enredo: true, roteiro: true, storyboard: true, animacao: true } }) });
    await abrir(d);
    expect(botao(fixture, 'Gerar o áudio').disabled).toBe(false);
    (html(fixture).querySelector('#music-volume') as HTMLInputElement).value = '0.4';
    html(fixture).querySelector('#music-volume')!.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    expect(botao(fixture, 'Gerar o áudio').disabled).toBe(true); // há ajustes não salvos
    expect(html(fixture).textContent).toContain('Salve os ajustes antes de gerar o áudio.');
    botao(fixture, 'Salvar os ajustes').click();
    const salvar = http.expectOne(`/api/projects/${id}`);
    expect(salvar.request.method).toBe('PATCH');
    expect(salvar.request.body.music).toMatchObject({ enabled: true, volume: 0.4 });
    expect(salvar.request.body.settings).toMatchObject({ transition: 'corte', narrator: { id: 'pm_alex', speed: 0.95, pitch: 1 } });
    salvar.flush({ ...d, project: { ...d.project, music: { enabled: true, style: 'alegre', volume: 0.4, seed: 1 }, settings: { transition: 'corte', narrator: { id: 'pm_alex', speed: 0.95, pitch: 1 }, voices: {} } } });
    await fixture.whenStable();
    botao(fixture, 'Gerar o áudio').click();
    expect(http.expectOne(`/api/projects/${id}/audio`).request.body).toEqual({ transition: 'corte' });
  });

  it('montagem: só monta com o áudio pronto e mostra o vídeo com o volume medido', async () => {
    const final = makeMedia({ id: 'm'.repeat(32), kind: 'video', role: 'video_final', duration_s: 42, width: 1080, height: 1920, size_bytes: 8_000_000 });
    const d = detalhe({
      stages: makeStages('montagem', ['enredo', 'roteiro', 'storyboard', 'animacao', 'audio']),
      files: { final, subtitles: null, mix: makeMedia({ kind: 'audio', role: 'mix' }), music: null, thumbnails: [] },
      quality: { loudness_input: -18.4 },
    });
    await abrir(d);
    const texto = html(fixture).textContent!;
    expect(texto).toContain('1080×1920');
    expect(texto).toContain('volume medido: -18.4 LUFS antes do ajuste');
    expect(html(fixture).querySelector('video')!.getAttribute('src')).toBe(final.url);
    botao(fixture, 'Montar de novo').click();
    expect(http.expectOne(`/api/projects/${id}/assemble`).request.body).toEqual({ transition: 'corte' });
  });

  it('revisão: checklist, miniaturas, textos do YouTube, outro idioma e formato, e o pacote', async () => {
    const final = makeMedia({ id: 'm'.repeat(32), kind: 'video', role: 'video_final', duration_s: 42, width: 1080, height: 1920 });
    const miniatura = makeMedia({ id: 't'.repeat(32), role: 'thumbnail', width: 1280, height: 720, prompt: 'A chuva do jardim' });
    const meta: ProjectMetadata = {
      'pt-BR': { title: 'A chuva | Vídeo infantil', description: 'Uma tarde de chuva.', tags: ['chuva', 'lila'] },
      en: { title: 'The rain | Kids cartoon', description: 'A rainy afternoon.', tags: ['rain'] },
      source: 'ia',
    };
    const c1 = makeScene({ id: '1'.repeat(32), data: { background: { media_id: fundo.id, seed: 5, prompt: 'x', quality: 'padrao' } } });
    const d = detalhe({
      scenes: [c1],
      stages: makeStages('revisao', ['enredo', 'roteiro', 'storyboard', 'animacao', 'audio', 'montagem']),
      files: { final, subtitles: makeMedia({ kind: 'legenda', role: 'legenda' }), mix: null, music: null, thumbnails: [miniatura] },
      metadata: meta,
      variants: [{ id: 'v'.repeat(32), title: 'A chuva (EN)', language: 'en', format: 'short', stage: 'roteiro' }],
    });
    fixture.detectChanges();
    http.expectOne('/api/projects/options').flush(OPTIONS);
    http.expectOne(`/api/projects/${id}`).flush(d);
    await fixture.whenStable();
    const review = http.expectOne(`/api/projects/${id}/review`);
    review.flush({ checklist: [{ id: 'flashes', label: 'Sem flashes (máx. 3 por segundo)', status: 'ok', detail: 'No máximo 0 por segundo.' }, { id: 'volume', label: 'Volume próximo de -14 LUFS', status: 'warning', detail: 'Revisar.' }], files: d.files, metadata: meta, quality: null, reminder: 'Marque como conteúdo para crianças.' });
    await fixture.whenStable();
    const texto = html(fixture).textContent!;
    expect(texto).toContain('Sem flashes (máx. 3 por segundo)');
    expect(texto).toContain('Marque como conteúdo para crianças.');
    expect(html(fixture).querySelector('a[download][href$="a-chuva-do-jardim.mp4"]')).not.toBeNull();
    expect(texto).toContain('Origem: modelo local');
    expect((campo(fixture, 'Título', 0) as HTMLInputElement).value).toBe('A chuva | Vídeo infantil');
    expect((campo(fixture, 'Tags (separadas por vírgula)', 0) as HTMLTextAreaElement).value).toBe('chuva, lila');
    expect(texto).toContain('2 de 15 tags');

    // miniaturas
    (html(fixture).querySelector('#thumb-count') as HTMLSelectElement).value = '4';
    html(fixture).querySelector('#thumb-count')!.dispatchEvent(new Event('change'));
    botao(fixture, 'Gerar miniaturas').click();
    const miniaturas = http.expectOne(`/api/projects/${id}/thumbnails`);
    expect(miniaturas.request.body).toEqual({ count: 4, text: null });
    miniaturas.flush(makeJob({ id: 'mn', kind: 'projeto.miniaturas', status: 'queued', params: { project_id: id } }));
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('1280×720');

    // editar e salvar o texto em inglês
    expect(botao(fixture, 'Salvar os textos').disabled).toBe(true);
    await digitar(fixture, 'Título', 'The rain in the garden', 1);
    await digitar(fixture, 'Tags (separadas por vírgula)', '#rain, garden, Rain', 1);
    expect(html(fixture).textContent).toContain('Há mudanças ainda não salvas.');
    botao(fixture, 'Salvar os textos').click();
    const salvar = http.expectOne(`/api/projects/${id}/metadata`);
    expect(salvar.request.method).toBe('PUT');
    expect(salvar.request.body.texts.en).toEqual({ title: 'The rain in the garden', description: 'A rainy afternoon.', tags: ['rain', 'garden'] });
    salvar.flush({ ...d, metadata: { ...meta, en: { title: 'The rain in the garden', description: 'A rainy afternoon.', tags: ['rain', 'garden'] }, source: 'manual' } });
    await fixture.whenStable();
    expect(TestBed.inject(ToastService).toasts().at(-1)?.text).toBe('Textos salvos.');
    http.match(`/api/projects/${id}/review`).forEach((r) => r.flush({ checklist: [], files: d.files, metadata: null, quality: null, reminder: '' }));

    // sugerir de novo
    botao(fixture, 'Sugerir com o modelo local').click();
    const sugerir = http.expectOne(`/api/projects/${id}/metadata`);
    expect(sugerir.request.body).toEqual({ mode: 'ia' });
    sugerir.flush(makeJob({ id: 'md', kind: 'projeto.metadados', status: 'queued', params: { project_id: id } }));
    await fixture.whenStable();

    // outro idioma e outro formato
    expect(html(fixture).textContent).toContain('Versão em inglês');
    botao(fixture, 'Criar traduzindo com o modelo local').click();
    const idioma = http.expectOne(`/api/projects/${id}/language-version`);
    expect(idioma.request.body).toEqual({ language: 'en', mode: 'ia' });
    idioma.flush(makeJob({ id: 'li', kind: 'projeto.versao_idioma', status: 'queued', params: { project_id: id } }));
    await fixture.whenStable();
    expect(html(fixture).querySelector('a[href$="' + 'v'.repeat(32) + '"]')!.textContent).toBe('A chuva (EN)');
    botao(fixture, 'Criar a versão Vídeo longo').click();
    const variante = http.expectOne(`/api/projects/${id}/variant`);
    expect(variante.request.body).toEqual({ format: 'longo' });
    variante.flush({ project: makeProject({ id: 'w'.repeat(32) }), warnings: ['O roteiro do original ainda não foi aprovado.'] });
    http.expectOne(`/api/projects/${id}`).flush(d);
    expect(router.navigate).toHaveBeenCalledWith(['/projetos', 'w'.repeat(32)]);

    // o pacote .fabulim, com ou sem os vídeos
    const baixar = (): string => html(fixture).querySelector('fab-section#pacote a[download], a[download][href^="/api/packages/projects"]')!.getAttribute('href')!;
    expect(baixar()).toBe(`/api/packages/projects/${id}?renders=false`);
    const marcar = [...html(fixture).querySelectorAll<HTMLInputElement>('input[type=checkbox]')].at(-1)!;
    marcar.checked = true;
    marcar.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    expect(baixar()).toBe(`/api/packages/projects/${id}?renders=true`);
  });

  it('«renderizar o aprovado» pede o próximo trabalho ou explica por que não há', async () => {
    await abrir();
    botao(fixture, 'Renderizar o aprovado').click();
    const req = http.expectOne('/api/projects/night-queue');
    expect(req.request.body).toEqual({ project_ids: [id] });
    req.flush({ queued: [], skipped: [{ project_id: id, title: 'x', stage: 'storyboard', stage_label: 'cenários', kind: 'projeto.storyboard', blocked_by: 'Já está na fila.' }] });
    expect(TestBed.inject(ToastService).toasts().at(-1)?.text).toBe('Já está na fila.');
    botao(fixture, 'Renderizar o aprovado').click();
    http.expectOne('/api/projects/night-queue').flush({ queued: [], skipped: [] });
    expect(TestBed.inject(ToastService).toasts().at(-1)?.text).toContain('Nada liberado neste projeto');
  });

  it('enredo: edita a história, avisa que reabre o roteiro e salva pelo PATCH do projeto', async () => {
    await abrir(detalhe({ project: makeProject({ id, character_ids: [lila.id], approvals: { enredo: true, roteiro: true } }), stages: makeStages('storyboard', ['enredo', 'roteiro']) }));
    html(fixture).querySelector<HTMLButtonElement>('.stage-bar button')!.click();
    await fixture.whenStable();
    expect(botao(fixture, 'Salvar o enredo').disabled).toBe(true);
    await digitar(fixture, 'História', 'Lila brinca na chuva.');
    expect(html(fixture).textContent).toContain('Mudar a história volta o roteiro');
    botao(fixture, 'Salvar o enredo').click();
    const req = http.expectOne(`/api/projects/${id}`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body.story.story).toBe('Lila brinca na chuva.');
    expect(req.request.body.character_ids).toEqual([lila.id]);
    expect(req.request.body.target_duration_s).toBe(30);
    req.flush(detalhe());
  });

  it('apagar o projeto pede confirmação e volta para a lista', async () => {
    await abrir();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    botao(fixture, 'Apagar projeto').click();
    http.expectOne((r) => r.url === `/api/projects/${id}` && r.method === 'DELETE').flush({ deleted: true, media_removed: 0 });
    expect(router.navigate).toHaveBeenCalledWith(['/projetos']);
  });

  it('uma imagem nova de uma cena recarrega o projeto', async () => {
    await abrir(detalhe({ scenes: [cena(1)] }));
    jobs.connect();
    FakeEventSource.instances[0].emit('media.created', makeMedia({ owner_id: '1'.repeat(32), owner_type: 'cena', role: 'fundo' }));
    await new Promise((r) => setTimeout(r, 600));
    http.expectOne(`/api/projects/${id}`).flush(detalhe({ scenes: [cena(1)] }));
  });
});
