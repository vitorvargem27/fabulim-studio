import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';

import { formatDuration, formatPercent } from '../core/format';
import { I18nService } from '../core/i18n/i18n.service';
import { TPipe } from '../core/i18n/t.pipe';
import { JobsService } from '../core/jobs.service';
import { Job } from '../core/models';
import { BadgeComponent, BadgeTone } from './badge';
import { IconComponent } from './icon';
import { ProgressComponent } from './progress';

const TONES: Record<Job['status'], BadgeTone> = {
  queued: 'neutral',
  running: 'info',
  paused: 'warning',
  done: 'ok',
  failed: 'error',
  canceled: 'neutral',
};

/**
 * O andamento de uma tarefa da fila, dentro da própria página que a pediu: título, barra, mensagem, tempo estimado e
 * cancelar. Recebe só o id: quem manda é a fila ao vivo (SSE), então nunca fica desatualizado.
 */
@Component({
  selector: 'fab-job-progress',
  imports: [BadgeComponent, IconComponent, ProgressComponent, TPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (job(); as j) {
      <div class="job-box grid gap-2 border-2 border-ink bg-wash p-3" role="status" [attr.aria-label]="j.title">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <strong class="font-display text-[1.0625rem] font-semibold">{{ j.title }}</strong>
          <fab-badge [tone]="tone()">{{ 'job.status.' + j.status | t }}</fab-badge>
        </div>
        @if (j.status === 'running' || j.status === 'paused' || j.status === 'queued') {
          <fab-progress [value]="j.progress" [label]="j.title" [paused]="j.status === 'paused'" />
          <p class="text-small text-ink-soft">
            @if (j.status === 'queued') {
              {{ 'job.waiting' | t }}
            } @else {
              {{ percent() }}
              @if (j.message) {
                · {{ j.message }}
              }
              @if (j.eta_seconds && j.status === 'running') {
                · {{ 'fila.eta' | t: { time: duration(j.eta_seconds) } }}
              }
            }
          </p>
          <div class="flex flex-wrap gap-2">
            <button type="button" class="btn btn-sm btn-danger" (click)="jobs.act(j, 'cancel')" [disabled]="j.cancel_requested">
              <fab-icon name="stop" [size]="16" />
              {{ 'fila.cancel.short' | t }}
            </button>
          </div>
        }
        @if (j.status === 'failed' && j.error) {
          <p class="text-small font-semibold text-bad-ink" role="alert">{{ j.error }}</p>
        }
        @if (j.status === 'canceled') {
          <p class="text-small text-ink-soft">{{ 'job.canceled' | t }}</p>
        }
      </div>
    }
  `,
  host: { class: 'block empty:hidden' },
})
export class JobProgressComponent {
  readonly jobId = input<string | null>(null);
  protected readonly jobs = inject(JobsService);
  protected readonly i18n = inject(I18nService);

  protected readonly job = computed(() => this.jobs.byId(this.jobId()));
  protected readonly tone = computed(() => TONES[this.job()?.status ?? 'queued']);
  protected readonly percent = computed(() => formatPercent(this.job()?.progress ?? 0));
  protected readonly duration = formatDuration;
}
