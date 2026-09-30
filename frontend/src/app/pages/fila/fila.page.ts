import { CdkDrag, CdkDragDrop, CdkDragHandle, CdkDropList, moveItemInArray } from '@angular/cdk/drag-drop';
import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { formatDuration, formatPercent, formatTime } from '../../core/format';
import { I18nService } from '../../core/i18n/i18n.service';
import { TPipe } from '../../core/i18n/t.pipe';
import { heldByWorker, JobsService } from '../../core/jobs.service';
import { Job } from '../../core/models';
import { BadgeComponent, BadgeTone } from '../../ui/badge';
import { EmptyStateComponent } from '../../ui/empty-state';
import { IconComponent } from '../../ui/icon';
import { PageHeaderComponent } from '../../ui/page-header';
import { ProgressComponent } from '../../ui/progress';
import { SectionComponent } from '../../ui/section';
import { NightQueueComponent } from './night-queue';

const TONES: Record<Job['status'], BadgeTone> = {
  queued: 'neutral',
  running: 'info',
  paused: 'warning',
  done: 'ok',
  failed: 'error',
  canceled: 'neutral',
};

/** Fila única de tarefas pesadas: ao vivo (SSE), pausar/retomar/cancelar e reordenar arrastando (ou pelos botões). */
@Component({
  selector: 'fab-fila-page',
  imports: [
    CdkDrag,
    CdkDragHandle,
    CdkDropList,
    NgTemplateOutlet,
    TPipe,
    BadgeComponent,
    EmptyStateComponent,
    IconComponent,
    NightQueueComponent,
    PageHeaderComponent,
    ProgressComponent,
    SectionComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './fila.page.html',
})
export class FilaPage {
  protected readonly jobs = inject(JobsService);
  private readonly i18n = inject(I18nService);

  protected readonly time = formatTime;
  protected readonly duration = formatDuration;
  protected readonly percent = formatPercent;

  protected readonly current = computed(() => this.jobs.jobs().find(heldByWorker) ?? null);
  protected readonly queued = computed(() =>
    this.jobs.active().filter((j) => j.status === 'queued' || (j.status === 'paused' && !j.pause_requested)),
  );
  protected readonly hasAny = computed(() => this.jobs.jobs().length > 0);

  protected demo(): void {
    this.jobs.create('demo.sleep', { seconds: 20, steps: 20 });
  }

  protected drop(event: CdkDragDrop<Job[]>): void {
    if (event.previousIndex === event.currentIndex) return;
    const ids = this.queued().map((j) => j.id);
    moveItemInArray(ids, event.previousIndex, event.currentIndex);
    this.jobs.reorder(ids);
  }

  /** Alternativa ao arrastar (teclado e leitor de tela): sobe ou desce uma posição. */
  protected move(job: Job, delta: -1 | 1): void {
    const ids = this.queued().map((j) => j.id);
    const from = ids.indexOf(job.id);
    const to = from + delta;
    if (from === -1 || to < 0 || to >= ids.length) return;
    moveItemInArray(ids, from, to);
    this.jobs.reorder(ids);
  }

  protected act(job: Job, action: 'pause' | 'resume' | 'cancel'): void {
    this.jobs.act(job, action);
  }

  protected tone(job: Job): BadgeTone {
    return TONES[job.status];
  }

  protected canPause(job: Job): boolean {
    return job.status === 'running' && !job.pause_requested;
  }

  protected canResume(job: Job): boolean {
    return job.status === 'paused' || (job.status === 'running' && job.pause_requested);
  }

  protected kind(job: Job): string {
    const key = `fila.kind.${job.kind}`;
    const text = this.i18n.t(key);
    return text === key ? job.kind : text;
  }
}
