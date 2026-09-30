import { HttpEventType } from '@angular/common/http';
import { HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { makeCharacter, makeJob, makeMedia, provideTestHttp } from '../../testing/fixtures';
import { JobsService } from '../core/jobs.service';
import { ParsedPrompt, ParseResponse } from '../core/models';
import { ViewerService } from '../core/viewer.service';
import { CharacterPickerComponent } from './character-picker';
import { FieldComponent } from './field';
import { JobProgressComponent } from './job-progress';
import { MediaTileComponent } from './media-tile';
import { PackageImportComponent } from './package-import';
import { PromptBoxComponent, ReadPrompt } from './prompt-box';
import { PROMPT_EXAMPLES } from './prompt-examples';
import { ViewerHostComponent } from './viewer-host';

const html = (f: ComponentFixture<unknown>): HTMLElement => f.nativeElement as HTMLElement;

describe('FieldComponent', () => {
  let fixture: ComponentFixture<FieldComponent>;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({ providers: provideTestHttp() });
    fixture = TestBed.createComponent(FieldComponent);
    fixture.componentRef.setInput('label', 'Nome');
  });

  it('liga o rótulo ao campo, marca o obrigatório e liga a dica por aria-describedby', async () => {
    fixture.componentRef.setInput('required', true);
    fixture.componentRef.setInput('hint', 'Como aparece na lista');
    await fixture.whenStable();
    const el = html(fixture);
    const label = el.querySelector('label')!;
    const input = el.querySelector('input')!;
    expect(label.getAttribute('for')).toBe(input.id);
    expect(label.textContent).toContain('*');
    expect(input.getAttribute('aria-required')).toBe('true');
    const dica = el.querySelector('.field-hint')!;
    expect(input.getAttribute('aria-describedby')).toBe(dica.id);
    expect(dica.textContent).toBe('Como aparece na lista');
  });

  it('digitar atualiza o valor; várias linhas usam textarea; número aceita limites', async () => {
    const valores: string[] = [];
    fixture.componentInstance.value.subscribe((v) => valores.push(v));
    await fixture.whenStable();
    const input = html(fixture).querySelector('input')!;
    input.value = 'Lila';
    input.dispatchEvent(new Event('input'));
    expect(valores).toEqual(['Lila']);

    fixture.componentRef.setInput('multiline', true);
    fixture.componentRef.setInput('rows', 5);
    fixture.componentRef.setInput('maxlength', 30);
    await fixture.whenStable();
    const area = html(fixture).querySelector('textarea')!;
    expect(area.rows).toBe(5);
    expect(area.getAttribute('maxlength')).toBe('30');
    expect(html(fixture).querySelector('input')).toBeNull();

    fixture.componentRef.setInput('multiline', false);
    fixture.componentRef.setInput('type', 'number');
    fixture.componentRef.setInput('min', 1);
    fixture.componentRef.setInput('max', 4);
    await fixture.whenStable();
    const numero = html(fixture).querySelector('input')!;
    expect(numero.type).toBe('number');
    expect(numero.getAttribute('min')).toBe('1');
    expect(numero.getAttribute('max')).toBe('4');
  });
});

describe('MediaTileComponent', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: provideTestHttp() }));

  const criar = async (media = makeMedia(), inputs: Record<string, unknown> = {}): Promise<ComponentFixture<MediaTileComponent>> => {
    const fixture = TestBed.createComponent(MediaTileComponent);
    fixture.componentRef.setInput('media', media);
    for (const [k, v] of Object.entries(inputs)) fixture.componentRef.setInput(k, v);
    await fixture.whenStable();
    return fixture;
  };

  it('mostra a miniatura com a proporção da imagem e abre em tela grande ao clicar', async () => {
    const media = makeMedia({ width: 1280, height: 720, prompt: 'um jardim' });
    const fixture = await criar(media, { caption: 'Cenário' });
    const img = html(fixture).querySelector('img')!;
    expect(img.getAttribute('src')).toBe(media.thumb_url);
    expect(img.getAttribute('alt')).toBe('um jardim');
    expect(img.style.aspectRatio).toBe('1280 / 720');
    html(fixture).querySelector<HTMLButtonElement>('button')!.click();
    expect(TestBed.inject(ViewerService).current()?.media.id).toBe(media.id);
    expect(html(fixture).querySelector('strong')?.textContent).toBe('Cenário');
  });

  it('recorte aparece sobre xadrez; sem miniatura mostra um ícone; vídeo mostra a duração', async () => {
    const recorte = await criar(makeMedia({ role: 'recorte' }));
    expect(html(recorte).querySelector('img')!.className).toContain('checker');
    const forcado = await criar(makeMedia({ role: 'variacao' }), { transparent: true });
    expect(html(forcado).querySelector('img')!.className).toContain('checker');
    const semThumb = await criar(makeMedia({ thumb_url: null }));
    expect(html(semThumb).querySelector('img')).toBeNull();
    expect(html(semThumb).querySelector('svg')).not.toBeNull();
    const video = await criar(makeMedia({ kind: 'video', duration_s: 75 }));
    expect(html(video).textContent).toContain('1:15');
  });

  it('áudio mostra o tocador e não o botão de abrir', async () => {
    const fixture = await criar(makeMedia({ kind: 'audio', thumb_url: null, role: 'voz_teste' }), { caption: 'Voz de teste' });
    expect(html(fixture).querySelector('audio')).not.toBeNull();
    expect(html(fixture).querySelector('button')).toBeNull();
  });

  it('a mídia escolhida ganha contorno e o detalhe aparece embaixo', async () => {
    const fixture = await criar(makeMedia(), { selected: true, detail: 'Semente 7' });
    expect(html(fixture).querySelector('figure')!.className).toContain('shadow-hard');
    expect(html(fixture).textContent).toContain('Semente 7');
  });
});

describe('CharacterPickerComponent', () => {
  let fixture: ComponentFixture<CharacterPickerComponent>;
  const lila = makeCharacter({ id: 'a'.repeat(32), name: 'Lila' });
  const bento = makeCharacter({ id: 'b'.repeat(32), name: 'Bento', style: '3D', has_cutout: false });
  const sem = makeCharacter({ id: 'c'.repeat(32), name: 'Sem imagem', main_image_id: null, main_image_url: null, has_cutout: false });

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: provideTestHttp() });
    fixture = TestBed.createComponent(CharacterPickerComponent);
    fixture.componentRef.setInput('label', 'Personagens');
    fixture.componentRef.setInput('characters', [lila, bento, sem]);
  });

  const botoes = (): HTMLButtonElement[] => [...html(fixture).querySelectorAll<HTMLButtonElement>('button')];

  it('só oferece quem já tem imagem e marca a escolha com aria-pressed', async () => {
    await fixture.whenStable();
    expect(botoes().map((b) => b.textContent!.replace(/\s+/g, ' ').trim())).toEqual(['Lila · 2D', 'Bento · 3D']);
    botoes()[0].click();
    await fixture.whenStable();
    expect(fixture.componentInstance.selected()).toEqual([lila.id]);
    expect(botoes()[0].getAttribute('aria-pressed')).toBe('true');
    botoes()[0].click();
    expect(fixture.componentInstance.selected()).toEqual([]);
  });

  it('respeita o limite e, para vídeos, só mostra quem tem o PNG transparente', async () => {
    fixture.componentRef.setInput('max', 1);
    await fixture.whenStable();
    botoes()[0].click();
    await fixture.whenStable();
    expect(botoes()[1].disabled).toBe(true); // o limite foi atingido
    fixture.componentRef.setInput('requireCutout', true);
    await fixture.whenStable();
    expect(botoes().map((b) => b.textContent!.trim().split(' ')[0])).toEqual(['Lila']);
  });

  it('sem personagens prontos oferece criar um', async () => {
    fixture.componentRef.setInput('characters', []);
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Ainda não há personagens prontos');
    expect(html(fixture).querySelector('a')!.getAttribute('href')).toBe('/personagens');
  });
});

describe('JobProgressComponent', () => {
  let fixture: ComponentFixture<JobProgressComponent>;
  let jobs: JobsService;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: provideTestHttp() });
    jobs = TestBed.inject(JobsService);
    fixture = TestBed.createComponent(JobProgressComponent);
  });

  it('não mostra nada sem tarefa', async () => {
    fixture.componentRef.setInput('jobId', 'nao-existe');
    await fixture.whenStable();
    expect(html(fixture).textContent!.trim()).toBe('');
  });

  it('mostra o andamento ao vivo, com barra, mensagem, tempo restante e como cancelar', async () => {
    jobs.merge(makeJob({ id: 'j1', title: 'Variações de Lila', status: 'running', progress: 0.42, message: 'Desenhando 1 de 2', eta_seconds: 65 }));
    fixture.componentRef.setInput('jobId', 'j1');
    await fixture.whenStable();
    const el = html(fixture);
    expect(el.textContent).toContain('Variações de Lila');
    expect(el.textContent).toContain('42%');
    expect(el.textContent).toContain('Desenhando 1 de 2');
    expect(el.textContent).toContain('faltam ~1 min 05 s');
    expect(el.querySelector('[role="progressbar"]')!.getAttribute('aria-valuenow')).toBe('42');
    jobs.merge(makeJob({ id: 'j1', title: 'Variações de Lila', status: 'running', progress: 0.9 }));
    await fixture.whenStable();
    expect(el.textContent).toContain('90%');
    el.querySelector<HTMLButtonElement>('button')!.click();
    const http = TestBed.inject(HttpTestingController);
    expect(http.expectOne('/api/jobs/j1/cancel').request.method).toBe('POST');
  });

  it('avisa quando está na fila, quando falhou e quando foi cancelada', async () => {
    jobs.merge(makeJob({ id: 'q', status: 'queued' }));
    fixture.componentRef.setInput('jobId', 'q');
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Esperando a vez na fila');
    jobs.merge(makeJob({ id: 'q', status: 'failed', error: 'A voz ainda não está instalada.' }));
    await fixture.whenStable();
    expect(html(fixture).querySelector('[role="alert"]')!.textContent).toContain('A voz ainda não está instalada.');
    expect(html(fixture).querySelector('button')).toBeNull();
    jobs.merge(makeJob({ id: 'q', status: 'canceled' }));
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Tarefa cancelada');
  });
});

describe('PromptBoxComponent', () => {
  let fixture: ComponentFixture<PromptBoxComponent>;
  let http: HttpTestingController;
  let jobs: JobsService;
  let lidos: ReadPrompt[];

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({ providers: provideTestHttp() });
    http = TestBed.inject(HttpTestingController);
    jobs = TestBed.inject(JobsService);
    fixture = TestBed.createComponent(PromptBoxComponent);
    fixture.componentRef.setInput('type', 'personagem');
    lidos = [];
    fixture.componentInstance.parsed.subscribe((r) => lidos.push(r));
    fixture.detectChanges();
  });

  const el = (): HTMLElement => html(fixture);
  const botao = (texto: string): HTMLButtonElement => [...el().querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent!.includes(texto))!;
  const escrever = async (texto: string): Promise<void> => {
    const area = el().querySelector('textarea')!;
    area.value = texto;
    area.dispatchEvent(new Event('input'));
    await fixture.whenStable();
  };
  const lido = (form: Record<string, unknown>, extras: Partial<ParsedPrompt<Record<string, unknown>>> = {}): ParseResponse => ({
    status: 'done',
    detected_type: 'personagem',
    result: { type: 'personagem', form, source: 'estruturado', missing: [], warnings: [], ...extras },
    blocked: null,
  });

  it('o botão de ler só vale com texto e os exemplos preenchem a caixa', async () => {
    await fixture.whenStable();
    expect(botao('Ler o prompt').disabled).toBe(true);
    botao('Exemplo estruturado').click();
    await fixture.whenStable();
    expect(el().querySelector('textarea')!.value).toBe(PROMPT_EXAMPLES.personagem.structured);
    botao('Exemplo em texto livre').click();
    await fixture.whenStable();
    expect(el().querySelector('textarea')!.value).toBe(PROMPT_EXAMPLES.personagem.free);
    expect(botao('Ler o prompt').disabled).toBe(false);
    botao('Limpar').click();
    await fixture.whenStable();
    expect(el().querySelector('textarea')!.value).toBe('');
  });

  it('o formato estruturado volta na hora e entrega o formulário junto com o texto colado', async () => {
    await escrever('### PERSONAGEM\nNome: Lila');
    botao('Ler o prompt').click();
    const req = http.expectOne('/api/prompts/parse');
    expect(req.request.body).toEqual({ text: '### PERSONAGEM\nNome: Lila', type: 'personagem' });
    req.flush(lido({ name: 'Lila' }, { warnings: ['Faltou a paleta'] }));
    await fixture.whenStable();
    expect(lidos).toHaveLength(1);
    expect(lidos[0].text).toBe('### PERSONAGEM\nNome: Lila');
    expect(lidos[0].result.form).toEqual({ name: 'Lila' });
    expect(el().textContent).toContain('Faltou a paleta');
  });

  it('mostra o motivo quando o filtro de conteúdo bloqueia, ou quando o tipo do prompt é outro', async () => {
    await escrever('Peppa Pig');
    botao('Ler o prompt').click();
    http.expectOne('/api/prompts/parse').flush({ status: 'blocked', detected_type: 'personagem', result: null, blocked: { reason: 'Marca de terceiros não é permitida.' } });
    await fixture.whenStable();
    expect(el().querySelector('[role="alert"]')!.textContent).toContain('Marca de terceiros não é permitida.');
    expect(lidos).toEqual([]);

    await escrever('### ENREDO\nHistória: ...');
    botao('Ler o prompt').click();
    http.expectOne('/api/prompts/parse').flush({ ...lido({}), detected_type: 'enredo' });
    await fixture.whenStable();
    expect(el().querySelector('[role="alert"]')!.textContent).toContain('é de enredo');
    expect(el().querySelector('[role="alert"]')!.textContent).toContain('aqui você cria personagem');
  });

  it('texto livre vai para a fila e o formulário chega quando a tarefa termina', async () => {
    await escrever('Uma raposinha ruiva chamada Bia');
    botao('Ler o prompt').click();
    const job = makeJob({ id: 'l1', kind: 'prompt.interpretar', status: 'queued', title: 'Ler o prompt com o modelo local' });
    http.expectOne('/api/prompts/parse').flush({ status: 'queued', detected_type: 'personagem', job });
    await fixture.whenStable();
    expect(el().textContent).toContain('Ler o prompt com o modelo local');
    expect(botao('Ler o prompt').disabled).toBe(true); // continua ocupado até terminar
    jobs.merge({ ...job, status: 'done', progress: 1, result: lido({ name: 'Bia' }) as unknown as Record<string, unknown> });
    await fixture.whenStable();
    expect(lidos[0].result.form).toEqual({ name: 'Bia' });
    expect(lidos[0].text).toBe('Uma raposinha ruiva chamada Bia');
    expect(botao('Ler o prompt').disabled).toBe(false);
  });

  it('se a tarefa falha, mostra o erro em vez de travar', async () => {
    await escrever('texto livre');
    botao('Ler o prompt').click();
    const job = makeJob({ id: 'l2', status: 'queued' });
    http.expectOne('/api/prompts/parse').flush({ status: 'queued', detected_type: 'personagem', job });
    jobs.merge({ ...job, status: 'failed', error: 'O modelo local não respondeu.' });
    await fixture.whenStable();
    expect(el().querySelector('[role="alert"]')!.textContent).toContain('O modelo local não respondeu.');
    expect(lidos).toEqual([]);
  });

  it('erro do servidor aparece na tela', async () => {
    await escrever('texto');
    botao('Ler o prompt').click();
    http.expectOne('/api/prompts/parse').flush({ detail: 'Cole ou escreva o prompt primeiro.' }, { status: 422, statusText: 'Unprocessable' });
    await fixture.whenStable();
    expect(el().querySelector('[role="alert"]')!.textContent).toContain('Cole ou escreva o prompt primeiro.');
  });

  it('o histórico lista os últimos prompts, reaproveita um e apaga outro', async () => {
    await fixture.whenStable();
    botao('Histórico').click();
    const req = http.expectOne((r) => r.url === '/api/prompts/history');
    expect(req.request.params.get('type')).toBe('personagem');
    req.flush([
      { id: 1, type: 'personagem', text: '### PERSONAGEM\nNome: Lila', created_at: '2026-09-30T10:00:00Z' },
      { id: 2, type: 'personagem', text: 'x'.repeat(300), created_at: '2026-09-30T10:01:00Z' },
    ]);
    await fixture.whenStable();
    const itens = [...el().querySelectorAll('li')];
    expect(itens).toHaveLength(2);
    expect(itens[1].textContent).toContain('…'); // texto longo é cortado na lista
    itens[1].querySelector<HTMLButtonElement>('button[aria-label]')!.click();
    http.expectOne('/api/prompts/history/2').flush({ deleted: true });
    await fixture.whenStable();
    expect(el().querySelectorAll('li')).toHaveLength(1);
    el().querySelector<HTMLButtonElement>('li button')!.click();
    await fixture.whenStable();
    expect(el().querySelector('textarea')!.value).toContain('Nome: Lila');
    expect(el().querySelector('li')).toBeNull(); // a lista fecha ao escolher
  });
});

describe('PackageImportComponent', () => {
  let fixture: ComponentFixture<PackageImportComponent>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: provideTestHttp() });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(PackageImportComponent);
  });

  const escolher = async (nome = 'p.fabulim'): Promise<File> => {
    const file = new File(['zip'], nome);
    const input = html(fixture).querySelector<HTMLInputElement>('input[type=file]')!;
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    input.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    return file;
  };
  const enviar = (): HTMLButtonElement => html(fixture).querySelector<HTMLButtonElement>('button.btn-primary')!;

  it('importa um projeto: envia o arquivo, mostra o andamento e o resumo com o que mudou', async () => {
    await fixture.whenStable();
    expect(enviar().disabled).toBe(true);
    const file = await escolher();
    const importados: string[] = [];
    fixture.componentInstance.imported.subscribe((r) => importados.push(r.kind));
    enviar().click();
    const req = http.expectOne('/api/packages/import');
    expect(req.request.body).toBe(file);
    req.event({ type: HttpEventType.UploadProgress, loaded: 50, total: 100 });
    await fixture.whenStable();
    expect(html(fixture).querySelector('[role="progressbar"]')!.getAttribute('aria-valuenow')).toBe('50');
    req.flush({
      kind: 'project',
      project_id: 'p1',
      characters: [{ id: 'c1', name: 'Lila (importado)', renamed_from: 'Lila' }],
      scenes: 2,
      media: 7,
      warnings: ['«Lila» já existia na biblioteca.'],
      project: { id: 'p1', title: 'A chuva do jardim' },
      character_list: [],
    });
    await fixture.whenStable();
    expect(importados).toEqual(['project']);
    const texto = html(fixture).textContent!;
    expect(texto).toContain('Projeto «A chuva do jardim» importado: 2 cenas e 7 arquivos.');
    expect(texto).toContain('«Lila» já existia na biblioteca.');
    expect(html(fixture).querySelector('a')!.getAttribute('href')).toBe('/projetos/p1');
  });

  it('importa personagens e mostra o erro do servidor quando o pacote é recusado', async () => {
    await escolher();
    enviar().click();
    http.expectOne('/api/packages/import').flush({ detail: 'O arquivo não é um pacote .fabulim (não é um zip válido).' }, { status: 422, statusText: 'Unprocessable' });
    await fixture.whenStable();
    expect(html(fixture).querySelector('[role="alert"]')!.textContent).toContain('não é um zip válido');
    expect(enviar().disabled).toBe(false); // dá para tentar outro arquivo

    await escolher('bib.fabulim');
    enviar().click();
    http.expectOne('/api/packages/import').flush({ kind: 'characters', project_id: null, characters: [{ id: 'a', name: 'Lila', renamed_from: null }], scenes: 0, media: 5, warnings: [], project: null, character_list: [] });
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('1 personagem importado, com 5 imagens.');
    expect(html(fixture).querySelector('[role="alert"]')).toBeNull();
  });
});

describe('ViewerHostComponent', () => {
  it('abre a mídia com os dados da geração e fecha com o botão', async () => {
    TestBed.configureTestingModule({ providers: provideTestHttp() });
    const fixture = TestBed.createComponent(ViewerHostComponent);
    const viewer = TestBed.inject(ViewerService);
    await fixture.whenStable();
    const dialog = html(fixture).querySelector('dialog')!;
    expect(dialog.hasAttribute('open')).toBe(false);
    viewer.open(makeMedia({ id: 'v'.repeat(32), width: 512, height: 512, seed: 42, prompt: 'coelha lilás', model: 'FLUX.2 klein 4B' }), 'Lila');
    await fixture.whenStable();
    expect(dialog.hasAttribute('open') || dialog.open).toBe(true);
    const texto = dialog.textContent!;
    expect(texto).toContain('Lila');
    expect(texto).toContain('512 × 512');
    expect(texto).toContain('42');
    expect(texto).toContain('coelha lilás');
    expect(dialog.querySelector('img')!.getAttribute('src')).toBe(`/api/media/${'v'.repeat(32)}`);
    expect(dialog.querySelector('a[download]')!.getAttribute('href')).toBe(`/api/media/${'v'.repeat(32)}?download=true`);
    dialog.querySelector<HTMLButtonElement>('button')!.click();
    await fixture.whenStable();
    expect(viewer.current()).toBeNull();
    expect(dialog.hasAttribute('open')).toBe(false);
  });

  it('vídeo e áudio ganham o tocador certo', async () => {
    TestBed.configureTestingModule({ providers: provideTestHttp() });
    const fixture = TestBed.createComponent(ViewerHostComponent);
    const viewer = TestBed.inject(ViewerService);
    viewer.open(makeMedia({ kind: 'video', duration_s: 5 }));
    await fixture.whenStable();
    expect(html(fixture).querySelector('video')).not.toBeNull();
    viewer.open(makeMedia({ kind: 'audio' }));
    await fixture.whenStable();
    expect(html(fixture).querySelector('audio')).not.toBeNull();
  });
});
