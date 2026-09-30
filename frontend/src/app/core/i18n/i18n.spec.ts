import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { TestBed } from '@angular/core/testing';

import { EN } from './en';
import { I18nService } from './i18n.service';
import { PT_BR } from './pt-br';
import { TPipe } from './t.pipe';

describe('I18nService', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.lang = '';
  });

  it('usa português por padrão e troca de idioma', () => {
    const i18n = TestBed.inject(I18nService);
    expect(i18n.lang()).toBe('pt-BR');
    expect(i18n.t('nav.fila')).toBe('Fila');
    i18n.set('en');
    TestBed.tick();
    expect(i18n.t('nav.fila')).toBe('Queue');
    expect(document.documentElement.lang).toBe('en');
    expect(localStorage.getItem('fabulim.lang')).toBe('en');
  });

  it('interpola parâmetros e mantém o {marcador} quando falta o valor', () => {
    const i18n = TestBed.inject(I18nService);
    expect(i18n.t('fila.eta', { time: '2 min' })).toBe('faltam ~2 min');
    expect(i18n.t('fila.eta')).toBe('faltam ~{time}');
    expect(i18n.t('fila.eta', {})).toBe('faltam ~{time}');
  });

  it('escolhe singular ou plural pelo valor do parâmetro', () => {
    const i18n = TestBed.inject(I18nService);
    expect(i18n.t('proj.scenes', { n: 1 })).toBe('1 cena');
    expect(i18n.t('proj.scenes', { n: 0 })).toBe('0 cenas');
    expect(i18n.t('proj.scenes', { n: 12 })).toBe('12 cenas');
    expect(i18n.t('proj.approval.pending', { n: 1 })).toBe('Falta 1 cena para aprovar.');
    expect(i18n.t('proj.approval.pending', { n: 3 })).toBe('Faltam 3 cenas para aprovar.');
    expect(i18n.t('personagens.var.generate', { n: '1' })).toBe('Gerar 1 variação');
    expect(i18n.t('proj.scenes')).toBe('{n} {n#cena|cenas}'); // sem parâmetros o texto sai como está
    expect(i18n.t('proj.scenes', {})).toBe('{n} {n#cena|cenas}');
    i18n.set('en');
    expect(i18n.t('proj.scenes', { n: 1 })).toBe('1 scene');
    expect(i18n.t('proj.scenes', { n: 2 })).toBe('2 scenes');
  });

  it('cai no português e depois na própria chave quando falta tradução', () => {
    const i18n = TestBed.inject(I18nService);
    i18n.set('en');
    (EN as Record<string, string>)['teste.so.pt'] = undefined as unknown as string;
    delete (EN as Record<string, string>)['teste.so.pt'];
    expect(i18n.t('chave.que.nao.existe')).toBe('chave.que.nao.existe');
  });

  it('lê o idioma guardado', () => {
    localStorage.setItem('fabulim.lang', 'en');
    expect(TestBed.inject(I18nService).lang()).toBe('en');
  });

  it('o pipe `t` traduz e reage à troca de idioma', () => {
    const pipe = TestBed.runInInjectionContext(() => new TPipe());
    const i18n = TestBed.inject(I18nService);
    expect(pipe.transform('nav.status')).toBe('Status');
    expect(pipe.transform('nav.config')).toBe('Configurações');
    i18n.set('en');
    expect(pipe.transform('nav.config')).toBe('Settings');
  });
});

describe('cobertura das traduções', () => {
  const RAIZ = join(process.cwd(), 'src', 'app'); // os testes rodam com a pasta frontend/ como diretório atual
  const arquivos = (dir: string): string[] =>
    readdirSync(dir).flatMap((nome) => {
      const caminho = join(dir, nome);
      if (statSync(caminho).isDirectory()) return arquivos(caminho);
      return /\.(ts|html)$/.test(nome) && !/\.spec\.ts$/.test(nome) && !/i18n[\\/](pt-br|en)[.\w]*\.ts$/.test(caminho) ? [caminho] : [];
    });

  const PREFIXOS = 'nav|app|topbar|theme|lang|toast|common|state|servicos|status|maquina|accel|bench|cap|feature|criar|fila|job|logs|config|notfound|modelos|viewer|tile|prompt|picker|imagem|personagens|clipes|proj|pkg';
  // Chaves montadas com concatenação, listadas aqui para o teste conferir também.
  const DINAMICAS = [
    ...['ok', 'warning', 'error', 'inactive'].map((s) => `state.${s}`),
    ...['ok', 'warning', 'error'].map((s) => `servicos.overall.${s}`),
    ...['available', 'slow', 'unavailable'].map((s) => `cap.state.${s}`),
    ...['queued', 'running', 'paused', 'done', 'failed', 'canceled'].map((s) => `job.status.${s}`),
    ...['cuda', 'rocm', 'directml', 'vulkan', 'metal', 'openvino'].map((s) => `accel.${s}`),
    ...['llm_ollama', 'image', 'cutout', 'tts', 'music', 'video'].map((s) => `bench.task.${s}`),
    ...['ok', 'skipped', 'error'].map((s) => `bench.status.${s}`),
    ...['integrated', 'discrete', 'unified'].map((s) => `maquina.gpu.${s}`),
    ...['demo.sleep', 'system.diagnostico', 'benchmark.calibracao', 'ferramentas.instalar'].map((s) => `fila.kind.${s}`),
    // os grupos da página Modelos vêm do catálogo do servidor (backend/app/ferramentas/catalogo.py)
    ...['ffmpeg', 'imagem', 'voz', 'recorte'].flatMap((g) => [`modelos.group.${g}`, `modelos.group.${g}.hint`]),
    // ferramentas de criação: chaves montadas na tela a partir de um valor (tipo, estado, etapa...)
    ...['personagem', 'enredo', 'imagem'].flatMap((t) => [`prompt.label.${t}`, `prompt.placeholder.${t}`, `prompt.type.${t}`]),
    ...['cenario', 'objeto', 'thumbnail', 'livre'].map((k) => `imagem.kind.${k}`),
    ...['16:9', '9:16', '1:1'].map((f) => `imagem.format.${f}`),
    ...['rascunho', 'padrao', 'alta'].map((q) => `imagem.quality.${q}`),
    ...['ready', 'cutout', 'choose'].map((s) => `personagens.status.${s}`),
    ...['principal', 'frente', 'tres_quartos', 'lado', 'feliz', 'triste', 'surpreso', 'sono', 'bravo'].map((s) => `personagens.slot.${s}`),
    ...['front', 'left', 'right'].map((f) => `personagens.facing.${f}`),
    ...['clipe_rapido', 'clipe_enviado', 'clipe_unido', 'clipe_reenquadrado', 'video_final'].map((r) => `clipes.role.${r}`),
    ...['9:16', '16:9', '1:1', '720p'].map((p) => `clipes.preset.${p}`),
    ...['corte', 'fade', 'suave'].map((t) => `clipes.transition.${t}`),
    ...['short', 'longo'].map((f) => `proj.format.${f}`),
    ...['enredo', 'roteiro', 'storyboard', 'animacao', 'audio', 'montagem', 'revisao'].map((e) => `proj.stage.${e}`),
    ...['ok', 'warning', 'error'].map((s) => `proj.review.status.${s}`),
    ...['aberto', 'medio', 'proximo'].map((f) => `proj.framing.${f}`),
    ...['neutro', 'feliz', 'triste', 'surpreso', 'sono', 'bravo'].map((e) => `proj.emotion.${e}`),
    ...['pop', 'boing', 'brilho', 'splash', 'whoosh', 'ding', 'passos', 'chuva'].map((s) => `proj.sfx.${s}`),
    ...['faltantes', 'regerar', 'variacoes'].map((m) => `proj.sb.mode.${m}`),
    ...['ia', 'simples', 'manual'].map((s) => `proj.review.meta.source.${s}`),
    ...['pt-BR', 'en'].flatMap((l) => [`proj.review.meta.lang.${l}`, `proj.lang.${l}`]),
    ...[
      'personagem.variacoes',
      'personagem.recortar',
      'personagem.folha',
      'personagem.voz_teste',
      'imagem.gerar',
      'prompt.interpretar',
      'projeto.roteiro',
      'projeto.storyboard',
      'projeto.animar',
      'projeto.audio',
      'projeto.montar',
      'projeto.miniaturas',
      'projeto.metadados',
      'projeto.versao_idioma',
      'clipe.rapido',
      'clipe.reenquadrar',
      'clipe.unir',
    ].map((k) => `fila.kind.${k}`),
  ];

  let cache: Set<string> | null = null; // varrer os arquivos é caro: faz uma vez só
  const usadas = (): Set<string> => {
    if (cache) return cache;
    const achadas = new Set<string>(DINAMICAS);
    const regex = new RegExp(`'((?:${PREFIXOS})\\.[A-Za-z0-9_.]*[A-Za-z0-9_])'`, 'g');
    for (const arquivo of arquivos(RAIZ)) {
      for (const m of readFileSync(arquivo, 'utf-8').matchAll(regex)) achadas.add(m[1]);
    }
    achadas.delete('job.updated'); // nome do evento SSE, não é tradução
    // cada etapa do caminho ("criar.step.x") tem a explicação (".text") e o botão (".go"), montados na tela por concatenação
    for (const chave of [...achadas].filter((k) => /^criar\.step\.[a-z]+$/.test(k))) {
      achadas.add(`${chave}.text`);
      achadas.add(`${chave}.go`);
    }
    cache = achadas;
    return achadas;
  };

  it('toda chave usada no código existe em português', () => {
    const faltam = [...usadas()].filter((k) => !(k in PT_BR));
    expect(faltam).toEqual([]);
  });

  it('toda chave usada no código existe em inglês', () => {
    const faltam = [...usadas()].filter((k) => !(k in EN));
    expect(faltam).toEqual([]);
  });

  it('inglês e português têm as mesmas chaves e os mesmos {marcadores}', () => {
    expect(Object.keys(EN).sort()).toEqual(Object.keys(PT_BR).sort());
    const marcadores = (t: string): string[] => [...new Set([...t.matchAll(/\{(\w+)(?:#[^|}]*\|[^}]*)?\}/g)].map((m) => m[1]))].sort();
    for (const chave of Object.keys(PT_BR)) {
      expect(marcadores(EN[chave]), chave).toEqual(marcadores(PT_BR[chave]));
    }
  });

  it('não há texto vazio nem chave sem uso (dicionário sem lixo)', () => {
    for (const [chave, texto] of Object.entries(PT_BR)) expect(texto.trim(), chave).not.toBe('');
    const inuteis = Object.keys(PT_BR).filter((k) => !usadas().has(k));
    expect(inuteis).toEqual([]);
  });
});
