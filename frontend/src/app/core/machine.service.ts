import { Injectable, computed, inject, signal } from '@angular/core';

import { ApiService } from './api.service';
import { BenchmarkReport, Capability, MachineSnapshot } from './models';

/** Perfil da máquina, matriz de capacidades e resultados do benchmark de calibração. */
@Injectable({ providedIn: 'root' })
export class MachineService {
  private readonly api = inject(ApiService);

  readonly snapshot = signal<MachineSnapshot | null>(null);
  readonly benchmark = signal<BenchmarkReport | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  readonly profile = computed(() => this.snapshot()?.profile ?? null);
  readonly capabilities = computed<Capability[]>(() => this.snapshot()?.capabilities ?? []);

  capability(id: string): Capability | undefined {
    return this.capabilities().find((c) => c.id === id);
  }

  refresh(): void {
    this.loading.set(true);
    this.api.machine().subscribe({
      next: (snapshot) => {
        this.snapshot.set(snapshot);
        this.error.set(null);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('unreachable');
        this.loading.set(false);
      },
    });
    this.api.benchmark().subscribe({
      next: (report) => this.benchmark.set(report),
      error: () => undefined, // o benchmark é complementar: a página funciona sem ele
    });
  }
}
