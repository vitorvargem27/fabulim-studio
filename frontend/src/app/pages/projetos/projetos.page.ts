import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { formatDateTime } from '../../core/format';
import { errorMessage } from '../../core/http-error';
import { I18nService } from '../../core/i18n/i18n.service';
import { TPipe } from '../../core/i18n/t.pipe';
import { JobsService } from '../../core/jobs.service';
import { ProjectSummary, StageId } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { BadgeComponent } from '../../ui/badge';
import { EmptyStateComponent } from '../../ui/empty-state';
import { IconComponent } from '../../ui/icon';
import { PackageImportComponent } from '../../ui/package-import';
import { PageHeaderComponent } from '../../ui/page-header';
import { SectionComponent } from '../../ui/section';
import { STAGE_ORDER } from './project.store';

/** Quantas das sete etapas já foram aprovadas (a barra de progresso do cartão). */
export function approvedCount(project: Pick<ProjectSummary, 'approvals'>): number {
  return STAGE_ORDER.filter((s) => project.approvals[s]).length;
}

/** Lista dos projetos (briefing 7.4): cada vídeo com enredo, cenas, versões e o ponto em que está. */
@Component({
  selector: 'fab-projetos-page',
  imports: [
    RouterLink,
    TPipe,
    BadgeComponent,
    EmptyStateComponent,
    IconComponent,
    PackageImportComponent,
    PageHeaderComponent,
    SectionComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './projetos.page.html',
})
export class ProjetosPage {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);
  private readonly i18n = inject(I18nService);
  private readonly jobs = inject(JobsService);

  protected readonly items = signal<ProjectSummary[]>([]);
  protected readonly loaded = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly total = computed(() => STAGE_ORDER.length);
  protected readonly date = formatDateTime;

  constructor() {
    this.load();
    this.jobs.finished$.pipe(takeUntilDestroyed(inject(DestroyRef))).subscribe((job) => {
      if (job.params['project_id']) this.load();
    });
  }

  protected load(): void {
    this.api.projects().subscribe({
      next: (res) => {
        this.items.set(res.items);
        this.loaded.set(true);
      },
      error: (e: unknown) => {
        this.loaded.set(true);
        this.error.set(errorMessage(e));
      },
    });
  }

  protected approved(project: ProjectSummary): number {
    return approvedCount(project);
  }

  protected stageName(stage: StageId): string {
    return this.i18n.t(`proj.stage.${stage}`);
  }

  protected remove(project: ProjectSummary): void {
    if (!window.confirm(this.i18n.t('proj.remove.confirm', { title: project.title }))) return;
    this.api.deleteProject(project.id).subscribe({
      next: () => {
        this.items.update((l) => l.filter((p) => p.id !== project.id));
        this.toast.show(this.i18n.t('proj.removed'));
      },
      error: (e: unknown) => this.toast.show(errorMessage(e), 'error'),
    });
  }
}
