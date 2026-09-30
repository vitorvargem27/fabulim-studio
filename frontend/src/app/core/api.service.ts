import { HttpClient, HttpEvent } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  AppMeta,
  BenchmarkReport,
  Character,
  CharacterDetail,
  CharacterForm,
  CharacterWithJob,
  Clip,
  ClipList,
  CreatedProject,
  Estimate,
  ImageForm,
  ImageFormat,
  ImportReport,
  Job,
  JobLog,
  LogEntry,
  MachineSnapshot,
  Media,
  MediaKind,
  MediaList,
  MetadataLanguage,
  MetadataText,
  NightItem,
  NightResult,
  ParseResponse,
  Project,
  ProjectDetail,
  ProjectOptions,
  ProjectSummary,
  PromptHistoryItem,
  PromptType,
  ResolvedNames,
  Review,
  SceneData,
  SceneResponse,
  SceneVersion,
  Stages,
  StatusReport,
  StoryForm,
  Style,
  ToolsReport,
  VoiceOption,
  VoiceSetting,
  Blocked,
} from './models';

export interface LogQuery {
  service?: string;
  level?: string;
  limit?: number;
}

export interface MediaQuery {
  kind?: MediaKind;
  role?: string[];
  ownerType?: string;
  ownerId?: string;
  parentId?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

export type Quality = 'rascunho' | 'padrao' | 'alta';

export interface ImageRequest {
  form: ImageForm;
  technical_prompt?: string | null;
  quality: Quality;
  count: number;
  seed?: number | null;
  character_ids: string[];
  based_on?: string | null;
}

export interface StoryboardRequest {
  scene_ids?: string[] | null;
  mode: 'faltantes' | 'regerar' | 'variacoes';
  variations?: number;
  quality?: Quality;
  seed?: number | null;
}

export interface ProjectPatch {
  title?: string;
  target_duration_s?: number;
  character_ids?: string[];
  music?: Record<string, unknown>;
  settings?: Record<string, unknown>;
  story?: Record<string, unknown>;
}

export type Transition = 'corte' | 'fade' | 'suave';
export type SizePreset = '9:16' | '16:9' | '1:1' | '720p';

/** Remove o que é `undefined`/`null`/vazio para não mandar parâmetros sem valor na URL. */
export function cleanParams(params: Record<string, string | number | boolean | readonly string[] | null | undefined>): Record<string, string | number | boolean | readonly string[]> {
  const out: Record<string, string | number | boolean | readonly string[]> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value) && value.length === 0) continue;
    out[key] = value as string | number | boolean | readonly string[];
  }
  return out;
}

/** Cliente HTTP do backend. Caminhos relativos: em dev o proxy do `ng serve` leva /api ao 127.0.0.1:8765. */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  meta(): Observable<AppMeta> {
    return this.http.get<AppMeta>('/api/meta');
  }

  status(): Observable<StatusReport> {
    return this.http.get<StatusReport>('/api/status');
  }

  machine(): Observable<MachineSnapshot> {
    return this.http.get<MachineSnapshot>('/api/machine');
  }

  startDiagnostic(light = false): Observable<Job> {
    return this.http.post<Job>('/api/machine/diagnostic', null, { params: { light: String(light) } });
  }

  benchmark(): Observable<BenchmarkReport> {
    return this.http.get<BenchmarkReport>('/api/benchmark');
  }

  runBenchmark(): Observable<Job> {
    return this.http.post<Job>('/api/benchmark/run', null);
  }

  tools(): Observable<ToolsReport> {
    return this.http.get<ToolsReport>('/api/tools');
  }

  installTool(id: string): Observable<Job> {
    return this.http.post<Job>(`/api/tools/${id}/install`, null);
  }

  jobs(): Observable<Job[]> {
    return this.http.get<Job[]>('/api/jobs');
  }

  createJob(kind: string, params: Record<string, unknown> = {}, title?: string): Observable<Job> {
    return this.http.post<Job>('/api/jobs', { kind, params, ...(title ? { title } : {}) });
  }

  jobAction(id: string, action: 'pause' | 'resume' | 'cancel'): Observable<Job> {
    return this.http.post<Job>(`/api/jobs/${id}/${action}`, null);
  }

  reorder(ids: string[]): Observable<Job[]> {
    return this.http.post<Job[]>('/api/jobs/reorder', { ids });
  }

  clearFinished(): Observable<{ removed: number }> {
    return this.http.delete<{ removed: number }>('/api/jobs/finished');
  }

  jobLogs(id: string): Observable<JobLog[]> {
    return this.http.get<JobLog[]>(`/api/jobs/${id}/logs`);
  }

  logs(query: LogQuery = {}): Observable<LogEntry[]> {
    const params: Record<string, string> = {};
    if (query.service) params['service'] = query.service;
    if (query.level) params['level'] = query.level;
    params['limit'] = String(query.limit ?? 200);
    return this.http.get<LogEntry[]>('/api/logs', { params });
  }

  // --- biblioteca de mídias ----------------------------------------------------------------------------------------------

  media(query: MediaQuery = {}): Observable<MediaList> {
    const params = cleanParams({
      kind: query.kind,
      role: query.role,
      owner_type: query.ownerType,
      owner_id: query.ownerId,
      parent_id: query.parentId,
      q: query.q,
      limit: query.limit,
      offset: query.offset,
    });
    return this.http.get<MediaList>('/api/media', { params });
  }

  mediaInfo(id: string): Observable<Media> {
    return this.http.get<Media>(`/api/media/${id}/info`);
  }

  deleteMedia(id: string): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`/api/media/${id}`);
  }

  uploadImage(file: File, role = 'upload'): Observable<Media> {
    return this.http.post<Media>('/api/media/upload', file, { params: { name: file.name, role } });
  }

  // --- prompts ----------------------------------------------------------------------------------------------------------

  parsePrompt(text: string, type?: PromptType): Observable<ParseResponse> {
    return this.http.post<ParseResponse>('/api/prompts/parse', { text, ...(type ? { type } : {}) });
  }

  checkTexts(texts: string[]): Observable<{ ok: boolean; blocked: Blocked | null }> {
    return this.http.post<{ ok: boolean; blocked: Blocked | null }>('/api/prompts/check', { texts });
  }

  promptHistory(type?: PromptType, limit = 30): Observable<PromptHistoryItem[]> {
    return this.http.get<PromptHistoryItem[]>('/api/prompts/history', { params: cleanParams({ type, limit }) });
  }

  deleteFromHistory(id: number): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`/api/prompts/history/${id}`);
  }

  clearHistory(type?: PromptType): Observable<{ removed: number }> {
    return this.http.delete<{ removed: number }>('/api/prompts/history', { params: cleanParams({ type }) });
  }

  // --- gerar imagem -----------------------------------------------------------------------------------------------------

  imageEstimate(format: ImageFormat, quality: Quality, count: number, references: number): Observable<Estimate> {
    return this.http.get<Estimate>('/api/images/estimate', { params: { format, quality, count, references } });
  }

  technicalPrompt(
    form: ImageForm,
    characterIds: string[],
    basedOn: string | null,
  ): Observable<{ technical_prompt: string; negative_prompt: string }> {
    return this.http.post<{ technical_prompt: string; negative_prompt: string }>('/api/images/technical-prompt', {
      form,
      character_ids: characterIds,
      ...(basedOn ? { based_on: basedOn } : {}),
    });
  }

  generateImage(request: ImageRequest): Observable<Job> {
    return this.http.post<Job>('/api/images', request);
  }

  // --- personagens -----------------------------------------------------------------------------------------------------

  characters(q?: string, style?: Style): Observable<{ items: Character[]; total: number }> {
    return this.http.get<{ items: Character[]; total: number }>('/api/characters', { params: cleanParams({ q, style }) });
  }

  character(id: string): Observable<CharacterDetail> {
    return this.http.get<CharacterDetail>(`/api/characters/${id}`);
  }

  characterVoices(): Observable<{ voices: Record<string, VoiceOption[]> }> {
    return this.http.get<{ voices: Record<string, VoiceOption[]> }>('/api/characters/voices');
  }

  characterEstimate(kind: 'variations' | 'conversion' | 'sheet' | 'cutout', count: number, quality: 'rascunho' | 'padrao'): Observable<Estimate> {
    return this.http.get<Estimate>('/api/characters/estimate', { params: { kind, count, quality } });
  }

  resolveNames(names: string[], style?: Style): Observable<ResolvedNames> {
    return this.http.post<ResolvedNames>('/api/characters/resolve', { names, ...(style ? { style } : {}) });
  }

  createCharacter(form: CharacterForm, originalPrompt = ''): Observable<Character> {
    return this.http.post<Character>('/api/characters', { form, original_prompt: originalPrompt });
  }

  uploadCharacter(file: File, name: string, style: Style, rights: boolean): Observable<CharacterWithJob> {
    return this.http.post<CharacterWithJob>('/api/characters/upload', file, {
      params: { name, style, rights, file_name: file.name },
    });
  }

  updateCharacter(id: string, change: { form?: CharacterForm; technical_prompt?: string }): Observable<Character> {
    return this.http.patch<Character>(`/api/characters/${id}`, change);
  }

  deleteCharacter(id: string): Observable<{ deleted: boolean; media_removed: number }> {
    return this.http.delete<{ deleted: boolean; media_removed: number }>(`/api/characters/${id}`);
  }

  generateVariations(
    id: string,
    request: { count: number; quality: 'rascunho' | 'padrao'; seed?: number | null; technical_prompt?: string | null },
  ): Observable<Job> {
    return this.http.post<Job>(`/api/characters/${id}/variations`, request);
  }

  chooseVariation(id: string, mediaId: string): Observable<CharacterWithJob> {
    return this.http.post<CharacterWithJob>(`/api/characters/${id}/choose`, { media_id: mediaId });
  }

  generateSheet(id: string, slots: string[], quality: 'rascunho' | 'padrao', seed?: number | null): Observable<Job> {
    return this.http.post<Job>(`/api/characters/${id}/sheet`, { slots, quality, ...(seed != null ? { seed } : {}) });
  }

  /** Para onde o recorte olha (a animação vira o personagem para o centro da cena). */
  setFacing(id: string, mediaId: string, facing: 'front' | 'left' | 'right'): Observable<Media> {
    return this.http.put<Media>(`/api/characters/${id}/cutouts/${mediaId}/facing`, { facing });
  }

  setVoice(id: string, voice: VoiceSetting): Observable<Character> {
    return this.http.put<Character>(`/api/characters/${id}/voice`, { id: voice.id, speed: voice.speed, pitch: voice.pitch });
  }

  testVoice(id: string, text: string, voice?: VoiceSetting): Observable<Job> {
    return this.http.post<Job>(`/api/characters/${id}/voice-test`, {
      text,
      ...(voice ? { voice: { id: voice.id, speed: voice.speed, pitch: voice.pitch } } : {}),
    });
  }

  convertCharacter(id: string, count: number, quality: 'rascunho' | 'padrao'): Observable<CharacterWithJob> {
    return this.http.post<CharacterWithJob>(`/api/characters/${id}/convert`, { count, quality });
  }

  // --- clipes ---------------------------------------------------------------------------------------------------------

  clips(query: { role?: string[]; q?: string; limit?: number; offset?: number } = {}): Observable<ClipList> {
    return this.http.get<ClipList>('/api/clips', { params: cleanParams({ role: query.role, q: query.q, limit: query.limit, offset: query.offset }) });
  }

  quickClip(request: {
    character_id: string;
    prompt: string;
    duration_s: number;
    format: '16:9' | '9:16';
    quality: 'rascunho' | 'padrao';
    seed?: number | null;
  }): Observable<Job> {
    return this.http.post<Job>('/api/clips/quick', request);
  }

  /** Envia o vídeo em corpo cru, com eventos de progresso (vídeos podem ter centenas de MB). */
  uploadClip(file: File, rights: boolean): Observable<HttpEvent<Clip>> {
    return this.http.post<Clip>('/api/clips/upload', file, {
      params: { name: file.name, rights },
      observe: 'events',
      reportProgress: true,
    });
  }

  joinClips(clipIds: string[], transition: Transition, size: 'auto' | SizePreset): Observable<Job> {
    return this.http.post<Job>('/api/clips/join', { clip_ids: clipIds, transition, size });
  }

  reframeClip(id: string, preset: SizePreset, mode: 'fit' | 'crop'): Observable<Job> {
    return this.http.post<Job>(`/api/clips/${id}/reframe`, { preset, mode });
  }

  continueClip(
    id: string,
    request: { prompt: string; character_ids: string[]; title: string; last_scene: string },
  ): Observable<{ project: Project; last_frame: Media; source: Clip }> {
    return this.http.post<{ project: Project; last_frame: Media; source: Clip }>(`/api/clips/${id}/continue`, request);
  }

  deleteClip(id: string): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`/api/clips/${id}`);
  }

  // --- projetos -----------------------------------------------------------------------------------------------------------

  projectOptions(): Observable<ProjectOptions> {
    return this.http.get<ProjectOptions>('/api/projects/options');
  }

  projects(): Observable<{ items: ProjectSummary[]; total: number }> {
    return this.http.get<{ items: ProjectSummary[]; total: number }>('/api/projects');
  }

  createProject(request: {
    form: StoryForm;
    original_prompt: string;
    character_ids: string[];
    target_duration_s?: number | null;
  }): Observable<CreatedProject> {
    return this.http.post<CreatedProject>('/api/projects', request);
  }

  project(id: string): Observable<ProjectDetail> {
    return this.http.get<ProjectDetail>(`/api/projects/${id}`);
  }

  updateProject(id: string, patch: ProjectPatch): Observable<ProjectDetail> {
    return this.http.patch<ProjectDetail>(`/api/projects/${id}`, patch);
  }

  deleteProject(id: string): Observable<{ deleted: boolean; media_removed: number }> {
    return this.http.delete<{ deleted: boolean; media_removed: number }>(`/api/projects/${id}`);
  }

  approveStage(id: string, stage: string, approveAll = false): Observable<ProjectDetail> {
    return this.http.post<ProjectDetail>(`/api/projects/${id}/stages/${stage}/approve`, { approve_all: approveAll });
  }

  reopenStage(id: string, stage: string): Observable<ProjectDetail> {
    return this.http.post<ProjectDetail>(`/api/projects/${id}/stages/${stage}/reopen`, null);
  }

  generateScript(id: string, mode: 'ia' | 'simples'): Observable<Job> {
    return this.http.post<Job>(`/api/projects/${id}/script`, { mode });
  }

  generateStoryboard(id: string, request: StoryboardRequest): Observable<Job> {
    return this.http.post<Job>(`/api/projects/${id}/storyboard`, request);
  }

  animateScenes(id: string, request: { scene_ids?: string[] | null; draft?: boolean; force?: boolean }): Observable<Job> {
    return this.http.post<Job>(`/api/projects/${id}/animate`, request);
  }

  generateAudio(id: string, transition?: Transition | null): Observable<Job> {
    return this.http.post<Job>(`/api/projects/${id}/audio`, transition ? { transition } : {});
  }

  assemble(id: string, transition?: Transition | null): Observable<Job> {
    return this.http.post<Job>(`/api/projects/${id}/assemble`, transition ? { transition } : {});
  }

  review(id: string): Observable<Review> {
    return this.http.get<Review>(`/api/projects/${id}/review`);
  }

  createScene(id: string, data: Partial<SceneData>, position?: number): Observable<SceneResponse> {
    return this.http.post<SceneResponse>(`/api/projects/${id}/scenes`, { data, ...(position ? { position } : {}) });
  }

  editScene(id: string, sceneId: string, changes: Partial<SceneData>): Observable<SceneResponse> {
    return this.http.patch<SceneResponse>(`/api/projects/${id}/scenes/${sceneId}`, { changes });
  }

  deleteScene(id: string, sceneId: string): Observable<{ deleted: boolean; stages: Stages }> {
    return this.http.delete<{ deleted: boolean; stages: Stages }>(`/api/projects/${id}/scenes/${sceneId}`);
  }

  reorderScenes(id: string, ids: string[]): Observable<ProjectDetail> {
    return this.http.post<ProjectDetail>(`/api/projects/${id}/scenes/reorder`, { ids });
  }

  approveScene(id: string, sceneId: string, stage: 'roteiro' | 'storyboard' | 'animacao', approved: boolean): Observable<SceneResponse> {
    return this.http.post<SceneResponse>(`/api/projects/${id}/scenes/${sceneId}/approve`, { stage, approved });
  }

  sceneVersions(id: string, sceneId: string): Observable<{ versions: SceneVersion[]; current: number }> {
    return this.http.get<{ versions: SceneVersion[]; current: number }>(`/api/projects/${id}/scenes/${sceneId}/versions`);
  }

  restoreScene(id: string, sceneId: string, version: number): Observable<SceneResponse> {
    return this.http.post<SceneResponse>(`/api/projects/${id}/scenes/${sceneId}/restore`, { version });
  }

  chooseBackground(id: string, sceneId: string, mediaId: string): Observable<SceneResponse> {
    return this.http.post<SceneResponse>(`/api/projects/${id}/scenes/${sceneId}/choose-background`, { media_id: mediaId });
  }

  recomposeScene(id: string, sceneId: string): Observable<SceneResponse> {
    return this.http.post<SceneResponse>(`/api/projects/${id}/scenes/${sceneId}/recompose`, null);
  }

  setLayout(id: string, sceneId: string, items: Record<string, unknown>[]): Observable<SceneResponse> {
    return this.http.put<SceneResponse>(`/api/projects/${id}/scenes/${sceneId}/layout`, { items });
  }

  // --- entrega: miniaturas, textos do YouTube, outro idioma e outro formato -----------------------------------------------

  generateThumbnails(id: string, request: { count: number; text?: string | null; scene_ids?: string[] | null }): Observable<Job> {
    return this.http.post<Job>(`/api/projects/${id}/thumbnails`, request);
  }

  deleteThumbnail(id: string, mediaId: string): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`/api/projects/${id}/thumbnails/${mediaId}`);
  }

  generateMetadata(id: string, mode: 'ia' | 'simples'): Observable<Job> {
    return this.http.post<Job>(`/api/projects/${id}/metadata`, { mode });
  }

  saveMetadata(id: string, texts: Partial<Record<MetadataLanguage, MetadataText>>): Observable<ProjectDetail> {
    return this.http.put<ProjectDetail>(`/api/projects/${id}/metadata`, { texts });
  }

  languageVersion(id: string, language: MetadataLanguage | null, mode: 'ia' | 'simples'): Observable<Job> {
    return this.http.post<Job>(`/api/projects/${id}/language-version`, { ...(language ? { language } : {}), mode });
  }

  createVariant(id: string, format: 'short' | 'longo'): Observable<{ project: Project; warnings: string[] }> {
    return this.http.post<{ project: Project; warnings: string[] }>(`/api/projects/${id}/variant`, { format });
  }

  nightPlan(): Observable<{ items: NightItem[] }> {
    return this.http.get<{ items: NightItem[] }>('/api/projects/night-plan');
  }

  nightQueue(projectIds?: string[]): Observable<NightResult> {
    return this.http.post<NightResult>('/api/projects/night-queue', projectIds ? { project_ids: projectIds } : {});
  }

  // --- pacotes .fabulim ------------------------------------------------------------------------------------------------------

  /** Endereço de download do pacote do projeto (o navegador baixa direto, sem passar pelo Angular). */
  projectPackageUrl(id: string, renders: boolean): string {
    return `/api/packages/projects/${id}?renders=${renders}`;
  }

  charactersPackageUrl(ids: string[] = []): string {
    return ids.length ? `/api/packages/characters?${ids.map((i) => `id=${i}`).join('&')}` : '/api/packages/characters';
  }

  importPackage(file: File): Observable<HttpEvent<ImportReport>> {
    return this.http.post<ImportReport>('/api/packages/import', file, { observe: 'events', reportProgress: true });
  }
}
