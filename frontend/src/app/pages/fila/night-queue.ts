import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { errorMessage } from '../../core/http-error';
import { I18nService } from '../../core/i18n/i18n.service';
import { TPipe } from '../../core/i18n/t.pipe';
import { JobsService } from '../../core/jobs.service';
import { NightItem } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { IconComponent } from '../../ui/icon';
import { SectionComponent } from '../../ui/section';

/**
 * Fila noturna (briefing 7.9): renderiza tudo o que já foi aprovado enquanto você dorme. Nunca aprova nada por conta própria:
 * olha até onde cada projeto foi aprovado e pede o próximo trabalho pesado (cenários, animação, áudio ou montagem).
 */
@Component({
  selector: 'fab-night-queue',
  imports: [RouterLink, TPipe, IconComponent, SectionComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <fab-section headingId="noite" [title]="'fila.night.title' | t" [hint]="'fila.night.hint' | t">
      @if (items().length) {
        <ul class="rule-list m-0 p-0">
          @for (item of items(); track item.project_id) {
            <li class="grid gap-x-6 gap-y-1 md:grid-cols-[minmax(0,1fr)_auto]">
              <div class="min-w-0">
                <a [routerLink]="['/projetos', item.project_id]" class="font-display text-[1.125rem] font-semibold">{{ item.title }}</a>
                <p class="text-small text-ink-soft">{{ 'fila.night.next' | t: { stage: item.stage_label } }}</p>
              </div>
              @if (item.blocked_by) {
                <span class="text-small font-semibold text-warn-ink">{{ item.blocked_by }}</span>
              } @else {
                <span class="text-small font-semibold text-ok-ink">{{ 'fila.night.ready' | t }}</span>
              }
            </li>
          }
        </ul>
        <div class="mt-5 flex flex-wrap items-center gap-3">
          <button type="button" class="btn btn-primary" (click)="start()" [disabled]="busy() || ready().length === 0">
            <fab-icon name="clock" [size]="18" />
            {{ 'fila.night.start' | t: { n: ready().length } }}
          </button>
          <span class="text-small text-ink-soft">{{ 'fila.night.note' | t }}</span>
        </div>
      } @else if (loaded()) {
        <p class="font-text text-ink-soft">{{ 'fila.night.empty' | t }}</p>
      }
      @if (error(); as message) {
        <p class="banner banner-error mt-4" role="alert">{{ message }}</p>
      }
    </fab-section>
  `,
})
export class NightQueueComponent {
  private readonly api = inject(ApiService);
  private readonly jobs = inject(JobsService);
  private readonly toast = inject(ToastService);
  private readonly i18n = inject(I18nService);

  protected readonly items = signal<NightItem[]>([]);
  protected readonly loaded = signal(false);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly ready = computed(() => this.items().filter((i) => !i.blocked_by));

  constructor() {
    this.load();
    this.jobs.finished$.pipe(takeUntilDestroyed(inject(DestroyRef))).subscribe((job) => {
      if (job.params['project_id']) this.load();
    });
  }

  protected load(): void {
    this.api.nightPlan().subscribe({
      next: (plan) => {
        this.items.set(plan.items);
        this.loaded.set(true);
      },
      error: () => this.loaded.set(true),
    });
  }

  protected start(): void {
    this.busy.set(true);
    this.error.set(null);
    this.api.nightQueue().subscribe({
      next: (result) => {
        this.busy.set(false);
        result.queued.forEach((job) => this.jobs.merge(job));
        this.toast.show(this.i18n.t('fila.night.queued', { n: result.queued.length }));
        this.load();
      },
      error: (e: unknown) => {
        this.busy.set(false);
        this.error.set(errorMessage(e));
      },
    });
  }
}
