import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked } from '@angular/core';

import { ApiService } from '../../../core/api.service';
import { I18nService } from '../../../core/i18n/i18n.service';
import { TPipe } from '../../../core/i18n/t.pipe';
import { DialogueLine, Emotion, Framing, Scene, SceneData, SceneVersion } from '../../../core/models';
import { formatDateTime } from '../../../core/format';
import { BadgeComponent } from '../../../ui/badge';
import { FieldComponent } from '../../../ui/field';
import { IconComponent } from '../../../ui/icon';
import { ProjectStore } from '../project.store';

export const SFX = ['pop', 'boing', 'brilho', 'splash', 'whoosh', 'ding', 'passos', 'chuva'];
const FRAMINGS: Framing[] = ['aberto', 'medio', 'proximo'];
const EMOTIONS: Emotion[] = ['neutro', 'feliz', 'triste', 'surpreso', 'sono', 'bravo'];

type EditableKey = 'title' | 'duration_s' | 'visual' | 'action' | 'setting' | 'framing' | 'emotion' | 'camera' | 'characters' | 'narration' | 'dialogue' | 'lyrics' | 'sfx';
export type Draft = Pick<SceneData, EditableKey>;
const KEYS: EditableKey[] = ['title', 'duration_s', 'visual', 'action', 'setting', 'framing', 'emotion', 'camera', 'characters', 'narration', 'dialogue', 'lyrics', 'sfx'];

export function draftOfScene(data: SceneData): Draft {
  return {
    title: data.title,
    duration_s: data.duration_s,
    visual: data.visual,
    action: data.action,
    setting: data.setting,
    framing: data.framing,
    emotion: data.emotion,
    camera: data.camera,
    characters: [...data.characters],
    narration: data.narration,
    dialogue: data.dialogue.map((d) => ({ ...d })),
    lyrics: data.lyrics,
    sfx: [...data.sfx],
  };
}

/** Só os campos que o usuário mudou (a edição manda apenas isso, e o servidor decide o que precisa ser refeito). */
export function changesOf(draft: Draft, data: SceneData): Partial<SceneData> {
  const changes: Record<string, unknown> = {};
  for (const key of KEYS) if (JSON.stringify(draft[key]) !== JSON.stringify(data[key])) changes[key] = draft[key];
  return changes as Partial<SceneData>;
}

/**
 * Uma cena do roteiro: resumo, aprovação, ordem, histórico de versões e o formulário completo (texto, falas, personagens,
 * câmera e efeitos). Cada edição vira uma versão nova: nada se perde e dá para voltar.
 */
@Component({
  selector: 'fab-scene-editor',
  imports: [TPipe, BadgeComponent, FieldComponent, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <article class="border-2 border-ink bg-panel">
      <header class="flex flex-wrap items-center gap-x-4 gap-y-2 border-b-2 border-ink bg-wash px-3 py-2">
        <span class="bg-accent px-2 py-0.5 font-mono text-meta font-extrabold text-on-accent">{{ scene().order }}</span>
        <strong class="min-w-0 flex-1 font-display text-[1.125rem] font-semibold">{{ scene().data.title || ('proj.scene.untitled' | t) }}</strong>
        <span class="text-small text-ink-soft">{{ scene().effective_duration_s }} s</span>
        @if (scene().data.suggestion) {
          <fab-badge tone="warning">{{ 'proj.scene.suggestion' | t }}</fab-badge>
        }
        <fab-badge [tone]="scene().data.approved['roteiro'] ? 'ok' : 'neutral'">{{ (scene().data.approved['roteiro'] ? 'proj.scene.approved' : 'proj.scene.pending') | t }}</fab-badge>
      </header>

      <div class="grid gap-3 p-3">
        @if (!open()) {
          <p class="font-text text-small">
            @if (scene().data.narration) {
              <em>“{{ scene().data.narration }}”</em>
            } @else {
              {{ scene().data.visual }}
            }
          </p>
          <p class="text-small text-ink-soft">{{ scene().character_names.join(', ') || ('proj.scene.nochars' | t) }}</p>
        } @else if (draft(); as d) {
          @if (scene().data.suggestion && scene().data.suggestion_notes) {
            <p class="banner" role="status">{{ scene().data.suggestion_notes }}</p>
          }
          <div class="field-row">
            <fab-field [label]="'proj.scene.title' | t" [maxlength]="120" [value]="d.title" (valueChange)="patch('title', $event)" />
            <div class="field">
              <label class="field-label" [attr.for]="uid + '-dur'">{{ 'proj.scene.duration' | t }}: {{ d.duration_s }} s</label>
              <input [id]="uid + '-dur'" type="range" min="3" max="10" step="0.5" [value]="d.duration_s" (input)="onDuration($event)" />
              <span class="field-hint">{{ 'proj.scene.duration.hint' | t }}</span>
            </div>
          </div>
          <fab-field [label]="'proj.scene.visual' | t" [hint]="'proj.scene.visual.hint' | t" [multiline]="true" [rows]="2" [maxlength]="600" [value]="d.visual" (valueChange)="patch('visual', $event)" />
          <div class="field-row">
            <fab-field [label]="'proj.scene.setting' | t" [maxlength]="200" [value]="d.setting" (valueChange)="patch('setting', $event)" />
            <fab-field [label]="'proj.scene.action' | t" [hint]="'proj.scene.action.hint' | t" [maxlength]="400" [value]="d.action" (valueChange)="patch('action', $event)" />
          </div>
          <div class="field-row">
            <div class="field">
              <label class="field-label" [attr.for]="uid + '-framing'">{{ 'proj.scene.framing' | t }}</label>
              <select [id]="uid + '-framing'" (change)="onSelect('framing', $event)">
                @for (f of framings; track f) {
                  <option [value]="f" [selected]="f === d.framing">{{ 'proj.framing.' + f | t }}</option>
                }
              </select>
            </div>
            <div class="field">
              <label class="field-label" [attr.for]="uid + '-emotion'">{{ 'proj.scene.emotion' | t }}</label>
              <select [id]="uid + '-emotion'" (change)="onSelect('emotion', $event)">
                @for (e of emotions; track e) {
                  <option [value]="e" [selected]="e === d.emotion">{{ 'proj.emotion.' + e | t }}</option>
                }
              </select>
            </div>
            <div class="field">
              <label class="field-label" [attr.for]="uid + '-camera'">{{ 'proj.scene.camera' | t }}</label>
              <select [id]="uid + '-camera'" (change)="onSelect('camera', $event)">
                @for (c of cameras(); track c) {
                  <option [value]="c" [selected]="c === d.camera">{{ cameraLabel(c) }}</option>
                }
              </select>
            </div>
          </div>

          <fieldset class="m-0 min-w-0 border-0 p-0">
            <legend class="field-label mb-2 p-0">{{ 'proj.scene.characters' | t }}</legend>
            <div class="chips">
              @for (c of store.characters(); track c.id) {
                <button type="button" [attr.aria-pressed]="d.characters.includes(c.id)" (click)="toggleCharacter(c.id)">{{ c.name }}</button>
              }
            </div>
          </fieldset>

          <fab-field [label]="'proj.scene.narration' | t" [hint]="'proj.scene.narration.hint' | t" [multiline]="true" [rows]="2" [maxlength]="600" [value]="d.narration" (valueChange)="patch('narration', $event)" />

          <fieldset class="m-0 grid min-w-0 gap-2 border-0 p-0">
            <legend class="field-label mb-1 p-0">{{ 'proj.scene.dialogue' | t }}</legend>
            @for (line of d.dialogue; track $index; let i = $index) {
              <div class="grid gap-2 md:grid-cols-[minmax(0,12rem)_minmax(0,1fr)_auto]">
                <select [attr.aria-label]="'proj.scene.speaker' | t" (change)="onSpeaker(i, $event)">
                  <option value="" [selected]="!line.character_id">{{ 'proj.scene.narrator' | t }}</option>
                  @for (c of store.characters(); track c.id) {
                    <option [value]="c.id" [selected]="c.id === line.character_id">{{ c.name }}</option>
                  }
                </select>
                <input type="text" maxlength="400" [attr.aria-label]="'proj.scene.line' | t" [value]="line.text" (input)="onLine(i, $event)" />
                <button type="button" class="btn btn-icon btn-sm btn-quiet" (click)="removeLine(i)" [attr.aria-label]="'proj.scene.line.remove' | t">
                  <fab-icon name="close" [size]="16" />
                </button>
              </div>
            }
            <div><button type="button" class="btn btn-sm" (click)="addLine()" [disabled]="d.dialogue.length >= 12">{{ 'proj.scene.line.add' | t }}</button></div>
          </fieldset>

          <fab-field [label]="'proj.scene.lyrics' | t" [hint]="'proj.scene.lyrics.hint' | t" [multiline]="true" [rows]="2" [maxlength]="600" [value]="d.lyrics" (valueChange)="patch('lyrics', $event)" />

          <fieldset class="m-0 min-w-0 border-0 p-0">
            <legend class="field-label mb-2 p-0">{{ 'proj.scene.sfx' | t }}</legend>
            <div class="chips">
              @for (s of sfx; track s) {
                <button type="button" [attr.aria-pressed]="d.sfx.includes(s)" (click)="toggleSfx(s)">{{ 'proj.sfx.' + s | t }}</button>
              }
            </div>
          </fieldset>
        }

        <div class="flex flex-wrap items-center gap-2 border-t border-rule-soft pt-3">
          <button type="button" class="btn btn-sm" (click)="open.set(!open())" [attr.aria-expanded]="open()">
            {{ (open() ? 'proj.scene.close' : 'proj.scene.edit') | t }}
          </button>
          @if (open()) {
            <button type="button" class="btn btn-sm btn-primary" (click)="save()" [disabled]="store.busy() || !dirty()">
              <fab-icon name="check" [size]="16" />
              {{ 'proj.scene.save' | t }}
            </button>
            @if (dirty()) {
              <button type="button" class="btn btn-sm btn-quiet" (click)="reset()">{{ 'proj.scene.discard' | t }}</button>
            }
          }
          <button
            type="button"
            class="btn btn-sm"
            (click)="store.approveScene(scene(), 'roteiro', !scene().data.approved['roteiro'])"
            [disabled]="store.busy()"
          >
            {{ (scene().data.approved['roteiro'] ? 'proj.scene.unapprove' : 'proj.scene.approve') | t }}
          </button>
          <span class="flex-1"></span>
          <button type="button" class="btn btn-icon btn-sm btn-quiet" (click)="move(-1)" [disabled]="index() === 0 || store.busy()" [attr.aria-label]="'proj.scene.up' | t"><fab-icon name="arrow-up" [size]="16" /></button>
          <button type="button" class="btn btn-icon btn-sm btn-quiet" (click)="move(1)" [disabled]="index() === count() - 1 || store.busy()" [attr.aria-label]="'proj.scene.down' | t"><fab-icon name="arrow-down" [size]="16" /></button>
          <button type="button" class="btn btn-sm btn-quiet" (click)="toggleVersions()" [attr.aria-expanded]="showVersions()">
            <fab-icon name="clock" [size]="16" />
            {{ 'proj.scene.versions' | t: { n: scene().version } }}
          </button>
          <button type="button" class="btn btn-icon btn-sm btn-quiet btn-danger" (click)="remove()" [attr.aria-label]="'proj.scene.remove' | t"><fab-icon name="trash" [size]="16" /></button>
        </div>

        @if (showVersions()) {
          <div class="border-2 border-rule-soft bg-wash p-3">
            @if (versions().length) {
              <ul class="rule-list m-0 p-0">
                @for (v of versions(); track v.version) {
                  <li class="flex flex-wrap items-center justify-between gap-2 py-2 text-small">
                    <span>
                      <strong>v{{ v.version }}</strong> · {{ date(v.created_at) }} · {{ v.reason }}
                      @if (v.version === scene().version) {
                        <fab-badge tone="info">{{ 'proj.scene.current' | t }}</fab-badge>
                      }
                    </span>
                    @if (v.version !== scene().version) {
                      <button type="button" class="btn btn-sm" (click)="restore(v)" [disabled]="store.busy()">{{ 'proj.scene.restore' | t }}</button>
                    }
                  </li>
                }
              </ul>
            } @else {
              <p class="text-small text-ink-soft">{{ 'proj.scene.versions.empty' | t }}</p>
            }
          </div>
        }
      </div>
    </article>
  `,
})
export class SceneEditorComponent {
  readonly scene = input.required<Scene>();
  readonly index = input.required<number>();
  readonly count = input.required<number>();

  protected readonly store = inject(ProjectStore);
  private readonly api = inject(ApiService);
  private readonly i18n = inject(I18nService);

  protected readonly framings = FRAMINGS;
  protected readonly emotions = EMOTIONS;
  protected readonly sfx = SFX;
  protected readonly date = formatDateTime;
  protected readonly uid = `scene-${Math.random().toString(36).slice(2, 8)}`;

  protected readonly open = signal(false);
  protected readonly draft = signal<Draft | null>(null);
  protected readonly showVersions = signal(false);
  protected readonly versions = signal<SceneVersion[]>([]);

  protected readonly cameras = computed(() => this.store.options()?.cameras ?? ['parada']);
  protected readonly dirty = computed(() => {
    const d = this.draft();
    return !!d && Object.keys(changesOf(d, this.scene().data)).length > 0;
  });

  constructor() {
    effect(() => {
      const scene = this.scene();
      if (!untracked(() => this.dirty())) this.draft.set(draftOfScene(scene.data));
    });
  }

  protected cameraLabel(camera: string): string {
    return this.store.options()?.camera_labels[camera] ?? camera;
  }

  protected patch<K extends EditableKey>(key: K, value: Draft[K]): void {
    this.draft.update((d) => (d ? { ...d, [key]: value } : d));
  }

  protected onDuration(event: Event): void {
    this.patch('duration_s', Number((event.target as HTMLInputElement).value));
  }

  protected onSelect(key: 'framing' | 'emotion' | 'camera', event: Event): void {
    this.patch(key, (event.target as HTMLSelectElement).value as never);
  }

  protected toggleCharacter(id: string): void {
    const d = this.draft();
    if (!d) return;
    this.patch('characters', d.characters.includes(id) ? d.characters.filter((c) => c !== id) : [...d.characters, id]);
  }

  protected toggleSfx(name: string): void {
    const d = this.draft();
    if (!d) return;
    this.patch('sfx', d.sfx.includes(name) ? d.sfx.filter((s) => s !== name) : [...d.sfx, name].slice(0, 6));
  }

  protected addLine(): void {
    const d = this.draft();
    if (!d) return;
    const first = d.characters[0] ?? null;
    this.patch('dialogue', [...d.dialogue, { character_id: first, text: '' }]);
  }

  protected removeLine(i: number): void {
    const d = this.draft();
    if (d) this.patch('dialogue', d.dialogue.filter((_, k) => k !== i));
  }

  protected onSpeaker(i: number, event: Event): void {
    const value = (event.target as HTMLSelectElement).value || null;
    this.updateLine(i, { character_id: value });
  }

  protected onLine(i: number, event: Event): void {
    this.updateLine(i, { text: (event.target as HTMLInputElement).value });
  }

  private updateLine(i: number, change: Partial<DialogueLine>): void {
    const d = this.draft();
    if (d) this.patch('dialogue', d.dialogue.map((line, k) => (k === i ? { ...line, ...change } : line)));
  }

  protected reset(): void {
    this.draft.set(draftOfScene(this.scene().data));
  }

  protected save(): void {
    const d = this.draft();
    if (!d) return;
    const changes = changesOf(d, this.scene().data);
    if (Object.keys(changes).length === 0) return;
    // linhas de fala vazias não valem: são tiradas antes de mandar
    if (changes.dialogue) changes.dialogue = changes.dialogue.filter((l) => l.text.trim());
    this.store.run(this.api.editScene(this.store.id(), this.scene().id, changes), (r) => {
      this.store.applyScene(r);
      this.draft.set(draftOfScene(r.scene.data));
    });
  }

  protected move(delta: -1 | 1): void {
    const ids = this.store.scenes().map((s) => s.id);
    const from = ids.indexOf(this.scene().id);
    const to = from + delta;
    if (from < 0 || to < 0 || to >= ids.length) return;
    [ids[from], ids[to]] = [ids[to], ids[from]];
    this.store.run(this.api.reorderScenes(this.store.id(), ids), (detail) => this.store.applyDetail(detail));
  }

  protected remove(): void {
    if (!window.confirm(this.i18n.t('proj.scene.remove.confirm', { n: this.scene().order }))) return;
    this.store.run(this.api.deleteScene(this.store.id(), this.scene().id), () => this.store.load(this.store.id()));
  }

  protected toggleVersions(): void {
    const show = !this.showVersions();
    this.showVersions.set(show);
    if (show) this.api.sceneVersions(this.store.id(), this.scene().id).subscribe({ next: (r) => this.versions.set(r.versions), error: () => this.versions.set([]) });
  }

  protected restore(version: SceneVersion): void {
    this.store.run(this.api.restoreScene(this.store.id(), this.scene().id, version.version), (r) => {
      this.store.applyScene(r);
      this.draft.set(draftOfScene(r.scene.data));
      this.showVersions.set(false);
    });
  }
}
