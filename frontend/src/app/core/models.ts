// Tipos da API do backend (espelham backend/app/**). Chaves de estrutura em inglês; textos para o usuário em PT-BR.

export type ServiceState = 'ok' | 'warning' | 'error' | 'inactive';

export interface ServiceStatus {
  id: string;
  name: string;
  state: ServiceState;
  summary: string;
  detail: string | null;
  version: string | null;
  how_to_fix: string[];
  log_service: string | null;
}

export interface StatusReport {
  overall: ServiceState;
  services: ServiceStatus[];
  generated_at: string;
}

export type JobStatus = 'queued' | 'running' | 'paused' | 'done' | 'failed' | 'canceled';

export interface Job {
  id: string;
  kind: string;
  title: string;
  params: Record<string, unknown>;
  status: JobStatus;
  priority: number;
  position: number;
  progress: number;
  message: string;
  eta_seconds: number | null;
  result: Record<string, unknown> | null;
  error: string | null;
  heavy: boolean;
  attempts: number;
  cancel_requested: boolean;
  pause_requested: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
}

export interface JobLog {
  id: number;
  job_id: string;
  ts: string;
  level: string;
  message: string;
}

export type CapabilityState = 'available' | 'slow' | 'unavailable';

export interface Capability {
  id: string;
  name: string;
  section: string;
  state: CapabilityState;
  reason: string;
  eta: string | null;
  eta_measured: boolean;
}

export type ProfileLetter = 'A' | 'B' | 'C' | 'D';

export interface MachineProfile {
  letter: ProfileLetter;
  name: string;
  reasons: string[];
  warnings: string[];
  acceleration: string[];
  main_gpu: string | null;
  ai_memory_mb: number;
}

export interface GpuInfo {
  vendor: string;
  name: string;
  kind: 'integrated' | 'discrete' | 'unified';
  dedicated_mb: number | null;
  shared_mb: number | null;
  driver: string | null;
  gfx_arch: string | null;
}

export interface AccelerationInfo {
  available: boolean;
  detail?: string | null;
  version?: string | null;
  api_version?: string | null;
  candidate?: boolean;
  devices?: { name: string; type: string | null }[];
}

export interface ToolInfo {
  installed: boolean;
  version?: string | null;
  path?: string | null;
  server_active?: boolean;
  models?: { name: string; size_mb: number }[];
  logged_in?: boolean | null;
  auth_method?: string | null;
  subscription?: string | null;
  versions_available?: string[];
}

export interface HardwareInfo {
  os: { family: string; name: string; version: string; arch: string };
  system: {
    vendor: string;
    model: string;
    marketing_name: string | null;
    is_laptop: boolean;
    battery: { present: boolean; percent: number | null; on_ac: boolean | null };
    power_plan: string | null;
  };
  cpu: {
    model: string;
    cores: number;
    threads: number;
    max_mhz: number | null;
    features: { avx: boolean; avx2: boolean; avx512: boolean; sse42: boolean; neon: boolean };
    npu: { present: boolean; name: string | null };
  };
  memory: { ram_total_mb: number; ram_free_mb: number };
  disk: { path: string; drive: string | null; total_mb: number; free_mb: number; kind: string };
  gpus: GpuInfo[];
  acceleration: Record<string, AccelerationInfo>;
  tools: Record<string, ToolInfo>;
}

export interface PendingItem {
  item: string;
  state: string;
  action: string;
}

export interface MachineSnapshot {
  exists: boolean;
  valid: boolean;
  errors: string[];
  collected_at?: string;
  full_collected_at?: string;
  mode?: 'full' | 'light';
  changed?: boolean;
  profile?: MachineProfile;
  hardware?: HardwareInfo;
  pending?: PendingItem[];
  capabilities: Capability[];
  measurements: Record<string, unknown>;
}

export interface BenchmarkResult {
  task: string;
  status: 'ok' | 'skipped' | 'error';
  model: string | null;
  seconds: number | null;
  metrics: Record<string, unknown>;
  detail: string | null;
  measured_at: string;
}

export interface BenchmarkReport {
  results: BenchmarkResult[];
  measurements: Record<string, unknown>;
}

export interface LogEntry {
  ts: string;
  level: string;
  service: string;
  msg: string;
  job_id?: string;
}

export interface AppMeta {
  name: string;
  version: string;
  host: string;
  port: number;
  data_dir: string;
  models_dir: string;
  tools_dir: string;
}

/** Um programa ou modelo do catálogo (ffmpeg, motor de imagens, voz...) com o estado de instalação. */
export interface ToolItem {
  id: string;
  name: string;
  purpose: string;
  group: string;
  license: string;
  installed: boolean;
  /** Espaço no disco quando instalado; antes disso, o tamanho aproximado do download (veja `size_estimated`). */
  size_bytes: number | null;
  size_estimated: boolean;
  job_id: string | null;
}

export interface ToolsReport {
  items: ToolItem[];
  tools_dir: string;
  models_dir: string;
}

// --- biblioteca de mídias ---------------------------------------------------------------------------------------------

export type MediaKind = 'imagem' | 'video' | 'audio' | 'legenda';

/** Uma mídia da biblioteca (imagem, vídeo, áudio ou legenda). A URL sempre é do servidor local: a interface nunca vê caminhos de disco. */
export interface Media {
  id: string;
  kind: MediaKind;
  role: string;
  url: string;
  thumb_url: string | null;
  format: string | null;
  width: number | null;
  height: number | null;
  duration_s: number | null;
  size_bytes: number | null;
  owner_type: string | null;
  owner_id: string | null;
  parent_id: string | null;
  prompt: string | null;
  technical_prompt: string | null;
  negative_prompt: string | null;
  style: string | null;
  seed: number | null;
  model: string | null;
  metadata: Record<string, unknown>;
  job_id: string | null;
  created_at: string;
}

export interface MediaList {
  items: Media[];
  total: number;
}

// --- prompts ---------------------------------------------------------------------------------------------------------

export type Style = '2D' | '3D';
export type PromptType = 'personagem' | 'enredo' | 'imagem';

export interface CharacterForm {
  name: string;
  style: Style;
  species: string;
  apparent_age: string;
  appearance: string;
  clothing: string;
  palette: string;
  personality: string;
  voice: string;
  expressions: string;
  notes: string;
}

export interface StoryForm {
  title: string;
  format: 'short' | 'longo';
  target_duration: string;
  language: 'pt-BR' | 'en';
  style: Style;
  characters: string[];
  theme: string;
  settings: string;
  story: string;
  music: string;
  notes: string;
}

export type ImageKind = 'cenario' | 'objeto' | 'thumbnail' | 'livre';
export type ImageFormat = '16:9' | '9:16' | '1:1';

export interface ImageForm {
  kind: ImageKind;
  style: Style;
  format: ImageFormat;
  characters: string[];
  description: string;
  notes: string;
}

export interface Blocked {
  reason: string;
  [key: string]: unknown;
}

export interface ParsedPrompt<F> {
  type: PromptType;
  form: F;
  source: 'estruturado' | 'ia';
  missing: string[];
  warnings: string[];
}

/** Resposta de `POST /api/prompts/parse`: pronta na hora (formato estruturado) ou um job do modelo local (texto livre). */
export interface ParseResponse<F = Record<string, unknown>> {
  status: 'done' | 'queued' | 'blocked';
  detected_type: PromptType;
  result?: ParsedPrompt<F> | null;
  blocked?: Blocked | null;
  job?: Job;
}

export interface PromptHistoryItem {
  id: number;
  type: PromptType;
  text: string;
  created_at: string;
}

// --- personagens ----------------------------------------------------------------------------------------------------

export interface VoiceSetting {
  id: string;
  speed: number;
  pitch: number;
  language?: string;
}

export interface VoiceOption {
  id: string;
  nome: string;
  lingua: string;
}

export interface Character {
  id: string;
  name: string;
  style: Style;
  form: CharacterForm;
  original_prompt: string;
  technical_prompt: string;
  voice: VoiceSetting;
  state: string;
  main_image_id: string | null;
  main_image_url: string | null;
  version: number;
  origin: string;
  origin_id: string | null;
  created_at: string;
  updated_at: string;
  cutout_slots: string[];
  has_cutout: boolean;
}

export interface SheetSlot {
  slot: string;
  image: Media | null;
  cutout: Media | null;
}

export interface CharacterDetail {
  character: Character;
  variations: Media[];
  uploads: Media[];
  sheet: SheetSlot[];
  voice_tests: Media[];
  versions: { version: number; images: number }[];
}

export interface CharacterWithJob {
  character: Character;
  job: Job | null;
}

export interface Estimate {
  width: number;
  height: number;
  total_seconds: number;
  total_label: string;
  per_image_seconds?: number;
  per_item_seconds?: number;
}

export interface ResolvedNames {
  found: Character[];
  missing: string[];
  other_style: { name: string; available_style: Style; character: Character }[];
}

// --- clipes ---------------------------------------------------------------------------------------------------------

export interface Clip extends Media {
  project_title: string | null;
  variants: string[];
}

export interface ClipList {
  items: Clip[];
  total: number;
}

// --- projetos -------------------------------------------------------------------------------------------------------

export type StageId = 'enredo' | 'roteiro' | 'storyboard' | 'animacao' | 'audio' | 'montagem' | 'revisao';

export interface Stage {
  id: StageId;
  name: string;
  approved: boolean;
  available: boolean;
  ready: boolean;
  missing: string;
  scenes_approved?: number;
  scenes_total?: number;
}

export interface Stages {
  stages: Stage[];
  current: StageId;
}

export interface MusicSettings {
  enabled?: boolean;
  style?: string;
  seed?: number;
  volume?: number;
}

export interface Project {
  id: string;
  title: string;
  format: 'short' | 'longo';
  aspect: string;
  language: 'pt-BR' | 'en';
  style: Style;
  target_duration_s: number;
  story: Partial<StoryForm> & { original_prompt?: string };
  character_ids: string[];
  stage: StageId;
  approvals: Partial<Record<StageId, boolean>>;
  music: MusicSettings;
  settings: Record<string, unknown>;
  origin_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectSummary extends Omit<Project, 'story'> {
  scene_count: number;
  thumb_url: string | null;
  has_final: boolean;
  characters: string[];
}

export interface DialogueLine {
  character_id: string | null;
  text: string;
}

export type Framing = 'aberto' | 'medio' | 'proximo';
export type Emotion = 'neutro' | 'feliz' | 'triste' | 'surpreso' | 'sono' | 'bravo';

export interface LayoutItem {
  personagem_id: string;
  x: number;
  base_y: number;
  altura: number;
  espelhar: boolean;
  /** `null` = automático (o servidor escolhe pela emoção, pela ação e pelo texto da cena) */
  pose: string | null;
  acao: string | null;
  entrada: string | null;
}

export interface SceneData {
  title: string;
  duration_s: number;
  visual: string;
  action: string;
  setting: string;
  framing: Framing;
  emotion: Emotion;
  characters: string[];
  narration: string;
  dialogue: DialogueLine[];
  lyrics: string;
  sfx: string[];
  camera: string;
  suggestion: boolean;
  suggestion_notes: string;
  layout: LayoutItem[] | null;
  background: { media_id: string; seed: number | null; prompt: string; quality: string } | null;
  candidates: string[];
  keyframe_media_id: string | null;
  clip: { media_id: string; render_hash: string; quality: string; duration_s: number } | null;
  timeline: Record<string, unknown> | null;
  approved: Partial<Record<'roteiro' | 'storyboard' | 'animacao', boolean>>;
}

export interface Scene {
  id: string;
  project_id: string;
  order: number;
  data: SceneData;
  status: string;
  version: number;
  keyframe: Media | null;
  background_media: Media | null;
  candidate_media: Media[];
  clip_media: Media | null;
  character_names: string[];
  layout: LayoutItem[];
  effective_duration_s: number;
}

export interface ChecklistItem {
  id: string;
  label: string;
  status: 'ok' | 'warning' | 'error';
  detail: string;
}

/** Título, descrição e tags de um idioma (os limites são os do YouTube). */
export interface MetadataText {
  title: string;
  description: string;
  tags: string[];
}

export type MetadataLanguage = 'pt-BR' | 'en';

/** Os textos do YouTube do projeto nos dois idiomas, e de onde vieram (`ia`, `simples` ou `manual`). */
export interface ProjectMetadata {
  'pt-BR': MetadataText;
  en: MetadataText;
  source?: string;
  generated_at?: string;
}

/** O que a fila noturna faria com um projeto. */
export interface NightItem {
  project_id: string;
  title: string;
  stage: string;
  stage_label: string;
  kind: string;
  blocked_by: string | null;
}

export interface NightResult {
  queued: Job[];
  skipped: NightItem[];
}

/** O que a importação de um pacote .fabulim fez (e os avisos do que muda nesta máquina). */
export interface ImportReport {
  kind: 'project' | 'characters';
  project_id: string | null;
  characters: { id: string; name: string; renamed_from: string | null }[];
  scenes: number;
  media: number;
  warnings: string[];
  project: ProjectSummary | null;
  character_list: Character[];
}

export interface ProjectFiles {
  final: Media | null;
  subtitles: Media | null;
  mix: Media | null;
  music: Media | null;
  thumbnails: Media[];
}

export interface StyleWarning {
  character_id: string;
  name: string;
  character_style: Style;
  project_style: Style;
  message: string;
}

export interface ProjectDetail {
  project: Project;
  scenes: Scene[];
  characters: Character[];
  missing_character_ids: string[];
  style_warnings: StyleWarning[];
  stages: Stages;
  files: ProjectFiles;
  metadata: ProjectMetadata | null;
  quality: Record<string, unknown> | null;
  active_jobs: Job[];
  variants: { id: string; title: string; language: string; format: string; stage: string }[];
}

export interface ProjectOptions {
  actions: string[];
  entrances: string[];
  cameras: string[];
  action_labels: Record<string, string>;
  camera_labels: Record<string, string>;
  music_styles: { id: string; label: string; bpm: number }[];
  transitions: { id: string; seconds: number }[];
  voices: Record<string, VoiceOption[]>;
}

export interface SceneResponse {
  scene: Scene;
  stages: Stages;
  warning: string | null;
}

export interface SceneVersion {
  version: number;
  data: SceneData;
  reason: string;
  created_at: string;
}

export interface Review {
  checklist: ChecklistItem[];
  files: ProjectFiles;
  metadata: ProjectMetadata | null;
  quality: Record<string, unknown> | null;
  reminder: string;
}

export interface CreatedProject {
  project: Project;
  missing_characters: string[];
  style_warnings: StyleWarning[];
}
