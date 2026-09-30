import { ChangeDetectionStrategy, Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../../core/api.service';
import { durationLimit, matchCharacters } from '../../../core/match';
import { TPipe } from '../../../core/i18n/t.pipe';
import { Character, Project } from '../../../core/models';
import { CharacterPickerComponent } from '../../../ui/character-picker';
import { FieldComponent } from '../../../ui/field';
import { IconComponent } from '../../../ui/icon';
import { SectionComponent } from '../../../ui/section';
import { ProjectStore } from '../project.store';
import { StageApprovalComponent } from './stage-approval';

interface Draft {
  title: string;
  theme: string;
  settings: string;
  story: string;
  music: string;
  notes: string;
  seconds: number;
  characterIds: string[];
}

function draftOf(project: Project): Draft {
  const s = project.story;
  return {
    title: project.title,
    theme: s.theme ?? '',
    settings: s.settings ?? '',
    story: s.story ?? '',
    music: s.music ?? '',
    notes: s.notes ?? '',
    seconds: project.target_duration_s,
    characterIds: [...project.character_ids],
  };
}

/** Etapa 1: o enredo e quem aparece nele. Editar a história depois de aprovar volta o roteiro para «não aprovado». */
@Component({
  selector: 'fab-etapa-enredo',
  imports: [RouterLink, TPipe, CharacterPickerComponent, FieldComponent, IconComponent, SectionComponent, StageApprovalComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (draft(); as d) {
      <fab-section headingId="enredo" [title]="'proj.stage.enredo' | t" [hint]="'proj.enredo.hint' | t">
        <div class="grid gap-5">
          <fab-field [label]="'criar.f.title' | t" [maxlength]="160" [value]="d.title" (valueChange)="patch('title', $event)" />
          <fab-field
            [label]="'criar.f.story' | t"
            [multiline]="true"
            [rows]="9"
            [required]="true"
            [maxlength]="12000"
            [value]="d.story"
            (valueChange)="patch('story', $event)"
          />
          <div class="field-row">
            <fab-field [label]="'criar.f.theme' | t" [maxlength]="400" [value]="d.theme" (valueChange)="patch('theme', $event)" />
            <fab-field [label]="'criar.f.settings' | t" [maxlength]="600" [value]="d.settings" (valueChange)="patch('settings', $event)" />
          </div>
          <div class="field-row">
            <fab-field [label]="'criar.f.music' | t" [maxlength]="400" [value]="d.music" (valueChange)="patch('music', $event)" />
            <fab-field [label]="'criar.f.notes' | t" [maxlength]="1500" [value]="d.notes" (valueChange)="patch('notes', $event)" />
          </div>
          <div class="field">
            <label class="field-label" for="enredo-seconds">{{ 'criar.f.duration' | t }}: {{ d.seconds }} s</label>
            <input id="enredo-seconds" type="range" min="15" [max]="limit()" step="5" [value]="d.seconds" (input)="onSeconds($event)" />
            <span class="field-hint">{{ 'criar.f.duration.hint' | t: { max: limit() } }}</span>
          </div>

          <fab-character-picker
            [characters]="library()"
            [selected]="d.characterIds"
            (selectedChange)="patch('characterIds', $event)"
            [max]="8"
            [requireCutout]="true"
            [label]="'criar.f.characters' | t"
          />
          @for (name of missingNames(); track name) {
            <p class="banner" role="status">
              {{ 'criar.missing' | t: { names: name } }}
              <a [routerLink]="['/personagens']" [queryParams]="{ nome: name }" fragment="novo">{{ 'criar.missing.create' | t: { name } }}</a>
            </p>
          }
          @for (w of styleWarnings(); track w.character_id) {
            <p class="banner" role="status">
              {{ w.message }}
              <a [routerLink]="['/personagens', w.character_id]">{{ 'criar.mismatch.link' | t }}</a>
            </p>
          }

          <div class="flex flex-wrap items-center gap-3">
            <button type="button" class="btn btn-primary" (click)="save()" [disabled]="store.busy() || !dirty() || !d.story.trim()">
              <fab-icon name="check" [size]="18" />
              {{ 'proj.enredo.save' | t }}
            </button>
            @if (dirty() && anyApproved()) {
              <span class="text-small text-ink-soft">{{ 'proj.enredo.reopens' | t }}</span>
            }
          </div>
        </div>
      </fab-section>
      <fab-stage-approval stage="enredo" />
    }
  `,
})
export class EtapaEnredo {
  protected readonly store = inject(ProjectStore);
  private readonly api = inject(ApiService);

  protected readonly library = signal<Character[]>([]);
  protected readonly draft = signal<Draft | null>(null);

  protected readonly limit = computed(() => durationLimit(this.store.project()?.format ?? 'short'));
  protected readonly dirty = computed(() => {
    const p = this.store.project();
    const d = this.draft();
    return !!p && !!d && JSON.stringify(d) !== JSON.stringify(draftOf(p));
  });
  protected readonly anyApproved = computed(() => this.store.stages().some((s) => s.approved && s.id !== 'enredo') || !!this.store.stage('enredo')?.approved);
  protected readonly styleWarnings = computed(() => this.store.detail()?.style_warnings ?? []);
  protected readonly missingNames = computed(() => {
    const names = this.store.project()?.story.characters ?? [];
    const chosen = this.store.characters();
    return matchCharacters(names, [...chosen, ...this.library()]).missing;
  });

  constructor() {
    this.api.characters().subscribe({ next: (r) => this.library.set(r.items), error: () => undefined });
    effect(() => {
      const project = this.store.project();
      if (project && !untracked(() => this.dirty())) this.draft.set(draftOf(project));
    });
  }

  protected patch<K extends keyof Draft>(key: K, value: Draft[K]): void {
    this.draft.update((d) => (d ? { ...d, [key]: value } : d));
  }

  protected onSeconds(event: Event): void {
    this.patch('seconds', Number((event.target as HTMLInputElement).value));
  }

  protected save(): void {
    const d = this.draft();
    if (!d) return;
    this.store.run(
      this.api.updateProject(this.store.id(), {
        title: d.title.trim() || undefined,
        target_duration_s: d.seconds,
        character_ids: d.characterIds,
        story: { title: d.title, story: d.story, theme: d.theme, settings: d.settings, music: d.music, notes: d.notes },
      }),
      (detail) => this.store.applyDetail(detail),
    );
  }
}
