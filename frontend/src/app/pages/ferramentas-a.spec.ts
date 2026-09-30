import { HttpEventType } from '@angular/common/http';
import { HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { Router } from '@angular/router';

import {
  FakeEventSource,
  installFakeEventSource,
  makeCharacter,
  makeJob,
  makeMedia,
  provideTestHttp,
  uninstallFakeEventSource,
} from '../../testing/fixtures';
import { JobsService } from '../core/jobs.service';
import { MachineService } from '../core/machine.service';
import { Character, CharacterDetail, Clip } from '../core/models';
import { ToastService } from '../core/toast.service';
import { PromptBoxComponent } from '../ui/prompt-box';
import { ClipesPage } from './clipes/clipes.page';
import { ImagemPage } from './imagem/imagem.page';
import { PersonagemPage } from './personagens/personagem.page';
import { PersonagensPage, statusOf } from './personagens/personagens.page';

const html = (f: ComponentFixture<unknown>): HTMLElement => f.nativeElement as HTMLElement;
const ESTIMATIVA = { width: 1024, height: 576, total_seconds: 90, total_label: '1 min 30 s', per_image_seconds: 90 };

/** O campo (input ou textarea) de um `fab-field` ou de um `.field` pelo texto do rótulo. */
function campo(fixture: ComponentFixture<unknown>, rotulo: string): HTMLInputElement | HTMLTextAreaElement {
  const label = [...html(fixture).querySelectorAll('label')].find((l) => l.textContent!.includes(rotulo));
  if (!label) throw new Error(`campo «${rotulo}» não encontrado`);
  return html(fixture).querySelector(`#${label.getAttribute('for')}`) as HTMLInputElement | HTMLTextAreaElement;
}

async function digitar(fixture: ComponentFixture<unknown>, rotulo: string, valor: string): Promise<void> {
  const el = campo(fixture, rotulo);
  el.value = valor;
  el.dispatchEvent(new Event('input'));
  await fixture.whenStable();
}

function botao(fixture: ComponentFixture<unknown>, texto: string): HTMLButtonElement {
  const b = [...html(fixture).querySelectorAll<HTMLButtonElement>('button')].find((x) => x.textContent!.includes(texto));
  if (!b) throw new Error(`botão «${texto}» não encontrado`);
  return b;
}

describe('ImagemPage', () => {
  let fixture: ComponentFixture<ImagemPage>;
  let http: HttpTestingController;
  let jobs: JobsService;
  const lila = makeCharacter({ id: 'a'.repeat(32), name: 'Lila' });

  beforeEach(async () => {
    localStorage.clear();
    installFakeEventSource();
    await TestBed.configureTestingModule({ imports: [ImagemPage], providers: provideTestHttp() }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    jobs = TestBed.inject(JobsService);
    fixture = TestBed.createComponent(ImagemPage);
  });

  afterEach(() => uninstallFakeEventSource());

  const iniciar = async (biblioteca = makeMedia({ role: 'cenario', prompt: 'um jardim', metadata: { format: '16:9' } })): Promise<void> => {
    fixture.detectChanges();
    http.expectOne('/api/characters').flush({ items: [lila], total: 1 });
    http.expectOne((r) => r.url === '/api/media').flush({ items: [biblioteca], total: 1 });
    http.expectOne((r) => r.url === '/api/images/estimate').flush(ESTIMATIVA);
    await fixture.whenStable();
  };

  it('carrega a biblioteca e mostra a estimativa de tempo neste computador', async () => {
    await iniciar();
    const texto = html(fixture).textContent!;
    expect(texto).toContain('Suas imagens (1)');
    expect(texto).toContain('Estimativa neste computador: cerca de 1 min 30 s para 1 imagem de 1024×576.');
    const pedido = http.match(() => true);
    expect(pedido).toEqual([]);
  });

  it('a biblioteca só pede imagens avulsas (sem dono) dos tipos de imagem', async () => {
    fixture.detectChanges();
    const req = http.expectOne((r) => r.url === '/api/media');
    expect(req.request.params.getAll('role')).toEqual(['cenario', 'objeto', 'thumbnail', 'livre']);
    expect(req.request.params.get('owner_type')).toBe('nenhum');
    expect(req.request.params.get('kind')).toBe('imagem');
    req.flush({ items: [], total: 0 });
    http.expectOne('/api/characters').flush({ items: [], total: 0 });
    http.match((r) => r.url === '/api/images/estimate').forEach((r) => r.flush(ESTIMATIVA));
  });

  it('gera com o que foi preenchido e cada variação aparece assim que fica pronta', async () => {
    await iniciar();
    expect(botao(fixture, 'Gerar imagem').disabled).toBe(true); // sem descrição
    await digitar(fixture, 'Descrição', 'um jardim florido de manhã');
    (html(fixture).querySelector('#img-count') as HTMLInputElement).value = '2';
    html(fixture).querySelector('#img-count')!.dispatchEvent(new Event('change'));
    const pilha = html(fixture).querySelector<HTMLButtonElement>('fab-character-picker button')!;
    pilha.click(); // inclui a Lila
    await fixture.whenStable();
    http.match((r) => r.url === '/api/images/estimate').filter((r) => !r.cancelled).forEach((r) => r.flush(ESTIMATIVA));
    expect(botao(fixture, 'Gerar imagem').disabled).toBe(false);
    botao(fixture, 'Gerar imagem').click();
    const req = http.expectOne('/api/images');
    expect(req.request.body).toEqual({
      form: { kind: 'livre', style: '2D', format: '16:9', characters: ['Lila'], description: 'um jardim florido de manhã', notes: '' },
      technical_prompt: null,
      quality: 'padrao',
      count: 2,
      seed: null,
      character_ids: [lila.id],
      based_on: null,
    });
    const job = makeJob({ id: 'g'.repeat(32), kind: 'imagem.gerar', status: 'queued', title: 'Gerar imagem (2 imagens)' });
    req.flush(job);
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Gerar imagem (2 imagens)');
    expect(botao(fixture, 'Gerar imagem').disabled).toBe(true); // ocupado até terminar

    // as variações chegam pelo fluxo ao vivo
    jobs.connect();
    const es = FakeEventSource.instances[0];
    const primeira = makeMedia({ id: '1'.repeat(32), role: 'livre', job_id: job.id, prompt: 'um jardim florido de manhã', seed: 11 });
    es.emit('media.created', primeira);
    await fixture.whenStable();
    const resultado = [...html(fixture).querySelectorAll('h2')].find((h) => h.textContent === 'Resultado')!;
    expect(resultado).toBeTruthy();
    expect(html(fixture).textContent).toContain('Suas imagens (2)');
    es.emit('media.created', makeMedia({ id: '2'.repeat(32), role: 'livre', job_id: 'outro-job' })); // de outra tarefa: só na biblioteca
    es.emit('media.created', makeMedia({ id: '3'.repeat(32), kind: 'video' })); // não é imagem: ignorada
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Suas imagens (3)');
    jobs.merge({ ...job, status: 'done', progress: 1 });
    await fixture.whenStable();
    expect(botao(fixture, 'Gerar imagem').disabled).toBe(false);
    expect(TestBed.inject(ToastService).toasts().map((t) => t.text)).toContain('Imagens prontas.');
    es.emit('media.deleted', { id: '1'.repeat(32) });
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Suas imagens (2)');
  });

  it('mostra o erro do servidor quando a geração é recusada', async () => {
    await iniciar();
    await digitar(fixture, 'Descrição', 'um jardim');
    botao(fixture, 'Gerar imagem').click();
    http.expectOne('/api/images').flush({ detail: 'O motor de imagens não está instalado.' }, { status: 503, statusText: 'Unavailable' });
    await fixture.whenStable();
    expect(html(fixture).querySelector('[role="alert"]')!.textContent).toContain('O motor de imagens não está instalado.');
    expect(botao(fixture, 'Gerar imagem').disabled).toBe(false);
  });

  it('o prompt lido preenche o formulário e avisa dos personagens que não estão na biblioteca', async () => {
    await iniciar();
    const caixa = fixture.debugElement.query(By.directive(PromptBoxComponent)).componentInstance as PromptBoxComponent;
    caixa.parsed.emit({
      text: '### IMAGEM',
      result: {
        type: 'imagem',
        source: 'estruturado',
        missing: [],
        warnings: [],
        form: { kind: 'cenario', style: '3D', format: '9:16', characters: ['Lila', 'Bia'], description: 'um bosque ao entardecer', notes: 'sem gente' },
      },
    });
    http.match((r) => r.url === '/api/images/estimate').forEach((r) => r.flush(ESTIMATIVA));
    await fixture.whenStable();
    expect((campo(fixture, 'Descrição') as HTMLTextAreaElement).value).toBe('um bosque ao entardecer');
    expect((html(fixture).querySelector('#img-kind') as HTMLSelectElement).value).toBe('cenario');
    expect((html(fixture).querySelector('#img-format') as HTMLSelectElement).value).toBe('9:16');
    expect(html(fixture).querySelector('fab-segmented [aria-checked="true"]')!.textContent!.trim()).toBe('3D');
    // a Lila da biblioteca é 2D, mas o nome casa: fica escolhida; a Bia não existe
    expect(html(fixture).textContent).toContain('Não achei na biblioteca: Bia.');
    expect(html(fixture).querySelector('fab-character-picker button')!.getAttribute('aria-pressed')).toBe('true');
    expect(TestBed.inject(ToastService).toasts().at(-1)?.text).toContain('Formulário preenchido');
  });

  it('«gerar parecida» usa a imagem como base e o pedido leva o id dela', async () => {
    const base = makeMedia({ id: 'b'.repeat(32), role: 'cenario', prompt: 'um jardim', metadata: {} });
    await iniciar(base);
    botao(fixture, 'Gerar parecida').click();
    http.match((r) => r.url === '/api/images/estimate').forEach((r) => r.flush(ESTIMATIVA));
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Parecida com esta imagem');
    expect((campo(fixture, 'Descrição') as HTMLTextAreaElement).value).toBe('um jardim'); // já parte da descrição da imagem
    botao(fixture, 'Gerar imagem').click();
    expect(http.expectOne('/api/images').request.body.based_on).toBe(base.id);
    botao(fixture, 'Não usar como base');
  });

  it('apaga da biblioteca depois de confirmar', async () => {
    const media = makeMedia({ id: 'd'.repeat(32), role: 'objeto' });
    await iniciar(media);
    const confirmar = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    const apagar = html(fixture).querySelector<HTMLButtonElement>('button[aria-label="Apagar imagem"]')!;
    apagar.click();
    http.expectNone('/api/media/' + media.id);
    apagar.click();
    http.expectOne(`/api/media/${media.id}`).flush({ deleted: true });
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Suas imagens (0)');
    expect(confirmar).toHaveBeenCalledTimes(2);
    confirmar.mockRestore();
  });

  it('apagar não conta duas vezes quando o evento do servidor chega antes da resposta do pedido', async () => {
    const a = makeMedia({ id: 'a'.repeat(32), role: 'objeto' });
    const b = makeMedia({ id: 'b'.repeat(32), role: 'objeto' });
    fixture.detectChanges();
    http.expectOne('/api/characters').flush({ items: [lila], total: 1 });
    http.expectOne((r) => r.url === '/api/media').flush({ items: [a, b], total: 2 });
    http.expectOne((r) => r.url === '/api/images/estimate').flush(ESTIMATIVA);
    await fixture.whenStable();
    jobs.connect();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    html(fixture).querySelector<HTMLButtonElement>('button[aria-label="Apagar imagem"]')!.click();
    const pedido = http.expectOne(`/api/media/${a.id}`);
    FakeEventSource.instances[0].emit('media.deleted', { id: a.id }); // no navegador de verdade o evento costuma chegar primeiro
    pedido.flush({ deleted: true });
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Suas imagens (1)');
    expect(html(fixture).querySelectorAll('fab-media-tile')).toHaveLength(1);
  });

  it('montar o prompt técnico mostra o texto que vai para o modelo e só manda se você editou', async () => {
    await iniciar();
    await digitar(fixture, 'Descrição', 'um jardim');
    botao(fixture, 'Montar a partir da descrição').click();
    const req = http.expectOne('/api/images/technical-prompt');
    expect(req.request.body.form.description).toBe('um jardim');
    req.flush({ technical_prompt: 'flat 2D cartoon, a flower garden', negative_prompt: 'scary' });
    await fixture.whenStable();
    expect((campo(fixture, 'Prompt técnico') as HTMLTextAreaElement).value).toBe('flat 2D cartoon, a flower garden');
    botao(fixture, 'Gerar imagem').click();
    expect(http.expectOne('/api/images').request.body.technical_prompt).toBeNull(); // não foi editado: o servidor monta
  });
});

describe('statusOf', () => {
  it('diz o que falta para o personagem entrar num vídeo', () => {
    expect(statusOf(makeCharacter({ main_image_id: null, has_cutout: false }))).toBe('choose');
    expect(statusOf(makeCharacter({ has_cutout: false }))).toBe('cutout');
    expect(statusOf(makeCharacter())).toBe('ready');
  });
});

describe('PersonagensPage', () => {
  let fixture: ComponentFixture<PersonagensPage>;
  let http: HttpTestingController;
  let router: Router;
  const lila = makeCharacter({ id: 'a'.repeat(32), name: 'Lila' });
  const bento = makeCharacter({ id: 'b'.repeat(32), name: 'Bento', style: '3D', has_cutout: false });
  const novo = makeCharacter({ id: 'n'.repeat(32), name: 'Bia', main_image_id: null, has_cutout: false, main_image_url: null });

  beforeEach(async () => {
    localStorage.clear();
    installFakeEventSource();
    await TestBed.configureTestingModule({ imports: [PersonagensPage], providers: provideTestHttp() }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate').mockResolvedValue(true);
    fixture = TestBed.createComponent(PersonagensPage);
  });

  afterEach(() => uninstallFakeEventSource());

  const iniciar = async (items: Character[] = [lila, bento]): Promise<void> => {
    fixture.detectChanges();
    http.expectOne('/api/characters').flush({ items, total: items.length });
    await fixture.whenStable();
  };

  it('lista os personagens com o estado de cada um, busca e filtro por estilo', async () => {
    await iniciar();
    const cartoes = (): string[] => [...html(fixture).querySelectorAll('ul.tile-grid li')].map((li) => li.textContent!.replace(/\s+/g, ' ').trim());
    expect(cartoes()).toHaveLength(2);
    expect(cartoes()[0]).toContain('Lila');
    expect(cartoes()[0]).toContain('Pronto para vídeos');
    expect(cartoes()[1]).toContain('Falta recortar o fundo');
    expect(html(fixture).querySelector('ul.tile-grid a')!.getAttribute('href')).toBe(`/personagens/${lila.id}`);
    botao(fixture, '3D').click();
    await fixture.whenStable();
    expect(cartoes()).toHaveLength(1);
    expect(cartoes()[0]).toContain('Bento');
    botao(fixture, 'Todos').click();
    await digitar(fixture, 'Buscar pelo nome', 'lil');
    expect(cartoes()).toHaveLength(1);
    await digitar(fixture, 'Buscar pelo nome', 'zzz');
    expect(html(fixture).textContent).toContain('Nenhum personagem encontrado com esse filtro.');
  });

  it('biblioteca vazia convida a criar o primeiro personagem', async () => {
    await iniciar([]);
    expect(html(fixture).textContent).toContain('A biblioteca está vazia');
    expect(html(fixture).textContent).toContain('Criar o primeiro personagem');
  });

  it('o prompt lido preenche a ficha e criar leva para a página do personagem', async () => {
    await iniciar([]);
    expect(botao(fixture, 'Criar personagem').disabled).toBe(true);
    const caixa = fixture.debugElement.query(By.directive(PromptBoxComponent)).componentInstance as PromptBoxComponent;
    caixa.parsed.emit({
      text: '### PERSONAGEM\nNome: Bia',
      result: { type: 'personagem', source: 'estruturado', missing: [], warnings: [], form: { name: 'Bia', style: '3D', species: 'raposa', appearance: 'pelo ruivo' } },
    });
    await fixture.whenStable();
    expect((campo(fixture, 'Nome') as HTMLInputElement).value).toBe('Bia');
    expect((campo(fixture, 'Aparência') as HTMLTextAreaElement).value).toBe('pelo ruivo');
    const criar = [...html(fixture).querySelectorAll<HTMLButtonElement>('#ficha button.btn-primary')][0];
    expect(criar.disabled).toBe(false);
    criar.click();
    const req = http.expectOne((r) => r.url === '/api/characters' && r.method === 'POST');
    expect(req.request.body.form).toMatchObject({ name: 'Bia', style: '3D', species: 'raposa' });
    expect(req.request.body.original_prompt).toBe('### PERSONAGEM\nNome: Bia');
    req.flush(novo);
    await fixture.whenStable();
    expect(router.navigate).toHaveBeenCalledWith(['/personagens', novo.id]);
  });

  it('nome repetido mostra o aviso e o caminho para o personagem que já existe', async () => {
    await iniciar([lila]);
    (campo(fixture, 'Nome') as HTMLInputElement).value = 'Lila';
    campo(fixture, 'Nome').dispatchEvent(new Event('input'));
    await digitar(fixture, 'Aparência', 'pelo lilás');
    [...html(fixture).querySelectorAll<HTMLButtonElement>('#ficha button.btn-primary')][0].click();
    http.expectOne((r) => r.url === '/api/characters' && r.method === 'POST').flush(
      { detail: 'Já existe um personagem chamado «Lila» em 2D.', existing_id: lila.id },
      { status: 409, statusText: 'Conflict' },
    );
    await fixture.whenStable();
    const aviso = html(fixture).querySelector('[role="alert"]')!;
    expect(aviso.textContent).toContain('Já existe um personagem chamado «Lila» em 2D.');
    expect(aviso.querySelector('a')!.getAttribute('href')).toBe(`/personagens/${lila.id}`);
  });

  it('«Importar imagem do computador» abre o seletor de arquivos e já leva ao envio, com o nome do arquivo', async () => {
    await iniciar([]);
    const seletor = html(fixture).querySelector<HTMLInputElement>('#upload-file')!;
    const abrir = vi.spyOn(seletor, 'click').mockImplementation(() => undefined);
    botao(fixture, 'Importar imagem do computador').click();
    expect(abrir).toHaveBeenCalledTimes(1);
    const arquivo = new File(['png'], 'meu-coelho.png', { type: 'image/png' });
    Object.defineProperty(seletor, 'files', { value: [arquivo], configurable: true });
    seletor.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    expect((campo(fixture, 'Nome') as HTMLInputElement).value).toBe('meu-coelho'); // o painel de envio abriu sozinho
    expect(html(fixture).textContent).toContain('Arquivo escolhido: meu-coelho.png');
    botao(fixture, 'Escolher a imagem no computador').click(); // o botão da seção abre o mesmo seletor
    expect(abrir).toHaveBeenCalledTimes(2);
    expect(html(fixture).querySelector('#upload-file')).toBe(seletor); // um seletor só
  });

  it('envia uma imagem que você já tem, com o direito de uso confirmado', async () => {
    await iniciar([]);
    botao(fixture, 'Enviar uma imagem').click();
    await fixture.whenStable();
    expect(botao(fixture, 'Enviar e criar').disabled).toBe(true);
    const arquivo = new File(['png'], 'bia-final.png', { type: 'image/png' });
    const entrada = html(fixture).querySelector<HTMLInputElement>('#upload-file')!;
    Object.defineProperty(entrada, 'files', { value: [arquivo], configurable: true });
    entrada.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    expect((campo(fixture, 'Nome') as HTMLInputElement).value).toBe('bia-final'); // o nome vem do arquivo
    const direito = html(fixture).querySelector<HTMLInputElement>('input[type=checkbox]')!;
    direito.checked = true;
    direito.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    botao(fixture, 'Enviar e criar').click();
    const req = http.expectOne((r) => r.url === '/api/characters/upload');
    expect(req.request.params.get('name')).toBe('bia-final');
    expect(req.request.params.get('rights')).toBe('true');
    expect(req.request.body).toBe(arquivo);
    const job = makeJob({ id: 'r'.repeat(32), kind: 'personagem.recortar', status: 'queued' });
    req.flush({ character: novo, job });
    await fixture.whenStable();
    expect(TestBed.inject(JobsService).byId(job.id)).toBeTruthy(); // o recorte automático aparece na fila
    expect(router.navigate).toHaveBeenCalledWith(['/personagens', novo.id]);
  });

  it('um recorte que termina recarrega os cartões', async () => {
    await iniciar();
    TestBed.inject(JobsService).merge(makeJob({ id: 'c1', kind: 'personagem.recortar', status: 'running' }));
    TestBed.inject(JobsService).merge(makeJob({ id: 'c1', kind: 'personagem.recortar', status: 'done' }));
    http.expectOne('/api/characters').flush({ items: [{ ...bento, has_cutout: true }], total: 1 });
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Pronto para vídeos');
  });

  it('exporta a biblioteca e importa um pacote de outra máquina', async () => {
    await iniciar();
    const baixar = [...html(fixture).querySelectorAll<HTMLAnchorElement>('a[download]')].find((a) => a.getAttribute('href') === '/api/packages/characters');
    expect(baixar).toBeTruthy();
    expect(html(fixture).querySelector('fab-package-import')).not.toBeNull();
  });
});

describe('PersonagemPage', () => {
  let fixture: ComponentFixture<PersonagemPage>;
  let http: HttpTestingController;
  let router: Router;
  let jobs: JobsService;
  const id = 'a'.repeat(32);
  const principal = makeMedia({ id: 'a'.repeat(32), role: 'variacao', seed: 5 });
  const outra = makeMedia({ id: 'b'.repeat(32), role: 'variacao', seed: 6 });
  const recorteDoLado = makeMedia({ id: 'c'.repeat(32), role: 'recorte', metadata: { slot: 'lado', facing: 'right' } });

  const detalhe = (mudar: Partial<CharacterDetail['character']> = {}): CharacterDetail => ({
    character: makeCharacter({ id, name: 'Lila', main_image_id: principal.id, ...mudar }),
    variations: [principal, outra],
    uploads: [],
    sheet: [
      { slot: 'principal', image: principal, cutout: makeMedia({ role: 'recorte', metadata: { slot: 'principal' } }) },
      { slot: 'frente', image: null, cutout: null },
      { slot: 'lado', image: makeMedia({ role: 'pose' }), cutout: recorteDoLado },
    ],
    voice_tests: [makeMedia({ kind: 'audio', role: 'voz_teste', prompt: 'Oi! Eu sou a Lila.' })],
    versions: [{ version: 1, images: 3 }],
  });

  beforeEach(async () => {
    localStorage.clear();
    installFakeEventSource();
    await TestBed.configureTestingModule({ imports: [PersonagemPage], providers: provideTestHttp() }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    jobs = TestBed.inject(JobsService);
    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate').mockResolvedValue(true);
    fixture = TestBed.createComponent(PersonagemPage);
    fixture.componentRef.setInput('id', id);
  });

  afterEach(() => uninstallFakeEventSource());

  const iniciar = async (d: CharacterDetail = detalhe()): Promise<void> => {
    fixture.detectChanges();
    http.expectOne('/api/characters/voices').flush({ voices: { 'pt-BR': [{ id: 'pf_dora', nome: 'Dora (feminina)', lingua: 'pt-br' }, { id: 'pm_alex', nome: 'Alex (masculina)', lingua: 'pt-br' }] } });
    http.expectOne(`/api/characters/${id}`).flush(d);
    http.match((r) => r.url === '/api/characters/estimate').forEach((r) => r.flush({ width: 512, height: 512, total_seconds: 300, total_label: '5 min' }));
    http.match((r) => r.url === '/api/characters').forEach((r) => r.flush({ items: [], total: 0 }));
    await fixture.whenStable();
  };

  it('mostra o personagem, as variações com a principal marcada e o estado', async () => {
    await iniciar();
    const texto = html(fixture).textContent!;
    expect(html(fixture).querySelector('h1')!.textContent).toBe('Lila');
    expect(texto).toContain('Pronto para vídeos');
    expect(texto).toContain('Estimativa neste computador: cerca de 5 min para 4 imagens de 512×512.');
    expect(botao(fixture, 'Escolhida').disabled).toBe(true);
    expect(botao(fixture, 'Escolher esta')).toBeTruthy();
    expect(texto).toContain('Imagem principal');
  });

  it('escolher uma variação pede o recorte e mostra o andamento', async () => {
    await iniciar();
    botao(fixture, 'Escolher esta').click();
    const req = http.expectOne(`/api/characters/${id}/choose`);
    expect(req.request.body).toEqual({ media_id: outra.id });
    const job = makeJob({ id: 'j'.repeat(32), kind: 'personagem.recortar', status: 'running', title: 'Recortar o fundo de Lila', params: { character_id: id } });
    req.flush({ character: makeCharacter({ id, main_image_id: outra.id }), job });
    http.expectOne(`/api/characters/${id}`).flush(detalhe({ main_image_id: outra.id }));
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Recortar o fundo de Lila'); // a tarefa deste personagem aparece no topo
    expect(TestBed.inject(ToastService).toasts().at(-1)?.text).toContain('Recortando o fundo');
  });

  it('gera variações com a quantidade e a semente pedidas', async () => {
    await iniciar();
    (html(fixture).querySelector('#var-count') as HTMLSelectElement).value = '2';
    html(fixture).querySelector('#var-count')!.dispatchEvent(new Event('change'));
    await digitar(fixture, 'Semente', '77');
    http.match((r) => r.url === '/api/characters/estimate').forEach((r) => r.flush({ width: 512, height: 512, total_seconds: 150, total_label: '2 min 30 s' }));
    botao(fixture, 'Gerar 2 variações').click();
    const req = http.expectOne(`/api/characters/${id}/variations`);
    expect(req.request.body).toEqual({ count: 2, quality: 'rascunho', seed: 77, technical_prompt: null });
    req.flush(makeJob({ id: 'v1', kind: 'personagem.variacoes', status: 'queued', params: { character_id: id } }));
    await fixture.whenStable();
    expect(botao(fixture, 'Gerar 2 variações').disabled).toBe(true); // já há uma tarefa de variações em andamento
  });

  it('o fim de uma tarefa deste personagem recarrega os dados; uma variação nova aparece sozinha', async () => {
    await iniciar();
    jobs.merge(makeJob({ id: 'f1', kind: 'personagem.folha', status: 'running', params: { character_id: id } }));
    jobs.merge(makeJob({ id: 'f1', kind: 'personagem.folha', status: 'done', params: { character_id: id } }));
    http.expectOne(`/api/characters/${id}`).flush(detalhe());
    jobs.connect();
    FakeEventSource.instances[0].emit('media.created', makeMedia({ owner_id: id, owner_type: 'personagem' }));
    vi.useFakeTimers();
    vi.advanceTimersByTime(600);
    vi.useRealTimers();
    await new Promise((r) => setTimeout(r, 600)); // o recarregamento espera um pouco para juntar várias imagens
    http.match(`/api/characters/${id}`).forEach((r) => r.flush(detalhe()));
    // tarefa de outro personagem não recarrega
    jobs.merge(makeJob({ id: 'x', kind: 'personagem.folha', status: 'done', params: { character_id: 'z'.repeat(32) } }));
    http.expectNone(`/api/characters/${id}`);
  });

  it('a folha de referência mostra cada pose, deixa escolher as que faltam e corrige para onde o recorte olha', async () => {
    await iniciar();
    const texto = html(fixture).textContent!;
    expect(texto).toContain('De frente');
    expect(texto).toContain('Ainda não gerada');
    // escolher poses e gerar
    const alternar = (nome: string): HTMLButtonElement => [...html(fixture).querySelectorAll<HTMLButtonElement>('.chips button')].find((b) => b.textContent!.includes(nome))!;
    alternar('Feliz').click();
    alternar('De frente').click(); // sai (estava marcada por padrão)
    await fixture.whenStable();
    http.match((r) => r.url === '/api/characters/estimate').forEach((r) => r.flush({ width: 512, height: 512, total_seconds: 600, total_label: '10 min' }));
    botao(fixture, 'Gerar a folha de referência').click();
    expect(http.expectOne(`/api/characters/${id}/sheet`).request.body).toEqual({ slots: ['tres_quartos', 'lado', 'feliz'], quality: 'rascunho' });
    // direção do olhar do recorte de lado
    const olhar = html(fixture).querySelector<HTMLSelectElement>('#facing-lado')!;
    expect(olhar.value).toBe('right');
    olhar.value = 'left';
    olhar.dispatchEvent(new Event('change'));
    const req = http.expectOne(`/api/characters/${id}/cutouts/${recorteDoLado.id}/facing`);
    expect(req.request.body).toEqual({ facing: 'left' });
    req.flush({ ...recorteDoLado, metadata: { slot: 'lado', facing: 'left' } });
    http.expectOne(`/api/characters/${id}`).flush(detalhe());
  });

  it('sem imagem principal a folha pede a escolha antes; sem recorte oferece recortar', async () => {
    const d = detalhe({ main_image_id: null, has_cutout: false });
    await iniciar(d);
    expect(html(fixture).textContent).toContain('Escolha uma variação acima antes de gerar a folha de referência.');
    expect(html(fixture).textContent).toContain('Escolher uma imagem');
  });

  it('o recorte que faltou pode ser pedido de novo', async () => {
    await iniciar(detalhe({ has_cutout: false }));
    expect(html(fixture).textContent).toContain('ainda não foi recortado');
    botao(fixture, 'Recortar o fundo').click();
    const req = http.expectOne(`/api/characters/${id}/choose`);
    expect(req.request.body).toEqual({ media_id: principal.id }); // escolher de novo a principal pede o recorte
    req.flush({ character: makeCharacter({ id }), job: makeJob({ id: 'rc', kind: 'personagem.recortar', status: 'queued', params: { character_id: id } }) });
  });

  it('edita a ficha e salva só quando há mudança; o estilo não muda por aqui', async () => {
    await iniciar();
    expect(botao(fixture, 'Salvar a ficha').disabled).toBe(true);
    expect(html(fixture).textContent).toContain('não muda; use «Criar a versão»');
    await digitar(fixture, 'Personalidade', 'curiosa e teimosa');
    expect(botao(fixture, 'Salvar a ficha').disabled).toBe(false);
    botao(fixture, 'Salvar a ficha').click();
    const req = http.expectOne(`/api/characters/${id}`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body.form.personality).toBe('curiosa e teimosa');
    req.flush(makeCharacter({ id }));
    http.expectOne(`/api/characters/${id}`).flush(detalhe());
  });

  it('voz: escolhe, ajusta, ouve uma frase e salva', async () => {
    await iniciar();
    expect((campo(fixture, 'Frase para ouvir') as HTMLInputElement).value).toBe('Oi! Eu sou Lila. Vamos brincar juntos hoje?');
    const voz = html(fixture).querySelector<HTMLSelectElement>('#voice-id')!;
    voz.value = 'pm_alex';
    voz.dispatchEvent(new Event('change'));
    const velocidade = html(fixture).querySelector<HTMLInputElement>('#voice-speed')!;
    velocidade.value = '0.8';
    velocidade.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    botao(fixture, 'Ouvir a voz').click();
    const teste = http.expectOne(`/api/characters/${id}/voice-test`);
    expect(teste.request.body).toEqual({ text: 'Oi! Eu sou Lila. Vamos brincar juntos hoje?', voice: { id: 'pm_alex', speed: 0.8, pitch: 1 } });
    teste.flush(makeJob({ id: 'vt', kind: 'personagem.voz_teste', status: 'queued', params: { character_id: id } }));
    botao(fixture, 'Salvar a voz').click();
    const salvar = http.expectOne(`/api/characters/${id}/voice`);
    expect(salvar.request.method).toBe('PUT');
    expect(salvar.request.body).toEqual({ id: 'pm_alex', speed: 0.8, pitch: 1 });
    salvar.flush(makeCharacter({ id }));
    http.expectOne(`/api/characters/${id}`).flush(detalhe());
    await fixture.whenStable();
    expect(html(fixture).querySelector('audio')).not.toBeNull(); // as vozes de teste tocam ali mesmo
  });

  it('cria a versão no outro estilo e vai para ela', async () => {
    await iniciar();
    botao(fixture, 'Criar a versão 3D').click();
    const req = http.expectOne(`/api/characters/${id}/convert`);
    expect(req.request.body).toEqual({ count: 2, quality: 'rascunho' });
    req.flush({ character: makeCharacter({ id: 'n'.repeat(32), style: '3D' }), job: makeJob({ id: 'cv', status: 'queued' }) });
    await fixture.whenStable();
    expect(router.navigate).toHaveBeenCalledWith(['/personagens', 'n'.repeat(32)]);
  });

  it('apagar pede confirmação e volta para a biblioteca; personagem inexistente explica', async () => {
    await iniciar();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    botao(fixture, 'Apagar personagem').click();
    http.expectOne(`/api/characters/${id}`).flush({ deleted: true, media_removed: 5 });
    await fixture.whenStable();
    expect(router.navigate).toHaveBeenCalledWith(['/personagens']);

    const outro = TestBed.createComponent(PersonagemPage);
    outro.componentRef.setInput('id', 'f'.repeat(32));
    outro.detectChanges();
    http.match('/api/characters/voices').forEach((r) => r.flush({ voices: {} }));
    http.expectOne(`/api/characters/${'f'.repeat(32)}`).flush({ detail: 'nada' }, { status: 404, statusText: 'Not Found' });
    await outro.whenStable();
    expect(html(outro).textContent).toContain('Personagem não encontrado');
  });
});

describe('ClipesPage', () => {
  let fixture: ComponentFixture<ClipesPage>;
  let http: HttpTestingController;
  let router: Router;
  const lila = makeCharacter({ id: 'a'.repeat(32), name: 'Lila' });
  const clipe = (mudar: Partial<Clip> = {}): Clip => ({ ...makeMedia({ kind: 'video', role: 'clipe_rapido', duration_s: 5, width: 1080, height: 1920 }), project_title: null, variants: [], ...mudar });

  beforeEach(async () => {
    localStorage.clear();
    installFakeEventSource();
    await TestBed.configureTestingModule({ imports: [ClipesPage], providers: provideTestHttp() }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate').mockResolvedValue(true);
    fixture = TestBed.createComponent(ClipesPage);
  });

  afterEach(() => uninstallFakeEventSource());

  const iniciar = async (clips: Clip[] = [clipe({ id: '1'.repeat(32) }), clipe({ id: '2'.repeat(32), role: 'clipe_enviado' })]): Promise<void> => {
    TestBed.inject(MachineService).snapshot.set({
      exists: true,
      valid: true,
      errors: [],
      measurements: {},
      capabilities: [{ id: 'clipe_rapido', name: 'Clipe rápido', section: '7.7', state: 'slow', reason: 'Cenário gerado por IA.', eta: '≈ 2 min', eta_measured: false }],
    });
    fixture.detectChanges();
    http.expectOne('/api/characters').flush({ items: [lila, makeCharacter({ id: 'b'.repeat(32), name: 'Sem recorte', has_cutout: false })], total: 2 });
    http.expectOne((r) => r.url === '/api/clips').flush({ items: clips, total: clips.length });
    await fixture.whenStable();
  };

  it('lista os clipes com o tipo e o tamanho, e filtra por tipo', async () => {
    await iniciar();
    const texto = html(fixture).textContent!;
    expect(texto).toContain('Biblioteca de clipes (2)');
    expect(texto).toContain('Clipe rápido');
    expect(texto).toContain('1080×1920');
    botao(fixture, 'Enviado').click();
    const req = http.expectOne((r) => r.url === '/api/clips');
    expect(req.request.params.getAll('role')).toEqual(['clipe_enviado']);
    req.flush({ items: [clipe({ role: 'clipe_enviado' })], total: 1 });
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Biblioteca de clipes (1)');
  });

  it('clipe rápido: só oferece personagens com o PNG transparente e manda o pedido completo', async () => {
    await iniciar();
    const opcoes = [...html(fixture).querySelectorAll<HTMLOptionElement>('#quick-character option')].map((o) => o.textContent!.trim());
    expect(opcoes).toEqual(['Escolha um personagem', 'Lila (2D)']);
    expect(botao(fixture, 'Gerar clipe').disabled).toBe(true);
    const escolha = html(fixture).querySelector<HTMLSelectElement>('#quick-character')!;
    escolha.value = lila.id;
    escolha.dispatchEvent(new Event('change'));
    await digitar(fixture, 'O que acontece no clipe', 'pulando de alegria no jardim');
    expect(botao(fixture, 'Gerar clipe').disabled).toBe(false);
    expect(html(fixture).textContent).toContain('Cenário gerado por IA. · ≈ 2 min');
    botao(fixture, 'Gerar clipe').click();
    const req = http.expectOne('/api/clips/quick');
    expect(req.request.body).toEqual({ character_id: lila.id, prompt: 'pulando de alegria no jardim', duration_s: 5, format: '9:16', quality: 'rascunho', seed: null });
    req.flush(makeJob({ id: 'q1', kind: 'clipe.rapido', status: 'queued', title: 'Clipe rápido de Lila' }));
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Clipe rápido de Lila');
  });

  it('une clipes na ordem escolhida, com transição e tamanho', async () => {
    await iniciar();
    const marcar = html(fixture).querySelectorAll<HTMLInputElement>('fab-media-tile input[type=checkbox]');
    marcar[1].checked = true;
    marcar[1].dispatchEvent(new Event('change'));
    marcar[0].checked = true;
    marcar[0].dispatchEvent(new Event('change'));
    await fixture.whenStable();
    expect(botao(fixture, 'Unir 2 vídeos').disabled).toBe(false);
    // o segundo clipe marcado vem primeiro; sobe e desce pelos botões (alternativa ao arrastar)
    const ordem = (): string[] => [...html(fixture).querySelectorAll('ol li')].map((li) => li.textContent!.trim().slice(0, 1));
    expect(ordem()).toEqual(['1', '2']);
    html(fixture).querySelectorAll<HTMLButtonElement>('ol button[aria-label="Descer"]')[0].click();
    await fixture.whenStable();
    html(fixture).querySelectorAll<HTMLButtonElement>('ol button[aria-label="Subir"]')[1].click();
    await fixture.whenStable();
    (html(fixture).querySelector('#join-transition') as HTMLSelectElement).value = 'fade';
    html(fixture).querySelector('#join-transition')!.dispatchEvent(new Event('change'));
    botao(fixture, 'Unir 2 vídeos').click();
    const req = http.expectOne('/api/clips/join');
    expect(req.request.body.transition).toBe('fade');
    expect(req.request.body.clip_ids).toHaveLength(2);
    req.flush(makeJob({ id: 'u1', kind: 'clipe.unir', status: 'queued' }));
  });

  it('gera em outro formato e continua a partir do último quadro', async () => {
    const c1 = clipe({ id: '1'.repeat(32) });
    await iniciar([c1]);
    const naBiblioteca = (texto: string): HTMLButtonElement =>
      [...html(fixture).querySelectorAll<HTMLButtonElement>('fab-media-tile button')].find((b) => b.textContent!.includes(texto))!;
    naBiblioteca('Outro formato').click();
    await fixture.whenStable();
    (html(fixture).querySelector('#reframe-preset') as HTMLSelectElement).value = '16:9';
    html(fixture).querySelector('#reframe-preset')!.dispatchEvent(new Event('change'));
    botao(fixture, 'Gerar o novo formato').click();
    const req = http.expectOne(`/api/clips/${c1.id}/reframe`);
    expect(req.request.body).toEqual({ preset: '16:9', mode: 'fit' });
    req.flush(makeJob({ id: 'rf', kind: 'clipe.reenquadrar', status: 'queued' }));

    naBiblioteca('Continuar').click();
    await fixture.whenStable();
    expect(botao(fixture, 'Criar o projeto de continuação').disabled).toBe(true);
    await digitar(fixture, 'O que acontece a seguir', 'A Lila encontra um amigo.');
    await digitar(fixture, 'O que aparece no final do clipe', 'Lila sentada no jardim');
    botao(fixture, 'Criar o projeto de continuação').click();
    const cont = http.expectOne(`/api/clips/${c1.id}/continue`);
    expect(cont.request.body).toEqual({ prompt: 'A Lila encontra um amigo.', character_ids: [], title: '', last_scene: 'Lila sentada no jardim' });
    cont.flush({ project: { id: 'p'.repeat(32) }, last_frame: makeMedia(), source: c1 });
    await fixture.whenStable();
    expect(router.navigate).toHaveBeenCalledWith(['/projetos', 'p'.repeat(32)]);
  });

  it('envia um vídeo com o andamento e coloca o clipe na biblioteca', async () => {
    await iniciar([]);
    expect(html(fixture).textContent).toContain('Nenhum clipe ainda');
    expect(botao(fixture, 'Enviar vídeo').disabled).toBe(true);
    const arquivo = new File(['mp4'], 'meu.mp4', { type: 'video/mp4' });
    const entrada = html(fixture).querySelector<HTMLInputElement>('#clip-file')!;
    Object.defineProperty(entrada, 'files', { value: [arquivo], configurable: true });
    entrada.dispatchEvent(new Event('change'));
    const direito = html(fixture).querySelector<HTMLInputElement>('fab-section#enviar input[type=checkbox], input[type=checkbox]:last-of-type')!;
    [...html(fixture).querySelectorAll<HTMLInputElement>('input[type=checkbox]')].at(-1)!.click();
    void direito;
    await fixture.whenStable();
    botao(fixture, 'Enviar vídeo').click();
    const req = http.expectOne((r) => r.url === '/api/clips/upload');
    expect(req.request.body).toBe(arquivo);
    req.event({ type: HttpEventType.UploadProgress, loaded: 30, total: 60 });
    await fixture.whenStable();
    expect(html(fixture).querySelector('[role="progressbar"]')!.getAttribute('aria-valuenow')).toBe('50');
    req.flush(clipe({ id: '9'.repeat(32), role: 'clipe_enviado' }));
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Biblioteca de clipes (0)'); // o total vem do servidor; o clipe já está na lista
    expect(html(fixture).querySelectorAll('fab-media-tile')).toHaveLength(1);
    expect(TestBed.inject(ToastService).toasts().at(-1)?.text).toContain('Vídeo enviado');
  });

  it('apaga um clipe depois de confirmar', async () => {
    const c1 = clipe({ id: '1'.repeat(32) });
    await iniciar([c1]);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    html(fixture).querySelector<HTMLButtonElement>('button[aria-label="Apagar clipe"]')!.click();
    http.expectOne((r) => r.url === `/api/clips/${c1.id}` && r.method === 'DELETE').flush({ deleted: true });
    await fixture.whenStable();
    expect(html(fixture).querySelectorAll('fab-media-tile')).toHaveLength(0);
  });

  it('apagar não conta duas vezes quando o evento do servidor chega antes da resposta do pedido', async () => {
    const c1 = clipe({ id: '1'.repeat(32) });
    const c2 = clipe({ id: '2'.repeat(32) });
    await iniciar([c1, c2]);
    TestBed.inject(JobsService).connect();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    html(fixture).querySelector<HTMLButtonElement>('button[aria-label="Apagar clipe"]')!.click();
    const pedido = http.expectOne((r) => r.url === `/api/clips/${c1.id}` && r.method === 'DELETE');
    FakeEventSource.instances[0].emit('media.deleted', { id: c1.id });
    pedido.flush({ deleted: true });
    await fixture.whenStable();
    expect(html(fixture).textContent).toContain('Biblioteca de clipes (1)');
    expect(html(fixture).querySelectorAll('fab-media-tile')).toHaveLength(1);
  });
});
