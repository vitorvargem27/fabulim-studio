import { ChangeDetectionStrategy, Component, computed, effect, inject, signal, untracked } from '@angular/core';

import { ApiService, Transition } from '../../../core/api.service';
import { formatBytes, formatDuration } from '../../../core/format';
import { TPipe } from '../../../core/i18n/t.pipe';
import { IconComponent } from '../../../ui/icon';
import { SectionComponent } from '../../../ui/section';
import { ProjectStore } from '../project.store';
import { StageApprovalComponent } from './stage-approval';

const TRANSITIONS: Transition[] = ['corte', 'fade', 'suave'];

/** Etapa 6: a montagem. Junta os clipes e o áudio no vídeo final (H.264 e AAC, volume em -14 LUFS) e confere os flashes. */
@Component({
  selector: 'fab-etapa-montagem',
  imports: [TPipe, IconComponent, SectionComponent, StageApprovalComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <fab-section headingId="montagem" [title]="'proj.stage.montagem' | t" [hint]="'proj.mont.hint' | t">
      <div class="grid gap-5">
        <div class="field-row">
          <div class="field">
            <label class="field-label" for="mont-transition">{{ 'clipes.join.transition' | t }}</label>
            <select id="mont-transition" (change)="onTransition($event)">
              @for (t of transitions; track t) {
                <option [value]="t" [selected]="t === transition()">{{ 'clipes.transition.' + t | t }}</option>
              }
            </select>
          </div>
        </div>
        <div>
          <button type="button" class="btn btn-primary" (click)="assemble()" [disabled]="store.busy() || store.hasActive('projeto.montar') || !audioReady()">
            <fab-icon name="film" [size]="18" />
            {{ (final() ? 'proj.mont.again' : 'proj.mont.generate') | t }}
          </button>
          @if (!audioReady()) {
            <span class="ml-3 text-small text-ink-soft">{{ 'proj.mont.needs' | t }}</span>
          }
        </div>
      </div>
    </fab-section>

    @if (final(); as video) {
      <fab-section headingId="final" [title]="'proj.mont.result' | t" [hint]="'proj.mont.result.hint' | t">
        <div class="grid gap-4">
          <video class="w-full max-w-3xl border-2 border-ink bg-anil" [class.max-w-sm]="portrait()" [src]="video.url" [attr.poster]="video.thumb_url" controls playsinline></video>
          <p class="text-small text-ink-soft">
            {{ video.width }}×{{ video.height }} · {{ duration(video.duration_s) }} · {{ bytes(video.size_bytes) }}
            @if (loudness(); as l) {
              · {{ 'proj.mont.loudness' | t: { value: l } }}
            }
          </p>
        </div>
      </fab-section>
    }
    <fab-stage-approval stage="montagem" />
  `,
})
export class EtapaMontagem {
  protected readonly store = inject(ProjectStore);
  private readonly api = inject(ApiService);

  protected readonly transitions = TRANSITIONS;
  protected readonly transition = signal<Transition>('corte');
  protected readonly duration = formatDuration;
  protected readonly bytes = formatBytes;

  protected readonly final = computed(() => this.store.detail()?.files.final ?? null);
  protected readonly audioReady = computed(() => !!this.store.detail()?.files.mix);
  protected readonly portrait = computed(() => this.store.project()?.format === 'short');
  protected readonly loudness = computed(() => {
    const value = this.store.detail()?.quality?.['loudness_input'];
    return typeof value === 'number' ? value.toFixed(1) : null;
  });

  constructor() {
    effect(() => {
      const saved = this.store.project()?.settings['transition'];
      if (typeof saved === 'string') untracked(() => this.transition.set(saved as Transition));
    });
  }

  protected onTransition(event: Event): void {
    this.transition.set((event.target as HTMLSelectElement).value as Transition);
  }

  protected assemble(): void {
    this.store.startJob(this.api.assemble(this.store.id(), this.transition()));
  }
}
