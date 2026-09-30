import { ChangeDetectionStrategy, Component, computed, effect, inject, signal, untracked } from '@angular/core';

import { ApiService, Transition } from '../../../core/api.service';
import { TPipe } from '../../../core/i18n/t.pipe';
import { downloadUrl } from '../../../core/viewer.service';
import { VoiceOption, VoiceSetting } from '../../../core/models';
import { IconComponent } from '../../../ui/icon';
import { MediaTileComponent } from '../../../ui/media-tile';
import { SectionComponent } from '../../../ui/section';
import { ProjectStore } from '../project.store';
import { StageApprovalComponent } from './stage-approval';

const TRANSITIONS: Transition[] = ['corte', 'fade', 'suave'];
const DEFAULT_NARRATOR: Record<string, VoiceSetting> = {
  'pt-BR': { id: 'pm_alex', speed: 0.95, pitch: 1 },
  en: { id: 'am_adam', speed: 0.95, pitch: 1 },
};

interface AudioDraft {
  musicEnabled: boolean;
  musicStyle: string;
  musicVolume: number;
  musicSeed: number;
  transition: Transition;
  narrator: VoiceSetting;
  voices: Record<string, string>;
}

/** Etapa 5: o áudio. Vozes dos personagens e do narrador (Kokoro, local), música instrumental gerada por código e efeitos sonoros, com o volume acertado para -14 LUFS. */
@Component({
  selector: 'fab-etapa-audio',
  imports: [TPipe, IconComponent, MediaTileComponent, SectionComponent, StageApprovalComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (draft(); as d) {
      <fab-section headingId="audio" [title]="'proj.stage.audio' | t" [hint]="'proj.audio.hint' | t">
        <div class="grid gap-6">
          <fieldset class="m-0 grid min-w-0 gap-4 border-2 border-rule-soft p-4">
            <legend class="px-1 font-display text-[1.125rem] font-semibold">{{ 'proj.audio.music' | t }}</legend>
            <label class="inline-flex items-center gap-2 font-normal">
              <input type="checkbox" [checked]="d.musicEnabled" (change)="patch('musicEnabled', $any($event.target).checked)" />
              {{ 'proj.audio.music.on' | t }}
            </label>
            @if (d.musicEnabled) {
              <div class="field-row">
                <div class="field">
                  <label class="field-label" for="music-style">{{ 'proj.audio.style' | t }}</label>
                  <select id="music-style" (change)="patch('musicStyle', $any($event.target).value)">
                    @for (s of styles(); track s.id) {
                      <option [value]="s.id" [selected]="s.id === d.musicStyle">{{ s.label }} ({{ s.bpm }} bpm)</option>
                    }
                  </select>
                </div>
                <div class="field">
                  <label class="field-label" for="music-volume">{{ 'proj.audio.volume' | t }}: {{ percent(d.musicVolume) }}</label>
                  <input id="music-volume" type="range" min="0" max="0.6" step="0.02" [value]="d.musicVolume" (input)="patch('musicVolume', +$any($event.target).value)" />
                  <span class="field-hint">{{ 'proj.audio.volume.hint' | t }}</span>
                </div>
                <div class="field">
                  <span class="field-label">{{ 'proj.audio.melody' | t }} #{{ d.musicSeed }}</span>
                  <div><button type="button" class="btn btn-sm" (click)="anotherMelody()"><fab-icon name="refresh" [size]="16" /> {{ 'proj.audio.melody.other' | t }}</button></div>
                </div>
              </div>
            }
          </fieldset>

          <fieldset class="m-0 grid min-w-0 gap-4 border-2 border-rule-soft p-4">
            <legend class="px-1 font-display text-[1.125rem] font-semibold">{{ 'proj.audio.voices' | t }}</legend>
            <div class="field-row">
              <div class="field">
                <label class="field-label" for="narrator-voice">{{ 'proj.audio.narrator' | t }}</label>
                <select id="narrator-voice" (change)="patchNarrator('id', $any($event.target).value)">
                  @for (v of voices(); track v.id) {
                    <option [value]="v.id" [selected]="v.id === d.narrator.id">{{ v.nome }}</option>
                  }
                </select>
              </div>
              <div class="field">
                <label class="field-label" for="narrator-speed">{{ 'personagens.voice.speed' | t }}: {{ d.narrator.speed }}×</label>
                <input id="narrator-speed" type="range" min="0.6" max="1.4" step="0.05" [value]="d.narrator.speed" (input)="patchNarrator('speed', +$any($event.target).value)" />
              </div>
              <div class="field">
                <label class="field-label" for="narrator-pitch">{{ 'personagens.voice.pitch' | t }}: {{ d.narrator.pitch }}×</label>
                <input id="narrator-pitch" type="range" min="0.7" max="1.4" step="0.05" [value]="d.narrator.pitch" (input)="patchNarrator('pitch', +$any($event.target).value)" />
              </div>
            </div>
            @if (store.characters().length) {
              <div class="grid gap-3">
                <span class="field-label">{{ 'proj.audio.characters' | t }}</span>
                @for (c of store.characters(); track c.id) {
                  <div class="grid items-center gap-2 md:grid-cols-[minmax(0,12rem)_minmax(0,1fr)]">
                    <label class="font-bold" [attr.for]="'voice-' + c.id">{{ c.name }}</label>
                    <select [id]="'voice-' + c.id" (change)="patchVoice(c.id, $any($event.target).value)">
                      <option value="" [selected]="!d.voices[c.id]">{{ 'proj.audio.voice.own' | t }}</option>
                      @for (v of voices(); track v.id) {
                        <option [value]="v.id" [selected]="v.id === d.voices[c.id]">{{ v.nome }}</option>
                      }
                    </select>
                  </div>
                }
              </div>
            }
          </fieldset>

          <div class="field-row">
            <div class="field">
              <label class="field-label" for="audio-transition">{{ 'clipes.join.transition' | t }}</label>
              <select id="audio-transition" (change)="patch('transition', $any($event.target).value)">
                @for (t of transitions; track t) {
                  <option [value]="t" [selected]="t === d.transition">{{ 'clipes.transition.' + t | t }}</option>
                }
              </select>
              <span class="field-hint">{{ 'proj.audio.transition.hint' | t }}</span>
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-3">
            <button type="button" class="btn" (click)="save()" [disabled]="store.busy() || !dirty()">{{ 'proj.audio.save' | t }}</button>
            <button type="button" class="btn btn-primary" (click)="generate()" [disabled]="store.busy() || store.hasActive('projeto.audio') || dirty()">
              <fab-icon name="play" [size]="18" />
              {{ (files().mix ? 'proj.audio.again' : 'proj.audio.generate') | t }}
            </button>
            @if (dirty()) {
              <span class="text-small text-ink-soft">{{ 'proj.audio.save.first' | t }}</span>
            }
          </div>
        </div>
      </fab-section>

      @if (files().mix; as mix) {
        <fab-section headingId="audio-pronto" [title]="'proj.audio.ready' | t" [hint]="'proj.audio.ready.hint' | t">
          <div class="grid gap-4 md:grid-cols-2">
            <div class="grid gap-1"><span class="field-label">{{ 'proj.audio.mix' | t }}</span><fab-media-tile [media]="mix" /></div>
            @if (files().music; as music) {
              <div class="grid gap-1"><span class="field-label">{{ 'proj.audio.music' | t }}</span><fab-media-tile [media]="music" /></div>
            }
          </div>
          @if (files().subtitles; as srt) {
            <p class="mt-4"><a class="btn btn-sm" [href]="download(srt, 'legendas.srt')" download>{{ 'proj.audio.srt' | t }}</a></p>
          }
        </fab-section>
      }
      <fab-stage-approval stage="audio" />
    }
  `,
})
export class EtapaAudio {
  protected readonly store = inject(ProjectStore);
  private readonly api = inject(ApiService);

  protected readonly transitions = TRANSITIONS;
  protected readonly download = downloadUrl;
  protected readonly draft = signal<AudioDraft | null>(null);

  protected readonly files = computed(() => this.store.detail()?.files ?? { final: null, subtitles: null, mix: null, music: null, thumbnails: [] });
  protected readonly styles = computed(() => this.store.options()?.music_styles ?? []);
  protected readonly voices = computed<VoiceOption[]>(() => {
    const language = this.store.project()?.language ?? 'pt-BR';
    return this.store.options()?.voices[language] ?? [];
  });
  protected readonly dirty = computed(() => {
    const p = this.store.project();
    const d = this.draft();
    return !!p && !!d && JSON.stringify(d) !== JSON.stringify(this.fromProject());
  });

  constructor() {
    effect(() => {
      const project = this.store.project();
      this.store.options(); // as vozes e os estilos dependem das opções
      if (project && !untracked(() => this.dirty())) this.draft.set(this.fromProject());
    });
  }

  private fromProject(): AudioDraft {
    const p = this.store.project();
    const music = p?.music ?? {};
    const settings = p?.settings ?? {};
    const language = p?.language ?? 'pt-BR';
    const narrator = (settings['narrator'] as VoiceSetting | undefined) ?? DEFAULT_NARRATOR[language] ?? DEFAULT_NARRATOR['pt-BR'];
    const overrides = (settings['voices'] as Record<string, VoiceSetting> | undefined) ?? {};
    return {
      musicEnabled: music.enabled ?? true,
      musicStyle: music.style ?? this.store.options()?.music_styles[0]?.id ?? 'alegre',
      musicVolume: music.volume ?? 0.22,
      musicSeed: music.seed ?? 1,
      transition: ((settings['transition'] as Transition | undefined) ?? 'corte'),
      narrator: { id: narrator.id, speed: narrator.speed, pitch: narrator.pitch },
      voices: Object.fromEntries(Object.entries(overrides).map(([id, v]) => [id, v.id])),
    };
  }

  protected percent(value: number): string {
    return `${Math.round(value * 100)}%`;
  }

  protected patch<K extends keyof AudioDraft>(key: K, value: AudioDraft[K]): void {
    this.draft.update((d) => (d ? { ...d, [key]: value } : d));
  }

  protected patchNarrator<K extends keyof VoiceSetting>(key: K, value: VoiceSetting[K]): void {
    this.draft.update((d) => (d ? { ...d, narrator: { ...d.narrator, [key]: value } } : d));
  }

  protected patchVoice(characterId: string, voiceId: string): void {
    this.draft.update((d) => {
      if (!d) return d;
      const voices = { ...d.voices };
      if (voiceId) voices[characterId] = voiceId;
      else delete voices[characterId];
      return { ...d, voices };
    });
  }

  protected anotherMelody(): void {
    this.patch('musicSeed', Math.floor(Math.random() * 999_000) + 1);
  }

  protected save(): void {
    const d = this.draft();
    if (!d) return;
    const voices = Object.fromEntries(Object.entries(d.voices).map(([id, voice]) => [id, { id: voice, speed: 1, pitch: 1 }]));
    this.store.run(
      this.api.updateProject(this.store.id(), {
        music: { enabled: d.musicEnabled, style: d.musicStyle, volume: d.musicVolume, seed: d.musicSeed },
        settings: { transition: d.transition, narrator: d.narrator, voices },
      }),
      (detail) => this.store.applyDetail(detail),
    );
  }

  protected generate(): void {
    this.store.startJob(this.api.generateAudio(this.store.id(), this.draft()?.transition ?? null));
  }
}
