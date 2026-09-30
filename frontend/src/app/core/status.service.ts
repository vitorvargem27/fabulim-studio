import { Injectable, OnDestroy, computed, inject, signal } from '@angular/core';

import { ApiService } from './api.service';
import { ServiceStatus, StatusReport } from './models';

/** Saúde dos serviços (página Status e indicador do Claude no topo). Atualiza sozinho enquanto a aba está visível. */
@Injectable({ providedIn: 'root' })
export class StatusService implements OnDestroy {
  private readonly api = inject(ApiService);
  private timer: ReturnType<typeof setInterval> | null = null;

  readonly report = signal<StatusReport | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  readonly services = computed<ServiceStatus[]>(() => this.report()?.services ?? []);
  readonly claude = computed(() => this.services().find((s) => s.id === 'claude') ?? null);
  readonly problems = computed(() => this.services().filter((s) => s.state === 'error').length);
  readonly warnings = computed(() => this.services().filter((s) => s.state === 'warning').length);

  refresh(): void {
    if (this.loading()) return;
    this.loading.set(true);
    this.api.status().subscribe({
      next: (report) => {
        this.report.set(report);
        this.error.set(null);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('unreachable');
        this.loading.set(false);
      },
    });
  }

  startAutoRefresh(intervalMs = 15_000): void {
    if (this.timer) return;
    this.refresh();
    this.timer = setInterval(() => {
      if (typeof document === 'undefined' || document.visibilityState === 'visible') this.refresh();
    }, intervalMs);
  }

  ngOnDestroy(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}
