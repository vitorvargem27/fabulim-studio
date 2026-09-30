import { ChangeDetectionStrategy, Component, computed, effect, inject, input, output, signal, untracked } from '@angular/core';

import { ApiService, Quality } from '../../../core/api.service';
import { TPipe } from '../../../core/i18n/t.pipe';
import { LayoutItem, Scene } from '../../../core/models';
import { BadgeComponent } from '../../../ui/badge';
import { IconComponent } from '../../../ui/icon';
import { MediaTileComponent } from '../../../ui/media-tile';
import { ProjectStore } from '../project.store';

/** Uma cena no storyboard: a imagem-chave (cenário + personagens), os cenários alternativos e a posição de cada personagem. */
@Component({
  selector: 'fab-scene-storyboard',
  imports: [TPipe, BadgeComponent, IconComponent, MediaTileComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <article class="border-2 border-ink bg-panel">
      <header class="flex flex-wrap items-center gap-x-4 gap-y-2 border-b-2 border-ink bg-wash px-3 py-2">
        <label class="inline-flex items-center gap-2 font-normal">
          <input type="checkbox" [checked]="picked()" (change)="pick.emit($any($event.target).checked)" [attr.aria-label]="'proj.sb.pick' | t: { n: scene().order }" />
        </label>
        <span class="bg-accent px-2 py-0.5 font-mono text-meta font-extrabold text-on-accent">{{ scene().order }}</span>
        <strong class="min-w-0 flex-1 font-display text-[1.125rem] font-semibold">{{ scene().data.title || ('proj.scene.untitled' | t) }}</strong>
        <fab-badge [tone]="scene().data.approved['storyboard'] ? 'ok' : scene().data.background ? 'info' : 'neutral'">
          {{ (scene().data.approved['storyboard'] ? 'proj.scene.approved' : scene().data.background ? 'proj.sb.ready' : 'proj.sb.none') | t }}
        </fab-badge>
      </header>

      <div class="grid gap-4 p-3 md:grid-cols-[minmax(0,17rem)_minmax(0,1fr)]">
        <div>
          @if (scene().keyframe; as key) {
            <fab-media-tile [media]="key" [caption]="scene().character_names.join(', ')" />
          } @else {
            <div class="grid aspect-video place-items-center bg-wash p-4 text-center text-small text-ink-soft">{{ 'proj.sb.noimage' | t }}</div>
          }
        </div>

        <div class="grid content-start gap-3">
          <p class="font-text text-small">{{ scene().data.visual }}</p>
          <div class="flex flex-wrap gap-2">
            <button type="button" class="btn btn-sm" (click)="regenerate('regerar')" [disabled]="busy()">
              <fab-icon name="refresh" [size]="16" />
              {{ (scene().data.background ? 'proj.sb.again' : 'proj.sb.generate') | t }}
            </button>
            @if (scene().data.background) {
              <button type="button" class="btn btn-sm" (click)="regenerate('variacoes')" [disabled]="busy()">{{ 'proj.sb.more' | t }}</button>
              <button type="button" class="btn btn-sm" (click)="recompose()" [disabled]="busy()">{{ 'proj.sb.recompose' | t }}</button>
            }
            <button
              type="button"
              class="btn btn-sm btn-primary"
              (click)="store.approveScene(scene(), 'storyboard', !scene().data.approved['storyboard'])"
              [disabled]="busy() || (!scene().data.background && !scene().data.approved['storyboard'])"
            >
              {{ (scene().data.approved['storyboard'] ? 'proj.scene.unapprove' : 'proj.scene.approve') | t }}
            </button>
          </div>

          @if (scene().candidate_media.length > 1) {
            <div class="grid gap-2">
              <span class="field-label">{{ 'proj.sb.candidates' | t }}</span>
              <div class="grid grid-cols-[repeat(auto-fill,minmax(8rem,1fr))] gap-2">
                @for (media of scene().candidate_media; track media.id) {
                  <fab-media-tile [media]="media" [selected]="media.id === scene().data.background?.media_id">
                    @if (media.id === scene().data.background?.media_id) {
                      <button type="button" class="btn btn-sm" disabled>{{ 'proj.sb.chosen' | t }}</button>
                    } @else {
                      <button type="button" class="btn btn-sm" (click)="useBackground(media.id)" [disabled]="busy()">{{ 'proj.sb.use' | t }}</button>
                    }
                  </fab-media-tile>
                }
              </div>
            </div>
          }

          @if (layout().length) {
            <details class="border-2 border-rule-soft p-3">
              <summary class="cursor-pointer font-ui font-bold">{{ 'proj.layout.title' | t }}</summary>
              <div class="mt-3 grid gap-4">
                <p class="text-small text-ink-soft">{{ 'proj.layout.hint' | t }}</p>
                @for (item of layout(); track item.personagem_id; let i = $index) {
                  <fieldset class="m-0 grid min-w-0 gap-3 border-2 border-rule-soft p-3">
                    <legend class="px-1 font-display font-semibold">{{ nameOf(item.personagem_id) }}</legend>
                    <div class="field-row">
                      <div class="field">
                        <label class="field-label" [attr.for]="uid + '-x' + i">{{ 'proj.layout.x' | t }}: {{ item.x }}</label>
                        <input [id]="uid + '-x' + i" type="range" min="0" max="1" step="0.02" [value]="item.x" (input)="set(i, 'x', $event)" />
                      </div>
                      <div class="field">
                        <label class="field-label" [attr.for]="uid + '-y' + i">{{ 'proj.layout.y' | t }}: {{ item.base_y }}</label>
                        <input [id]="uid + '-y' + i" type="range" min="0.5" max="1" step="0.02" [value]="item.base_y" (input)="set(i, 'base_y', $event)" />
                      </div>
                      <div class="field">
                        <label class="field-label" [attr.for]="uid + '-h' + i">{{ 'proj.layout.size' | t }}: {{ item.altura }}</label>
                        <input [id]="uid + '-h' + i" type="range" min="0.15" max="0.9" step="0.02" [value]="item.altura" (input)="set(i, 'altura', $event)" />
                      </div>
                    </div>
                    <div class="field-row">
                      <div class="field">
                        <label class="field-label" [attr.for]="uid + '-p' + i">{{ 'proj.layout.pose' | t }}</label>
                        <select [id]="uid + '-p' + i" (change)="setText(i, 'pose', $event)">
                          <option value="" [selected]="!item.pose">{{ 'proj.layout.auto' | t }}</option>
                          @for (slot of slotsOf(item.personagem_id); track slot) {
                            <option [value]="slot" [selected]="slot === item.pose">{{ 'personagens.slot.' + slot | t }}</option>
                          }
                        </select>
                      </div>
                      <div class="field">
                        <label class="field-label" [attr.for]="uid + '-a' + i">{{ 'proj.layout.action' | t }}</label>
                        <select [id]="uid + '-a' + i" (change)="setText(i, 'acao', $event)">
                          <option value="" [selected]="!item.acao">{{ 'proj.layout.auto' | t }}</option>
                          @for (a of actions(); track a) {
                            <option [value]="a" [selected]="a === item.acao">{{ actionLabel(a) }}</option>
                          }
                        </select>
                      </div>
                      <div class="field">
                        <label class="field-label" [attr.for]="uid + '-e' + i">{{ 'proj.layout.entrance' | t }}</label>
                        <select [id]="uid + '-e' + i" (change)="setText(i, 'entrada', $event)">
                          <option value="" [selected]="!item.entrada">{{ 'proj.layout.auto' | t }}</option>
                          @for (e of entrances(); track e) {
                            <option [value]="e" [selected]="e === item.entrada">{{ e }}</option>
                          }
                        </select>
                      </div>
                    </div>
                    <label class="inline-flex items-center gap-2 font-normal">
                      <input type="checkbox" [checked]="item.espelhar" (change)="flip(i, $event)" />
                      {{ 'proj.layout.flip' | t }}
                    </label>
                  </fieldset>
                }
                <div class="flex flex-wrap gap-2">
                  <button type="button" class="btn btn-sm btn-primary" (click)="applyLayout()" [disabled]="busy() || !layoutDirty()">{{ 'proj.layout.apply' | t }}</button>
                  @if (layoutDirty()) {
                    <button type="button" class="btn btn-sm btn-quiet" (click)="resetLayout()">{{ 'proj.scene.discard' | t }}</button>
                  }
                </div>
              </div>
            </details>
          }
        </div>
      </div>
    </article>
  `,
})
export class SceneStoryboardComponent {
  readonly scene = input.required<Scene>();
  readonly picked = input(false);
  readonly quality = input<Quality>('padrao');
  /** Marcar ou desmarcar esta cena para «gerar só as escolhidas». */
  readonly pick = output<boolean>();

  protected readonly store = inject(ProjectStore);
  private readonly api = inject(ApiService);

  protected readonly uid = `sb-${Math.random().toString(36).slice(2, 8)}`;
  /** As posições em edição; `null` até chegarem do servidor (assim o começo não conta como «mudança não aplicada»). */
  private readonly editing = signal<LayoutItem[] | null>(null);
  protected readonly layout = computed(() => this.editing() ?? []);
  protected readonly busy = computed(() => this.store.busy() || this.store.hasActive('projeto.storyboard'));
  protected readonly layoutDirty = computed(() => {
    const atual = this.editing();
    return atual !== null && JSON.stringify(atual) !== JSON.stringify(this.scene().layout);
  });
  protected readonly actions = computed(() => this.store.options()?.actions ?? []);
  protected readonly entrances = computed(() => this.store.options()?.entrances ?? []);

  constructor() {
    effect(() => {
      const scene = this.scene();
      if (!untracked(() => this.layoutDirty())) this.editing.set(scene.layout.map((i) => ({ ...i })));
    });
  }

  protected nameOf(id: string): string {
    return this.store.characters().find((c) => c.id === id)?.name ?? '?';
  }

  protected slotsOf(id: string): string[] {
    return this.store.characters().find((c) => c.id === id)?.cutout_slots ?? [];
  }

  protected actionLabel(action: string): string {
    return this.store.options()?.action_labels[action] ?? action;
  }

  protected set(index: number, key: 'x' | 'base_y' | 'altura', event: Event): void {
    const value = Number((event.target as HTMLInputElement).value);
    this.editing.update((l) => (l ?? []).map((item, i) => (i === index ? { ...item, [key]: value } : item)));
  }

  protected setText(index: number, key: 'pose' | 'acao' | 'entrada', event: Event): void {
    const value = (event.target as HTMLSelectElement).value || null; // «automático» é null, como no servidor
    this.editing.update((l) => (l ?? []).map((item, i) => (i === index ? { ...item, [key]: value } : item)));
  }

  protected flip(index: number, event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    this.editing.update((l) => (l ?? []).map((item, i) => (i === index ? { ...item, espelhar: checked } : item)));
  }

  protected resetLayout(): void {
    this.editing.set(this.scene().layout.map((i) => ({ ...i })));
  }

  protected applyLayout(): void {
    this.store.run(this.api.setLayout(this.store.id(), this.scene().id, this.layout() as unknown as Record<string, unknown>[]), (r) => {
      this.store.applyScene(r);
      this.editing.set(r.scene.layout.map((i) => ({ ...i })));
    });
  }

  protected regenerate(mode: 'regerar' | 'variacoes'): void {
    this.store.startJob(
      this.api.generateStoryboard(this.store.id(), {
        scene_ids: [this.scene().id],
        mode,
        variations: mode === 'variacoes' ? 2 : 1,
        quality: this.quality(),
      }),
    );
  }

  protected useBackground(mediaId: string): void {
    this.store.run(this.api.chooseBackground(this.store.id(), this.scene().id, mediaId), (r) => this.store.applyScene(r));
  }

  protected recompose(): void {
    this.store.run(this.api.recomposeScene(this.store.id(), this.scene().id), (r) => this.store.applyScene(r));
  }
}
