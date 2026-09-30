import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal } from '@angular/core';

import { ApiService } from '../../core/api.service';
import { formatTime } from '../../core/format';
import { TPipe } from '../../core/i18n/t.pipe';
import { LogEntry } from '../../core/models';
import { StatusService } from '../../core/status.service';
import { BadgeComponent, BadgeTone } from '../../ui/badge';
import { EmptyStateComponent } from '../../ui/empty-state';
import { IconComponent } from '../../ui/icon';

const LEVEL_TONES: Record<string, BadgeTone> = {
  DEBUG: 'neutral',
  INFO: 'info',
  WARNING: 'warning',
  ERROR: 'error',
  CRITICAL: 'error',
};

/** Logs estruturados do backend, filtráveis por serviço e nível. O `?service=` da URL já chega preenchido. */
@Component({
  selector: 'fab-logs-page',
  imports: [TPipe, BadgeComponent, EmptyStateComponent, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './logs.page.html',
})
export class LogsPage {
  private readonly api = inject(ApiService);
  private readonly status = inject(StatusService);

  readonly service = input<string>(); // vem do query param ?service=

  protected readonly entries = signal<LogEntry[]>([]);
  protected readonly loading = signal(false);
  protected readonly failed = signal(false);
  protected readonly selectedService = signal('');
  protected readonly level = signal('');
  protected readonly auto = signal(false);
  protected readonly time = formatTime;

  protected readonly serviceOptions = computed(() => {
    const fromStatus = this.status.services().flatMap((s) => (s.log_service ? [s.log_service] : []));
    const all = new Set(['app', 'fila', ...fromStatus, ...this.entries().map((e) => e.service)]);
    const selected = this.selectedService();
    if (selected) all.add(selected);
    return [...all].sort();
  });

  constructor() {
    effect(() => {
      const fromUrl = this.service();
      if (fromUrl) this.selectedService.set(fromUrl);
    });
    effect(() => {
      this.selectedService();
      this.level();
      this.load();
    });
    effect((onCleanup) => {
      if (!this.auto()) return;
      const id = setInterval(() => this.load(), 5000);
      onCleanup(() => clearInterval(id));
    });
  }

  protected load(): void {
    this.loading.set(true);
    this.api.logs({ service: this.selectedService() || undefined, level: this.level() || undefined, limit: 300 }).subscribe({
      next: (entries) => {
        this.entries.set([...entries].reverse()); // mais recentes primeiro
        this.failed.set(false);
        this.loading.set(false);
      },
      error: () => {
        this.failed.set(true);
        this.loading.set(false);
      },
    });
  }

  protected tone(level: string): BadgeTone {
    return LEVEL_TONES[level] ?? 'neutral';
  }

  protected pick(kind: 'service' | 'level', event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    (kind === 'service' ? this.selectedService : this.level).set(value);
  }

  protected toggleAuto(event: Event): void {
    this.auto.set((event.target as HTMLInputElement).checked);
  }
}
