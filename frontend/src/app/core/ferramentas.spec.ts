import { HttpErrorResponse } from '@angular/common/http';
import { HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { FakeEventSource, installFakeEventSource, makeJob, makeMedia, provideTestHttp, uninstallFakeEventSource } from '../../testing/fixtures';
import { ApiService, cleanParams } from './api.service';
import { errorMessage, existingId } from './http-error';
import { JobsService, MediaEvent } from './jobs.service';
import { durationLimit, matchCharacters, normalize, parseDurationSeconds, parseSeed } from './match';
import { ImageForm } from './models';
import { makeCharacter } from '../../testing/fixtures';
import { downloadUrl, ViewerService } from './viewer.service';

describe('http-error', () => {
  const erro = (status: number, body: unknown): HttpErrorResponse => new HttpErrorResponse({ status, error: body });

  it('usa a mensagem em português que o servidor mandou', () => {
    expect(errorMessage(erro(409, { detail: 'Aprove a etapa «Roteiro» antes.' }))).toBe('Aprove a etapa «Roteiro» antes.');
    expect(errorMessage(erro(503, { detail: 'A voz ainda não está instalada.' }))).toBe('A voz ainda não está instalada.');
  });

  it('na validação de campos mostra só a primeira mensagem, com o nome do campo', () => {
    const detail = [{ loc: ['body', 'count'], msg: 'Input should be less than or equal to 4' }];
    expect(errorMessage(erro(422, { detail }))).toBe('count: Input should be less than or equal to 4');
    expect(errorMessage(erro(422, { detail: [{ loc: ['body'], msg: 'Corpo inválido' }] }))).toBe('Corpo inválido');
  });

  it('explica o que aconteceu quando não há detalhe', () => {
    expect(errorMessage(erro(0, null))).toContain('Não consegui falar com o servidor');
    expect(errorMessage(erro(413, null))).toContain('grande demais');
    expect(errorMessage(erro(404, null))).toContain('Não encontrei');
    expect(errorMessage(erro(500, null))).toContain('Status > Logs');
    expect(errorMessage(new Error('falhou'))).toBe('falhou');
    expect(errorMessage('estranho', 'texto de reserva')).toBe('texto de reserva');
  });

  it('acha o id do personagem que já existe num conflito de nome', () => {
    expect(existingId(erro(409, { detail: 'nome em uso', existing_id: 'abc' }))).toBe('abc');
    expect(existingId(erro(409, { detail: 'outro' }))).toBeNull();
    expect(existingId(erro(422, { existing_id: 'abc' }))).toBeNull();
    expect(existingId(new Error('x'))).toBeNull();
  });
});

describe('match', () => {
  it('normaliza sem acento, sem caixa e sem espaços duplicados', () => {
    expect(normalize('  Áurea   MÃE ')).toBe('aurea mae');
  });

  it('casa os nomes do enredo com a biblioteca, preferindo o estilo do vídeo', () => {
    const lila2d = makeCharacter({ id: 'a'.repeat(32), name: 'Lila', style: '2D' });
    const lila3d = makeCharacter({ id: 'b'.repeat(32), name: 'Lila', style: '3D' });
    const bento = makeCharacter({ id: 'c'.repeat(32), name: 'Bento', style: '2D' });
    const { found, missing } = matchCharacters(['lila', 'BENTO', 'Bia', ' bia ', 'LILA', ''], [lila2d, lila3d, bento], '3D');
    expect(found.map((c) => c.id)).toEqual([lila3d.id, bento.id]);
    expect(missing).toEqual(['Bia']); // sem repetir, na ordem em que apareceu
    expect(matchCharacters(['Lila'], [lila2d, lila3d]).found[0].id).toBe(lila2d.id); // sem estilo: o primeiro
  });

  it('lê a semente: só inteiros de 0 a 2147483646', () => {
    expect(parseSeed('123')).toBe(123);
    expect(parseSeed(' 42 ')).toBe(42);
    expect(parseSeed('')).toBeNull();
    expect(parseSeed('abc')).toBeNull();
    expect(parseSeed('-5')).toBeNull();
    expect(parseSeed('1.5')).toBeNull();
    expect(parseSeed('2147483647')).toBeNull();
  });

  it('lê a duração alvo em segundos, dentro do limite do formato', () => {
    expect(parseDurationSeconds('60 s', 'short')).toBe(60);
    expect(parseDurationSeconds('45', 'short')).toBe(45);
    expect(parseDurationSeconds('3 min', 'longo')).toBe(180);
    expect(parseDurationSeconds('1:30', 'longo')).toBe(90);
    expect(parseDurationSeconds('2,5 minutos', 'longo')).toBe(150);
    expect(parseDurationSeconds('10 min', 'longo')).toBe(300); // passa do limite
    expect(parseDurationSeconds('3 min', 'short')).toBe(60);
    expect(parseDurationSeconds('5 s', 'short')).toBe(15); // mínimo
    expect(parseDurationSeconds('', 'short')).toBe(45);
    expect(parseDurationSeconds('curto', 'longo')).toBe(120);
    expect(durationLimit('short')).toBe(60);
    expect(durationLimit('longo')).toBe(300);
  });
});

describe('cleanParams', () => {
  it('tira o que não tem valor e mantém listas', () => {
    expect(cleanParams({ a: 'x', b: undefined, c: null, d: '', e: [], f: ['1', '2'], g: 0, h: false })).toEqual({ a: 'x', f: ['1', '2'], g: 0, h: false });
  });
});

describe('ViewerService', () => {
  it('abre e fecha a mídia em tela grande', () => {
    const viewer = TestBed.inject(ViewerService);
    const media = makeMedia();
    expect(viewer.current()).toBeNull();
    viewer.open(media, 'Lila');
    expect(viewer.current()).toEqual({ media, title: 'Lila' });
    viewer.close();
    expect(viewer.current()).toBeNull();
  });

  it('monta o endereço de download com um nome sugerido', () => {
    const media = makeMedia({ id: 'f'.repeat(32) });
    expect(downloadUrl(media)).toBe(`/api/media/${'f'.repeat(32)}?download=true`);
    expect(downloadUrl(media, 'lila final.png')).toBe(`/api/media/${'f'.repeat(32)}?download=true&name=lila%20final.png`);
  });
});

describe('JobsService: fim de tarefa e mídias ao vivo', () => {
  let jobs: JobsService;

  beforeEach(() => {
    installFakeEventSource();
    TestBed.configureTestingModule({ providers: provideTestHttp() });
    jobs = TestBed.inject(JobsService);
  });

  afterEach(() => uninstallFakeEventSource());

  it('anuncia cada tarefa que termina uma vez só', () => {
    const fim: string[] = [];
    jobs.finished$.subscribe((j) => fim.push(`${j.id}:${j.status}`));
    const rodando = makeJob({ id: 'r', status: 'running' });
    jobs.merge(makeJob({ id: 'q', status: 'queued' }));
    jobs.merge(rodando);
    expect(fim).toEqual([]);
    jobs.merge({ ...rodando, status: 'done', progress: 1 });
    jobs.merge({ ...rodando, status: 'done', progress: 1 }); // a mesma atualização de novo não repete o aviso
    jobs.merge(makeJob({ id: 'x', status: 'failed' })); // já chegou terminada: também vale
    jobs.merge({ ...makeJob({ id: 'q' }), status: 'canceled' });
    expect(fim).toEqual(['r:done', 'x:failed', 'q:canceled']);
  });

  it('encontra a tarefa pelo id', () => {
    jobs.merge(makeJob({ id: 'j1' }));
    expect(jobs.byId('j1')?.id).toBe('j1');
    expect(jobs.byId('nada')).toBeUndefined();
    expect(jobs.byId(null)).toBeUndefined();
  });

  it('repassa as mídias criadas e apagadas que chegam pelo fluxo ao vivo', () => {
    const eventos: MediaEvent[] = [];
    jobs.media$.subscribe((e) => eventos.push(e));
    jobs.connect();
    const es = FakeEventSource.instances[0];
    const media = makeMedia({ id: 'm'.repeat(32) });
    es.emit('media.created', media);
    es.emit('media.deleted', { id: 'm'.repeat(32) });
    expect(eventos).toEqual([
      { type: 'created', media },
      { type: 'deleted', id: 'm'.repeat(32) },
    ]);
  });
});

describe('ApiService: ferramentas de criação', () => {
  let api: ApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: provideTestHttp() });
    api = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('a biblioteca de mídias filtra por tipo, papéis, dono e busca sem mandar o que está vazio', () => {
    api.media({ kind: 'imagem', role: ['cenario', 'livre'], ownerType: 'nenhum', q: 'jardim', limit: 24, offset: 24 }).subscribe();
    const req = http.expectOne((r) => r.url === '/api/media');
    expect(req.request.params.get('kind')).toBe('imagem');
    expect(req.request.params.getAll('role')).toEqual(['cenario', 'livre']);
    expect(req.request.params.get('owner_type')).toBe('nenhum');
    expect(req.request.params.get('q')).toBe('jardim');
    expect(req.request.params.get('limit')).toBe('24');
    expect(req.request.params.has('owner_id')).toBe(false);
    req.flush({ items: [], total: 0 });
    api.media().subscribe();
    expect(http.expectOne((r) => r.url === '/api/media').request.params.keys()).toEqual([]);
  });

  it('envia imagem e vídeo em corpo cru, com o nome e o direito de uso na URL', () => {
    const imagem = new File(['x'], 'lila.png', { type: 'image/png' });
    api.uploadImage(imagem).subscribe();
    const a = http.expectOne((r) => r.url === '/api/media/upload');
    expect(a.request.params.get('name')).toBe('lila.png');
    expect(a.request.params.get('role')).toBe('upload');
    expect(a.request.body).toBe(imagem);
    a.flush(makeMedia());

    api.uploadCharacter(imagem, 'Lila', '3D', true).subscribe();
    const b = http.expectOne((r) => r.url === '/api/characters/upload');
    expect(b.request.params.get('style')).toBe('3D');
    expect(b.request.params.get('rights')).toBe('true');
    expect(b.request.params.get('file_name')).toBe('lila.png');
    b.flush({ character: makeCharacter(), job: null });

    const video = new File(['v'], 'clipe.mp4', { type: 'video/mp4' });
    api.uploadClip(video, true).subscribe();
    const c = http.expectOne((r) => r.url === '/api/clips/upload');
    expect(c.request.params.get('rights')).toBe('true');
    expect(c.request.reportProgress).toBe(true);
    c.flush(makeMedia({ kind: 'video' }));
  });

  it('lê o prompt colado, confere textos e mexe no histórico', () => {
    api.parsePrompt('### ENREDO', 'enredo').subscribe();
    expect(http.expectOne('/api/prompts/parse').request.body).toEqual({ text: '### ENREDO', type: 'enredo' });
    api.parsePrompt('livre').subscribe();
    expect(http.match('/api/prompts/parse')[0].request.body).toEqual({ text: 'livre' });
    api.checkTexts(['a']).subscribe();
    http.expectOne('/api/prompts/check').flush({ ok: true, blocked: null });
    api.promptHistory('personagem', 10).subscribe();
    const h = http.expectOne((r) => r.url === '/api/prompts/history');
    expect(h.request.params.get('type')).toBe('personagem');
    h.flush([]);
    api.deleteFromHistory(3).subscribe();
    http.expectOne('/api/prompts/history/3').flush({ deleted: true });
    api.clearHistory().subscribe();
    http.expectOne((r) => r.url === '/api/prompts/history' && r.method === 'DELETE').flush({ removed: 0 });
  });

  it('imagem avulsa: estimativa, prompt técnico e geração', () => {
    api.imageEstimate('16:9', 'padrao', 2, 1).subscribe();
    const e = http.expectOne((r) => r.url === '/api/images/estimate');
    expect(e.request.params.get('format')).toBe('16:9');
    expect(e.request.params.get('references')).toBe('1');
    e.flush({ width: 1024, height: 576, total_seconds: 100, total_label: '1 min 40 s' });
    const form: ImageForm = { kind: 'livre', style: '2D', format: '16:9', characters: [], description: 'x', notes: '' };
    api.technicalPrompt(form, ['a'], 'b'.repeat(32)).subscribe();
    expect(http.expectOne('/api/images/technical-prompt').request.body).toEqual({ form, character_ids: ['a'], based_on: 'b'.repeat(32) });
    api.technicalPrompt(form, [], null).subscribe();
    expect(http.match('/api/images/technical-prompt')[0].request.body).toEqual({ form, character_ids: [] });
    api.generateImage({ form, quality: 'rascunho', count: 1, character_ids: [] }).subscribe();
    http.expectOne('/api/images').flush(makeJob());
  });

  it('personagens: criar, editar, variações, escolher, folha, voz, conversão e direção do recorte', () => {
    const c = 'c'.repeat(32);
    const m = 'm'.repeat(32);
    api.characters('lila', '2D').subscribe();
    const lista = http.expectOne((r) => r.url === '/api/characters');
    expect(lista.request.params.get('q')).toBe('lila');
    lista.flush({ items: [], total: 0 });
    api.character(c).subscribe();
    http.expectOne(`/api/characters/${c}`).flush({});
    api.resolveNames(['Lila'], '2D').subscribe();
    expect(http.expectOne('/api/characters/resolve').request.body).toEqual({ names: ['Lila'], style: '2D' });
    api.createCharacter(makeCharacter().form, 'prompt').subscribe();
    expect(http.expectOne('/api/characters').request.body.original_prompt).toBe('prompt');
    api.updateCharacter(c, { technical_prompt: 'novo' }).subscribe();
    const patch = http.expectOne(`/api/characters/${c}`);
    expect(patch.request.method).toBe('PATCH');
    patch.flush({});
    api.generateVariations(c, { count: 2, quality: 'rascunho', seed: 5, technical_prompt: null }).subscribe();
    expect(http.expectOne(`/api/characters/${c}/variations`).request.body.count).toBe(2);
    api.chooseVariation(c, m).subscribe();
    expect(http.expectOne(`/api/characters/${c}/choose`).request.body).toEqual({ media_id: m });
    api.generateSheet(c, ['frente', 'lado'], 'rascunho').subscribe();
    expect(http.expectOne(`/api/characters/${c}/sheet`).request.body).toEqual({ slots: ['frente', 'lado'], quality: 'rascunho' });
    api.generateSheet(c, ['frente'], 'padrao', 9).subscribe();
    expect(http.match(`/api/characters/${c}/sheet`)[0].request.body.seed).toBe(9);
    api.setVoice(c, { id: 'pm_alex', speed: 0.9, pitch: 1.1, language: 'pt-BR' }).subscribe();
    const voz = http.expectOne(`/api/characters/${c}/voice`);
    expect(voz.request.method).toBe('PUT');
    expect(voz.request.body).toEqual({ id: 'pm_alex', speed: 0.9, pitch: 1.1 });
    api.testVoice(c, 'Oi!').subscribe();
    expect(http.expectOne(`/api/characters/${c}/voice-test`).request.body).toEqual({ text: 'Oi!' });
    api.convertCharacter(c, 2, 'rascunho').subscribe();
    expect(http.expectOne(`/api/characters/${c}/convert`).request.body).toEqual({ count: 2, quality: 'rascunho' });
    api.setFacing(c, m, 'left').subscribe();
    const facing = http.expectOne(`/api/characters/${c}/cutouts/${m}/facing`);
    expect(facing.request.method).toBe('PUT');
    expect(facing.request.body).toEqual({ facing: 'left' });
    api.deleteCharacter(c).subscribe();
    http.expectOne(`/api/characters/${c}`).flush({ deleted: true, media_removed: 0 });
    api.characterEstimate('sheet', 3, 'rascunho').subscribe();
    expect(http.expectOne((r) => r.url === '/api/characters/estimate').request.params.get('count')).toBe('3');
    api.characterVoices().subscribe();
    http.expectOne('/api/characters/voices').flush({ voices: {} });
    http.match(() => true).forEach(() => undefined);
  });

  it('clipes: rápido, unir, outro formato, continuar e apagar', () => {
    api.clips({ role: ['clipe_unido'], q: 'x', limit: 5 }).subscribe();
    const lista = http.expectOne((r) => r.url === '/api/clips');
    expect(lista.request.params.getAll('role')).toEqual(['clipe_unido']);
    lista.flush({ items: [], total: 0 });
    api.quickClip({ character_id: 'c', prompt: 'pula', duration_s: 5, format: '9:16', quality: 'rascunho' }).subscribe();
    expect(http.expectOne('/api/clips/quick').request.body.prompt).toBe('pula');
    api.joinClips(['a', 'b'], 'fade', 'auto').subscribe();
    expect(http.expectOne('/api/clips/join').request.body).toEqual({ clip_ids: ['a', 'b'], transition: 'fade', size: 'auto' });
    api.reframeClip('a', '9:16', 'crop').subscribe();
    expect(http.expectOne('/api/clips/a/reframe').request.body).toEqual({ preset: '9:16', mode: 'crop' });
    api.continueClip('a', { prompt: 'p', character_ids: [], title: '', last_scene: '' }).subscribe();
    http.expectOne('/api/clips/a/continue');
    api.deleteClip('a').subscribe();
    http.expectOne((r) => r.url === '/api/clips/a' && r.method === 'DELETE');
  });

  it('projetos: criar, etapas, cenas, versões e as tarefas de cada etapa', () => {
    const p = 'p'.repeat(32);
    const s = 's'.repeat(32);
    api.projectOptions().subscribe();
    http.expectOne('/api/projects/options');
    api.projects().subscribe();
    http.expectOne('/api/projects');
    api.project(p).subscribe();
    http.expectOne(`/api/projects/${p}`);
    api.updateProject(p, { title: 'Novo' }).subscribe();
    expect(http.expectOne(`/api/projects/${p}`).request.method).toBe('PATCH');
    api.approveStage(p, 'roteiro', true).subscribe();
    expect(http.expectOne(`/api/projects/${p}/stages/roteiro/approve`).request.body).toEqual({ approve_all: true });
    api.reopenStage(p, 'roteiro').subscribe();
    http.expectOne(`/api/projects/${p}/stages/roteiro/reopen`);
    api.generateScript(p, 'simples').subscribe();
    expect(http.expectOne(`/api/projects/${p}/script`).request.body).toEqual({ mode: 'simples' });
    api.generateStoryboard(p, { mode: 'faltantes' }).subscribe();
    http.expectOne(`/api/projects/${p}/storyboard`);
    api.animateScenes(p, { draft: true }).subscribe();
    expect(http.expectOne(`/api/projects/${p}/animate`).request.body).toEqual({ draft: true });
    api.generateAudio(p).subscribe();
    expect(http.expectOne(`/api/projects/${p}/audio`).request.body).toEqual({});
    api.generateAudio(p, 'fade').subscribe();
    expect(http.expectOne(`/api/projects/${p}/audio`).request.body).toEqual({ transition: 'fade' });
    api.assemble(p, 'suave').subscribe();
    expect(http.expectOne(`/api/projects/${p}/assemble`).request.body).toEqual({ transition: 'suave' });
    api.review(p).subscribe();
    http.expectOne(`/api/projects/${p}/review`);
    api.createScene(p, { title: 'x' }, 2).subscribe();
    expect(http.expectOne(`/api/projects/${p}/scenes`).request.body).toEqual({ data: { title: 'x' }, position: 2 });
    api.editScene(p, s, { title: 'y' }).subscribe();
    expect(http.expectOne(`/api/projects/${p}/scenes/${s}`).request.body).toEqual({ changes: { title: 'y' } });
    api.deleteScene(p, s).subscribe();
    http.expectOne((r) => r.url === `/api/projects/${p}/scenes/${s}` && r.method === 'DELETE');
    api.reorderScenes(p, [s]).subscribe();
    expect(http.expectOne(`/api/projects/${p}/scenes/reorder`).request.body).toEqual({ ids: [s] });
    api.approveScene(p, s, 'storyboard', false).subscribe();
    expect(http.expectOne(`/api/projects/${p}/scenes/${s}/approve`).request.body).toEqual({ stage: 'storyboard', approved: false });
    api.sceneVersions(p, s).subscribe();
    http.expectOne(`/api/projects/${p}/scenes/${s}/versions`);
    api.restoreScene(p, s, 2).subscribe();
    expect(http.expectOne(`/api/projects/${p}/scenes/${s}/restore`).request.body).toEqual({ version: 2 });
    api.chooseBackground(p, s, 'm').subscribe();
    http.expectOne(`/api/projects/${p}/scenes/${s}/choose-background`);
    api.recomposeScene(p, s).subscribe();
    http.expectOne(`/api/projects/${p}/scenes/${s}/recompose`);
    api.setLayout(p, s, [{ personagem_id: 'c', x: 0.5 }]).subscribe();
    expect(http.expectOne(`/api/projects/${p}/scenes/${s}/layout`).request.method).toBe('PUT');
    api.deleteProject(p).subscribe();
    http.expectOne((r) => r.url === `/api/projects/${p}` && r.method === 'DELETE');
    api.createProject({ form: {} as never, original_prompt: '', character_ids: [] }).subscribe();
    http.expectOne((r) => r.url === '/api/projects' && r.method === 'POST');
  });

  it('entrega: miniaturas, textos do YouTube, outro idioma, formato, fila noturna e pacotes', () => {
    const p = 'p'.repeat(32);
    api.generateThumbnails(p, { count: 3, text: null }).subscribe();
    expect(http.expectOne(`/api/projects/${p}/thumbnails`).request.body).toEqual({ count: 3, text: null });
    api.deleteThumbnail(p, 'm').subscribe();
    http.expectOne((r) => r.url === `/api/projects/${p}/thumbnails/m` && r.method === 'DELETE');
    api.generateMetadata(p, 'ia').subscribe();
    expect(http.expectOne(`/api/projects/${p}/metadata`).request.body).toEqual({ mode: 'ia' });
    api.saveMetadata(p, { en: { title: 't', description: 'd', tags: ['a'] } }).subscribe();
    const salvar = http.expectOne(`/api/projects/${p}/metadata`);
    expect(salvar.request.method).toBe('PUT');
    expect(salvar.request.body).toEqual({ texts: { en: { title: 't', description: 'd', tags: ['a'] } } });
    api.languageVersion(p, 'en', 'ia').subscribe();
    expect(http.expectOne(`/api/projects/${p}/language-version`).request.body).toEqual({ language: 'en', mode: 'ia' });
    api.languageVersion(p, null, 'simples').subscribe();
    expect(http.match(`/api/projects/${p}/language-version`)[0].request.body).toEqual({ mode: 'simples' });
    api.createVariant(p, 'longo').subscribe();
    expect(http.expectOne(`/api/projects/${p}/variant`).request.body).toEqual({ format: 'longo' });
    api.nightPlan().subscribe();
    http.expectOne('/api/projects/night-plan');
    api.nightQueue().subscribe();
    expect(http.expectOne('/api/projects/night-queue').request.body).toEqual({});
    api.nightQueue([p]).subscribe();
    expect(http.expectOne('/api/projects/night-queue').request.body).toEqual({ project_ids: [p] });
    expect(api.projectPackageUrl(p, true)).toBe(`/api/packages/projects/${p}?renders=true`);
    expect(api.charactersPackageUrl()).toBe('/api/packages/characters');
    expect(api.charactersPackageUrl(['a', 'b'])).toBe('/api/packages/characters?id=a&id=b');
    const pacote = new File(['zip'], 'p.fabulim');
    api.importPackage(pacote).subscribe();
    const importar = http.expectOne('/api/packages/import');
    expect(importar.request.body).toBe(pacote);
    expect(importar.request.reportProgress).toBe(true);
  });
});
