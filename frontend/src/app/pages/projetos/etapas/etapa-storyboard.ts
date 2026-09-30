import { ChangeDetectionStrategy, Component, computed, effect, inject, signal, untracked } from '@angular/core';

import { ApiService, Quality, StoryboardRequest } from '../../../core/api.service';
import { formatDuration } from '../../../core/format';
import { TPipe } from '../../../core/i18n/t.pipe';
import { parseSeed } from '../../../core/match';
import { Estimate } from '../../../core/models';
import { EmptyStateComponent } from '../../../ui/empty-state';
import { FieldComponent } from '../../../ui/field';
import { IconComponent } from '../../../ui/icon';
import { SectionComponent } from '../../../ui/section';
import { ProjectStore } from '../project.store';
import { SceneStoryboardComponent } from './scene-storyboard';
import { StageApprovalComponent } from './stage-approval';

const MODES: StoryboardRequest['mode'][] = ['faltantes', 'regerar', 'variacoes'];
const QUALITIES: Quality[] = ['rascunho', 'padrao', 'alta'];

/**
 * Etapa 3: o storyboard. Cada cena ganha um cenário gerado por IA e os personagens (PNG transparente) por cima, para eles
 * continuarem iguais de uma cena para outra. Você escolhe entre alternativas e ajusta a posição de cada um.
 */
@Component({
  selector: 'fab-etapa-storyboard',
  imports: [TPipe, EmptyStateComponent, FieldComponent, IconComponent, SceneStoryboardComponent, SectionComponent, StageApprovalComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <fab-section headingId="storyboard" [title]="'proj.stage.storyboard' | t" [hint]="'proj.sb.hint' | t">
      @if (store.scenes().length) {
        <div class="grid gap-5">
          <div class="field-row">
            <div class="field">
              <label class="field-label" for="sb-mode">{{ 'proj.sb.mode' | t }}</label>
              <select id="sb-mode" (change)="onMode($event)">
                @for (m of modes; track m) {
                  <option [value]="m" [selected]="m === mode()">{{ 'proj.sb.mode.' + m | t }}</option>
                }
              </select>
            </div>
            @if (mode() === 'variacoes') {
              <div class="field">
                <label class="field-label" for="sb-variations">{{ 'proj.sb.variations' | t }}</label>
                <select id="sb-variations" (change)="onVariations($event)">
                  @for (n of [2, 3, 4]; track n) {
                    <option [value]="n" [selected]="n === variations()">{{ n }}</option>
                  }
                </select>
              </div>
            }
            <div class="field">
              <label class="field-label" for="sb-quality">{{ 'imagem.quality' | t }}</label>
              <select id="sb-quality" (change)="onQuality($event)">
                @for (q of qualities; track q) {
                  <option [value]="q" [selected]="q === quality()">{{ 'imagem.quality.' + q | t }}</option>
                }
              </select>
            </div>
            <fab-field type="text" [label]="'imagem.seed' | t" [maxlength]="10" [(value)]="seed" />
          </div>
          <p class="font-text text-body">
            {{ 'proj.sb.estimate' | t: { time: estimateLabel(), n: imageCount() } }}
          </p>
          <div class="flex flex-wrap items-center gap-3">
            <button type="button" class="btn btn-primary" (click)="generate()" [disabled]="store.busy() || store.hasActive('projeto.storyboard') || imageCount() === 0">
              <fab-icon name="sparkles" [size]="18" />
              {{ (picked().length ? 'proj.sb.generate.picked' : 'proj.sb.generate.all') | t: { n: picked().length } }}
            </button>
            @if (picked().length) {
              <button type="button" class="btn btn-sm btn-quiet" (click)="picked.set([])">{{ 'proj.sb.clear' | t }}</button>
            }
          </div>
        </div>
      } @else {
        <fab-empty [title]="'proj.sb.noscenes.title' | t" [text]="'proj.sb.noscenes.text' | t" />
      }
    </fab-section>

    @if (store.scenes().length) {
      <fab-section headingId="cenas-sb" [title]="('proj.scenes.title' | t) + ' (' + store.scenes().length + ')'" [hint]="'proj.sb.scenes.hint' | t">
        <div class="grid gap-5">
          @for (scene of store.scenes(); track scene.id) {
            <fab-scene-storyboard [scene]="scene" [quality]="quality()" [picked]="picked().includes(scene.id)" (pick)="togglePick(scene.id, $event)" />
          }
        </div>
      </fab-section>
      <fab-stage-approval stage="storyboard" />
    }
  `,
})
export class EtapaStoryboard {
  protected readonly store = inject(ProjectStore);
  private readonly api = inject(ApiService);

  protected readonly modes = MODES;
  protected readonly qualities = QUALITIES;
  protected readonly mode = signal<StoryboardRequest['mode']>('faltantes');
  protected readonly variations = signal(2);
  protected readonly quality = signal<Quality>('padrao');
  protected readonly seed = signal('');
  protected readonly picked = signal<string[]>([]);
  protected readonly estimate = signal<Estimate | null>(null);

  protected readonly imageCount = computed(() => {
    const scenes = this.store.scenes();
    const chosen = this.picked();
    const target = chosen.length ? scenes.filter((s) => chosen.includes(s.id)) : scenes;
    switch (this.mode()) {
      case 'faltantes':
        return target.filter((s) => !s.data.background).length;
      case 'variacoes':
        return target.length * this.variations();
      default:
        return target.length;
    }
  });
  protected readonly estimateLabel = computed(() => {
    const per = this.estimate()?.per_image_seconds;
    return per ? formatDuration(per * this.imageCount()) : '—';
  });

  constructor() {
    effect(() => {
      const format = this.store.project()?.format === 'short' ? '9:16' : '16:9';
      const quality = this.quality();
      untracked(() =>
        this.api.imageEstimate(format, quality, 1, 1).subscribe({ next: (e) => this.estimate.set(e), error: () => this.estimate.set(null) }),
      );
    });
  }

  protected onMode(event: Event): void {
    this.mode.set((event.target as HTMLSelectElement).value as StoryboardRequest['mode']);
  }

  protected onVariations(event: Event): void {
    this.variations.set(Number((event.target as HTMLSelectElement).value));
  }

  protected onQuality(event: Event): void {
    this.quality.set((event.target as HTMLSelectElement).value as Quality);
  }

  protected togglePick(id: string, on: boolean): void {
    this.picked.update((l) => (on ? [...l.filter((x) => x !== id), id] : l.filter((x) => x !== id)));
  }

  protected generate(): void {
    const chosen = this.picked();
    this.store.startJob(
      this.api.generateStoryboard(this.store.id(), {
        scene_ids: chosen.length ? chosen : null,
        mode: this.mode(),
        variations: this.mode() === 'variacoes' ? this.variations() : 1,
        quality: this.quality(),
        seed: parseSeed(this.seed()),
      }),
    );
  }
}
