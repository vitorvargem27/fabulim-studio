import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { EnvironmentProviders, Provider } from '@angular/core';
import { provideRouter, Routes } from '@angular/router';

import { Character, Job, MachineSnapshot, Media, Project, ProjectDetail, ProjectOptions, Scene, SceneData, StageId, Stages, StatusReport } from '../app/core/models';

/** Dados de exemplo usados pelos testes: espelham o que o backend devolve para o ThinkPad (perfil C). */
export const SNAPSHOT_C: MachineSnapshot = {
  exists: true,
  valid: true,
  errors: [],
  collected_at: '2026-09-29T00:04:31-03:00',
  full_collected_at: '2026-09-29T00:02:15-03:00',
  mode: 'light',
  changed: false,
  profile: {
    letter: 'C',
    name: 'Notebook ou GPU integrada',
    reasons: ['RAM de 31,7 GB (mínimo de 16 GB atendido)', 'sem VRAM dedicada: modelos usam a CPU e a memória compartilhada'],
    warnings: ['Espaço apertado (61,2 GB livres)'],
    acceleration: ['CPU com AVX-512: linha de base confiável', 'Vulkan na GPU integrada: medir'],
    main_gpu: 'Intel(R) Iris(R) Xe Graphics',
    ai_memory_mb: 24283,
  },
  hardware: {
    os: { family: 'windows', name: 'Microsoft Windows 11 Pro', version: '10.0.26200', arch: 'x64' },
    system: {
      vendor: 'LENOVO',
      model: '20W1SGSV00',
      marketing_name: 'ThinkPad T14 Gen 2i',
      is_laptop: true,
      battery: { present: true, percent: 100, on_ac: true },
      power_plan: 'Equilibrado',
    },
    cpu: {
      model: '11th Gen Intel(R) Core(TM) i7-1185G7',
      cores: 4,
      threads: 8,
      max_mhz: 2995,
      features: { avx: true, avx2: true, avx512: true, sse42: true, neon: false },
      npu: { present: false, name: null },
    },
    memory: { ram_total_mb: 32475, ram_free_mb: 10800 },
    disk: { path: 'C:\\video_create_ai', drive: 'C:', total_mb: 486304, free_mb: 62722, kind: 'SSD (NVMe)' },
    gpus: [
      {
        vendor: 'intel',
        name: 'Intel(R) Iris(R) Xe Graphics',
        kind: 'integrated',
        dedicated_mb: 128,
        shared_mb: 16237,
        driver: '32.0.101.7085',
        gfx_arch: null,
      },
    ],
    acceleration: {
      cuda: { available: false },
      rocm: { available: false },
      directml: { available: true, detail: 'DirectML.dll presente' },
      vulkan: { available: true, api_version: '1.4.313', devices: [{ name: 'Intel(R) Iris(R) Xe Graphics', type: 'integrated_gpu' }] },
      metal: { available: false },
      openvino: { available: false, candidate: true },
    },
    tools: {},
  },
  pending: [{ item: 'ffmpeg', state: 'ausente', action: 'Instalar ffmpeg (pede a sua autorização)' }],
  capabilities: [
    { id: 'llm_local', name: 'LLM local (roteiro, enredo, prompt técnico)', section: '4', state: 'slow', reason: 'Roda na CPU.', eta: '≈ 2,9 min por roteiro', eta_measured: true },
    { id: 'imagem', name: 'Gerar imagens', section: '7.1', state: 'slow', reason: 'Sem GPU dedicada.', eta: '2 a 8 min por imagem', eta_measured: false },
    { id: 'recorte', name: 'Recorte de fundo', section: '7.1', state: 'available', reason: 'Segmentação leve.', eta: null, eta_measured: false },
    { id: 'animacao_ia', name: 'Animação por IA', section: '3.2', state: 'unavailable', reason: 'Precisa de uma GPU dedicada.', eta: null, eta_measured: false },
    { id: 'animacao_cena', name: 'Animação de cena (por código)', section: '3.2', state: 'unavailable', reason: 'Precisa do ffmpeg.', eta: null, eta_measured: false },
    { id: 'voz', name: 'Voz de personagens', section: '7.8', state: 'available', reason: 'Kokoro.', eta: null, eta_measured: false },
  ],
  measurements: {},
};

export const STATUS_REPORT: StatusReport = {
  overall: 'warning',
  generated_at: '2026-09-29T10:17:00+00:00',
  services: [
    { id: 'backend', name: 'Servidor do Fabulim', state: 'ok', summary: 'Escutando em 127.0.0.1:8765', detail: 'No ar há 3 min.', version: '0.1.0', how_to_fix: [], log_service: 'app' },
    { id: 'ollama', name: 'LLM local (Ollama)', state: 'error', summary: 'Não respondeu', detail: 'connection refused', version: null, how_to_fix: ['Abra o aplicativo Ollama.', 'Ou rode `ollama serve`.'], log_service: null },
    { id: 'claude', name: 'Claude (opcional)', state: 'ok', summary: 'Conectado', detail: 'Login claude.ai, plano pro.', version: '2.1.284', how_to_fix: [], log_service: null },
    { id: 'ffmpeg', name: 'ffmpeg (montagem de vídeo)', state: 'warning', summary: 'Ainda não instalado', detail: null, version: null, how_to_fix: ['Instale o ffmpeg.'], log_service: null },
    { id: 'music_engine', name: 'Música (ACE-Step)', state: 'inactive', summary: 'Ainda não disponível', detail: 'O gerador de música ainda não faz parte da lista de Modelos.', version: null, how_to_fix: [], log_service: null },
  ],
};

let seq = 0;
export function makeJob(partial: Partial<Job> = {}): Job {
  seq += 1;
  return {
    id: partial.id ?? seq.toString(16).padStart(32, '0'),
    kind: 'demo.sleep',
    title: `Job ${seq}`,
    params: {},
    status: 'queued',
    priority: 0,
    position: seq,
    progress: 0,
    message: '',
    eta_seconds: null,
    result: null,
    error: null,
    heavy: true,
    attempts: 0,
    cancel_requested: false,
    pause_requested: false,
    created_at: '2026-09-29T10:00:00.000+00:00',
    started_at: null,
    finished_at: null,
    updated_at: '2026-09-29T10:00:00.000+00:00',
    ...partial,
  };
}

/** EventSource falso: o teste dispara `snapshot` e `job.updated` à mão. */
export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private readonly listeners = new Map<string, ((e: MessageEvent<string>) => void)[]>();

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (e: MessageEvent<string>) => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, data: unknown): void {
    for (const listener of this.listeners.get(type) ?? []) {
      listener(new MessageEvent(type, { data: JSON.stringify(data) }));
    }
  }

  static reset(): void {
    FakeEventSource.instances = [];
  }
}

export function installFakeEventSource(): void {
  FakeEventSource.reset();
  (globalThis as unknown as { EventSource: typeof FakeEventSource }).EventSource = FakeEventSource;
}

export function uninstallFakeEventSource(): void {
  delete (globalThis as unknown as { EventSource?: unknown }).EventSource;
}

export function provideTestHttp(routes: Routes = []): (Provider | EnvironmentProviders)[] {
  return [provideHttpClient(), provideHttpClientTesting(), provideRouter(routes)];
}

// --- dados de exemplo das ferramentas de criação --------------------------------------------------------------------------

let mediaSeq = 0;
export function makeMedia(partial: Partial<Media> = {}): Media {
  mediaSeq += 1;
  const id = partial.id ?? mediaSeq.toString(16).padStart(32, 'e');
  return {
    id,
    kind: 'imagem',
    role: 'variacao',
    url: `/api/media/${id}`,
    thumb_url: `/api/media/${id}/thumb`,
    format: 'png',
    width: 512,
    height: 512,
    duration_s: null,
    size_bytes: 120_000,
    owner_type: null,
    owner_id: null,
    parent_id: null,
    prompt: null,
    technical_prompt: null,
    negative_prompt: null,
    style: '2D',
    seed: 7,
    model: 'FLUX.2 klein 4B',
    metadata: {},
    job_id: null,
    created_at: '2026-09-30T10:00:00Z',
    ...partial,
  };
}

let characterSeq = 0;
export function makeCharacter(partial: Partial<Character> = {}): Character {
  characterSeq += 1;
  const id = partial.id ?? characterSeq.toString(16).padStart(32, 'c');
  const name = partial.name ?? 'Lila';
  return {
    id,
    name,
    style: '2D',
    form: {
      name,
      style: '2D',
      species: 'coelhinha',
      apparent_age: '4 anos',
      appearance: 'pelo lilás',
      clothing: 'vestido amarelo',
      palette: 'lilás e amarelo',
      personality: 'curiosa',
      voice: 'aguda e doce',
      expressions: 'feliz, triste',
      notes: '',
    },
    original_prompt: '',
    technical_prompt: 'flat 2D cartoon',
    voice: { id: 'pf_dora', speed: 1, pitch: 1 },
    state: 'pronto',
    main_image_id: 'a'.repeat(32),
    main_image_url: `/api/media/${'a'.repeat(32)}/thumb`,
    version: 1,
    origin: 'prompt',
    origin_id: null,
    created_at: '2026-09-30T10:00:00Z',
    updated_at: '2026-09-30T10:00:00Z',
    cutout_slots: ['principal'],
    has_cutout: true,
    ...partial,
  };
}

export function makeSceneData(partial: Partial<SceneData> = {}): SceneData {
  return {
    title: 'O jardim',
    duration_s: 5,
    visual: 'um jardim florido',
    action: 'brinca',
    setting: '',
    framing: 'medio',
    emotion: 'feliz',
    characters: [],
    narration: 'Era uma vez um jardim.',
    dialogue: [],
    lyrics: '',
    sfx: [],
    camera: 'parada',
    suggestion: false,
    suggestion_notes: '',
    layout: null,
    background: null,
    candidates: [],
    keyframe_media_id: null,
    clip: null,
    timeline: null,
    approved: {},
    ...partial,
  };
}

let sceneSeq = 0;
export function makeScene(partial: Omit<Partial<Scene>, 'data'> & { data?: Partial<SceneData> } = {}): Scene {
  sceneSeq += 1;
  const { data, ...rest } = partial;
  return {
    id: partial.id ?? sceneSeq.toString(16).padStart(32, 's'),
    project_id: 'p'.repeat(32),
    order: sceneSeq,
    data: makeSceneData(data),
    status: 'pendente',
    version: 1,
    keyframe: null,
    background_media: null,
    candidate_media: [],
    clip_media: null,
    character_names: [],
    layout: [],
    effective_duration_s: 5,
    ...rest,
  };
}

export function makeStages(current: StageId = 'enredo', approved: StageId[] = []): Stages {
  const order: StageId[] = ['enredo', 'roteiro', 'storyboard', 'animacao', 'audio', 'montagem', 'revisao'];
  return {
    current,
    stages: order.map((id, i) => ({
      id,
      name: id,
      approved: approved.includes(id),
      available: i === 0 || approved.includes(order[i - 1]),
      ready: true,
      missing: '',
    })),
  };
}

export function makeProject(partial: Partial<Project> = {}): Project {
  return {
    id: 'p'.repeat(32),
    title: 'A chuva do jardim',
    format: 'short',
    aspect: '9:16',
    language: 'pt-BR',
    style: '2D',
    target_duration_s: 30,
    story: { story: 'Lila brinca no jardim.', characters: ['Lila'] },
    character_ids: [],
    stage: 'enredo',
    approvals: {},
    music: {},
    settings: {},
    origin_id: null,
    created_at: '2026-09-30T10:00:00Z',
    updated_at: '2026-09-30T10:00:00Z',
    ...partial,
  };
}

export function makeDetail(partial: Partial<ProjectDetail> = {}): ProjectDetail {
  return {
    project: makeProject(),
    scenes: [],
    characters: [],
    missing_character_ids: [],
    style_warnings: [],
    stages: makeStages(),
    files: { final: null, subtitles: null, mix: null, music: null, thumbnails: [] },
    metadata: null,
    quality: null,
    active_jobs: [],
    variants: [],
    ...partial,
  };
}

export const OPTIONS: ProjectOptions = {
  actions: ['respirar', 'pular'],
  entrances: ['nenhuma', 'deslizar'],
  cameras: ['parada', 'zoom_in'],
  action_labels: { respirar: 'Respirar', pular: 'Pular' },
  camera_labels: { parada: 'Parada', zoom_in: 'Zoom' },
  music_styles: [
    { id: 'alegre', label: 'Alegre', bpm: 110 },
    { id: 'calma', label: 'Calma', bpm: 80 },
  ],
  transitions: [{ id: 'corte', seconds: 0 }],
  voices: { 'pt-BR': [{ id: 'pf_dora', nome: 'Dora (feminina)', lingua: 'pt-br' }], en: [{ id: 'am_adam', nome: 'Adam', lingua: 'en-us' }] },
};
