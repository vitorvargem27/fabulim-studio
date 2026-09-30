import { DestroyRef, Injectable, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Observable } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { errorMessage } from '../../core/http-error';
import { I18nService } from '../../core/i18n/i18n.service';
import { JobsService } from '../../core/jobs.service';
import { Character, Job, Project, ProjectDetail, ProjectOptions, Scene, SceneResponse, Stage, StageId, Stages } from '../../core/models';
import { ToastService } from '../../core/toast.service';

export const STAGE_ORDER: StageId[] = ['enredo', 'roteiro', 'storyboard', 'animacao', 'audio', 'montagem', 'revisao'];

/**
 * O projeto aberto na tela: os dados, as cenas, as etapas, as tarefas em andamento e as ações comuns. Cada painel de etapa
 * pede a este serviço em vez de repetir chamadas. Fica ligado à página do projeto (um por projeto aberto).
 */
@Injectable()
export class ProjectStore {
  private readonly api = inject(ApiService);
  private readonly jobs = inject(JobsService);
  private readonly toast = inject(ToastService);
  private readonly i18n = inject(I18nService);

  readonly detail = signal<ProjectDetail | null>(null);
  readonly options = signal<ProjectOptions | null>(null);
  readonly missing = signal(false);
  readonly error = signal<string | null>(null);
  readonly busy = signal(false);
  readonly id = signal('');
  /** Avisos que a última tarefa devolveu (por exemplo, «o modelo local não escreveu o roteiro; usei o modo simples»). */
  readonly notices = signal<string[]>([]);

  readonly project = computed<Project | null>(() => this.detail()?.project ?? null);
  readonly scenes = computed<Scene[]>(() => this.detail()?.scenes ?? []);
  readonly characters = computed<Character[]>(() => this.detail()?.characters ?? []);
  readonly stages = computed<Stage[]>(() => this.detail()?.stages.stages ?? []);
  readonly currentStage = computed<StageId>(() => this.detail()?.stages.current ?? 'enredo');
  readonly activeJobs = computed<Job[]>(() => {
    const id = this.id();
    return id ? this.jobs.active().filter((j) => j.params['project_id'] === id) : [];
  });

  private reloadTimer: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    const destroyed = inject(DestroyRef);
    this.api.projectOptions().subscribe({ next: (o) => this.options.set(o), error: () => undefined });
    this.jobs.finished$.pipe(takeUntilDestroyed(destroyed)).subscribe((job) => {
      if (job.params['project_id'] !== this.id()) return;
      const warnings = job.result?.['warnings'];
      this.notices.set(Array.isArray(warnings) ? warnings.map(String) : []);
      this.load(this.id());
      if (job.status === 'failed') this.toast.show(job.error ?? this.i18n.t('proj.job.failed'), 'error');
      else if (job.status === 'done') this.toast.show(job.title, 'success');
    });
    // cada imagem ou clipe de uma cena aparece assim que fica pronto
    this.jobs.media$.pipe(takeUntilDestroyed(destroyed)).subscribe((event) => {
      if (event.type !== 'created' || !this.id()) return;
      const owner = event.media.owner_id;
      if (owner === this.id() || this.scenes().some((s) => s.id === owner)) this.reloadSoon();
    });
    destroyed.onDestroy(() => {
      if (this.reloadTimer) clearTimeout(this.reloadTimer);
    });
  }

  /** Abre (ou recarrega) um projeto. */
  load(id: string): void {
    this.id.set(id);
    this.api.project(id).subscribe({
      next: (detail) => {
        if (id !== this.id()) return;
        this.detail.set(detail);
        this.missing.set(false);
      },
      error: () => this.missing.set(true),
    });
  }

  reloadSoon(): void {
    if (this.reloadTimer) clearTimeout(this.reloadTimer);
    this.reloadTimer = setTimeout(() => this.load(this.id()), 500);
  }

  /** Aplica a resposta de uma edição de cena sem recarregar tudo. */
  applyScene(response: SceneResponse): void {
    this.detail.update((d) => {
      if (!d) return d;
      const scenes = d.scenes.map((s) => (s.id === response.scene.id ? response.scene : s));
      const stages: Stages = response.stages;
      return { ...d, scenes: scenes.some((s) => s.id === response.scene.id) ? scenes : [...scenes, response.scene], stages };
    });
    if (response.warning) this.toast.show(response.warning, 'info');
  }

  applyDetail(detail: ProjectDetail): void {
    this.detail.set(detail);
  }

  /** Executa uma chamada mostrando «ocupado» e o erro (se houver) no lugar certo da tela. */
  run<T>(request: Observable<T>, done?: (value: T) => void): void {
    this.error.set(null);
    this.busy.set(true);
    request.subscribe({
      next: (value) => {
        this.busy.set(false);
        done?.(value);
      },
      error: (e: unknown) => {
        this.busy.set(false);
        this.error.set(errorMessage(e));
      },
    });
  }

  /** Pede uma tarefa da fila e a coloca na lista ao vivo. */
  startJob(request: Observable<Job>): void {
    this.notices.set([]);
    this.run(request, (job) => this.jobs.merge(job));
  }

  hasActive(kind: string): boolean {
    return this.activeJobs().some((j) => j.kind === kind);
  }

  stage(id: StageId): Stage | undefined {
    return this.stages().find((s) => s.id === id);
  }

  approveStage(stage: StageId, approveAll = false): void {
    this.run(this.api.approveStage(this.id(), stage, approveAll), (detail) => {
      this.detail.set(detail);
      this.toast.show(this.i18n.t('proj.stage.approved'));
    });
  }

  reopenStage(stage: StageId): void {
    this.run(this.api.reopenStage(this.id(), stage), (detail) => this.detail.set(detail));
  }

  approveScene(scene: Scene, stage: 'roteiro' | 'storyboard' | 'animacao', approved: boolean): void {
    this.run(this.api.approveScene(this.id(), scene.id, stage, approved), (r) => this.applyScene(r));
  }
}
