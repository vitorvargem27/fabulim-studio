import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { errorMessage } from '../../core/http-error';
import { I18nService } from '../../core/i18n/i18n.service';
import { TPipe } from '../../core/i18n/t.pipe';
import { JobsService } from '../../core/jobs.service';
import { Stage, StageId } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { EmptyStateComponent } from '../../ui/empty-state';
import { IconComponent } from '../../ui/icon';
import { JobProgressComponent } from '../../ui/job-progress';
import { PageHeaderComponent } from '../../ui/page-header';
import { EtapaAnimacao } from './etapas/etapa-animacao';
import { EtapaAudio } from './etapas/etapa-audio';
import { EtapaEnredo } from './etapas/etapa-enredo';
import { EtapaMontagem } from './etapas/etapa-montagem';
import { EtapaRevisao } from './etapas/etapa-revisao';
import { EtapaRoteiro } from './etapas/etapa-roteiro';
import { EtapaStoryboard } from './etapas/etapa-storyboard';
import { ProjectStore } from './project.store';

/**
 * O projeto por dentro (briefing 7.4): as sete etapas, cada uma com o que fazer e a aprovação que libera a próxima. O que já
 * foi gerado nunca é jogado fora ao voltar uma etapa: só volta a pedir aprovação.
 */
@Component({
  selector: 'fab-projeto-page',
  providers: [ProjectStore],
  imports: [
    RouterLink,
    TPipe,
    EmptyStateComponent,
    EtapaAnimacao,
    EtapaAudio,
    EtapaEnredo,
    EtapaMontagem,
    EtapaRevisao,
    EtapaRoteiro,
    EtapaStoryboard,
    IconComponent,
    JobProgressComponent,
    PageHeaderComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './projeto.page.html',
})
export class ProjetoPage {
  /** O id vem da rota (`/projetos/:id`). */
  readonly id = input.required<string>();

  protected readonly store = inject(ProjectStore);
  private readonly api = inject(ApiService);
  private readonly jobs = inject(JobsService);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);
  private readonly i18n = inject(I18nService);

  /** A etapa que o usuário escolheu ver (senão, a etapa atual do projeto). */
  protected readonly view = signal<StageId | null>(null);
  protected readonly shown = computed<StageId>(() => this.view() ?? this.store.currentStage());
  protected readonly project = this.store.project;

  constructor() {
    effect(() => {
      const id = this.id();
      untracked(() => {
        this.view.set(null);
        this.store.load(id);
      });
    });
  }

  protected select(stage: Stage): void {
    if (stage.available) this.view.set(stage.id);
  }

  protected stateOf(stage: Stage): 'approved' | 'current' | 'locked' | 'open' {
    if (stage.approved) return 'approved';
    if (!stage.available) return 'locked';
    return stage.id === this.store.currentStage() ? 'current' : 'open';
  }

  /** Renderiza agora o próximo trabalho pesado que as aprovações já liberaram (a mesma regra da fila noturna). */
  protected night(): void {
    this.api.nightQueue([this.id()]).subscribe({
      next: (result) => {
        result.queued.forEach((job) => this.jobs.merge(job));
        if (result.queued.length) this.toast.show(this.i18n.t('fila.night.queued', { n: result.queued.length }));
        else this.toast.show(result.skipped[0]?.blocked_by ?? this.i18n.t('fila.night.nothing'), 'info');
      },
      error: (e: unknown) => this.store.error.set(errorMessage(e)),
    });
  }

  protected remove(): void {
    const title = this.project()?.title ?? '';
    if (!window.confirm(this.i18n.t('proj.remove.confirm', { title }))) return;
    this.api.deleteProject(this.id()).subscribe({
      next: () => {
        this.toast.show(this.i18n.t('proj.removed'));
        void this.router.navigate(['/projetos']);
      },
      error: () => this.toast.show(this.i18n.t('proj.remove.failed'), 'error'),
    });
  }
}
