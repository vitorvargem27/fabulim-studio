import { ChangeDetectionStrategy, Component, DestroyRef, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { Observable, Subscription } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { errorMessage, existingId } from '../../core/http-error';
import { I18nService } from '../../core/i18n/i18n.service';
import { TPipe } from '../../core/i18n/t.pipe';
import { JobsService } from '../../core/jobs.service';
import { parseSeed } from '../../core/match';
import { Character, CharacterDetail, CharacterForm, Estimate, Job, Media, SheetSlot, VoiceOption, VoiceSetting } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { BadgeComponent } from '../../ui/badge';
import { EmptyStateComponent } from '../../ui/empty-state';
import { FieldComponent } from '../../ui/field';
import { IconComponent } from '../../ui/icon';
import { JobProgressComponent } from '../../ui/job-progress';
import { MediaTileComponent } from '../../ui/media-tile';
import { PageHeaderComponent } from '../../ui/page-header';
import { SectionComponent } from '../../ui/section';
import { CharacterFormComponent } from './character-form';
import { statusOf } from './personagens.page';

const POSES = ['frente', 'tres_quartos', 'lado'];
const EXPRESSIONS = ['feliz', 'triste', 'surpreso', 'sono', 'bravo'];
const SLOT_ORDER = ['principal', ...POSES, ...EXPRESSIONS];
const QUALITIES = ['rascunho', 'padrao'] as const;
type CharacterQuality = (typeof QUALITIES)[number];

/**
 * Um personagem por dentro: a ficha, as variações para escolher, a folha de referência (PNG transparente de cada pose,
 * que é o que a animação usa), a voz e a versão no outro estilo (2D e 3D).
 */
@Component({
  selector: 'fab-personagem-page',
  imports: [
    RouterLink,
    TPipe,
    BadgeComponent,
    CharacterFormComponent,
    EmptyStateComponent,
    FieldComponent,
    IconComponent,
    JobProgressComponent,
    MediaTileComponent,
    PageHeaderComponent,
    SectionComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './personagem.page.html',
})
export class PersonagemPage {
  /** O id vem da rota (`/personagens/:id`, ligado por `withComponentInputBinding`). */
  readonly id = input.required<string>();

  private readonly api = inject(ApiService);
  private readonly jobs = inject(JobsService);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);
  private readonly i18n = inject(I18nService);

  protected readonly slotChoices = [...POSES, ...EXPRESSIONS];
  protected readonly qualities = QUALITIES;
  protected readonly facings = ['front', 'left', 'right'] as const;

  protected readonly detail = signal<CharacterDetail | null>(null);
  protected readonly missing = signal(false);
  protected readonly related = signal<Character[]>([]);
  protected readonly form = signal<CharacterForm | null>(null);
  protected readonly technical = signal('');
  protected readonly error = signal<string | null>(null);
  protected readonly busy = signal(false);

  // variações
  protected readonly varCount = signal(4);
  protected readonly varQuality = signal<CharacterQuality>('rascunho');
  protected readonly varSeed = signal('');
  // folha
  protected readonly slots = signal<string[]>([...POSES]);
  protected readonly sheetQuality = signal<CharacterQuality>('rascunho');
  // voz
  protected readonly voices = signal<Record<string, VoiceOption[]>>({});
  protected readonly voice = signal<VoiceSetting>({ id: 'pf_dora', speed: 1, pitch: 1 });
  protected readonly testText = signal('');
  // estimativas
  protected readonly estimates = signal<Record<string, Estimate>>({});

  protected readonly character = computed(() => this.detail()?.character ?? null);
  protected readonly status = computed(() => {
    const c = this.character();
    return c ? statusOf(c) : 'choose';
  });
  protected readonly activeJobs = computed<Job[]>(() => {
    const id = this.id();
    return this.jobs.active().filter((j) => j.params['character_id'] === id);
  });
  protected readonly hasActive = (kind: string): boolean => this.activeJobs().some((j) => j.kind === kind);
  protected readonly formDirty = computed(() => {
    const c = this.character();
    const f = this.form();
    return !!c && !!f && JSON.stringify(f) !== JSON.stringify(c.form);
  });
  protected readonly technicalDirty = computed(() => this.technical() !== (this.character()?.technical_prompt ?? ''));
  protected readonly images = computed<Media[]>(() => {
    const d = this.detail();
    return d ? [...d.uploads, ...d.variations] : [];
  });
  protected readonly sheetSlots = computed<SheetSlot[]>(() => {
    const sheet = this.detail()?.sheet ?? [];
    return [...sheet].sort((a, b) => SLOT_ORDER.indexOf(a.slot) - SLOT_ORDER.indexOf(b.slot));
  });
  protected readonly voiceDirty = computed(() => {
    const saved = this.character()?.voice;
    const v = this.voice();
    return !saved || saved.id !== v.id || saved.speed !== v.speed || saved.pitch !== v.pitch;
  });
  protected readonly convertTarget = computed(() => (this.character()?.style === '2D' ? '3D' : '2D'));

  private reloadTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly subs: Subscription[] = [];

  constructor() {
    const destroyed = inject(DestroyRef);
    this.api.characterVoices().subscribe({ next: (r) => this.voices.set(r.voices), error: () => undefined });

    effect(() => {
      const id = this.id();
      untracked(() => this.load(id));
    });

    effect(() => {
      const count = this.varCount();
      const quality = this.varQuality();
      untracked(() => this.estimate('variations', count, quality));
    });
    effect(() => {
      const count = this.slots().length || 1;
      const quality = this.sheetQuality();
      untracked(() => this.estimate('sheet', count, quality));
    });
    untracked(() => this.estimate('conversion', 2, 'rascunho'));

    this.jobs.finished$.pipe(takeUntilDestroyed(destroyed)).subscribe((job) => {
      if (job.params['character_id'] !== this.id()) return;
      this.load(this.id(), true);
      if (job.status === 'failed') this.toast.show(job.error ?? this.i18n.t('personagens.job.failed'), 'error');
    });
    this.jobs.media$.pipe(takeUntilDestroyed(destroyed)).subscribe((event) => {
      if (event.type === 'created' && event.media.owner_id === this.id()) this.reloadSoon();
    });
    destroyed.onDestroy(() => {
      if (this.reloadTimer) clearTimeout(this.reloadTimer);
      this.subs.forEach((s) => s.unsubscribe());
    });
  }

  // --- carregar -----------------------------------------------------------------------------------------------------------

  private load(id: string, keepForm = false): void {
    this.api.character(id).subscribe({
      next: (detail) => {
        if (id !== this.id()) return;
        const first = this.detail()?.character.id !== detail.character.id;
        this.detail.set(detail);
        this.missing.set(false);
        if (first || !keepForm || !this.formDirty()) this.form.set({ ...detail.character.form });
        if (first || !this.technicalDirty()) this.technical.set(detail.character.technical_prompt);
        if (first) {
          this.voice.set({ ...detail.character.voice });
          this.testText.set(this.i18n.t('personagens.voice.sample', { name: detail.character.name }));
        }
        this.loadRelated(detail.character);
      },
      error: () => this.missing.set(true),
    });
  }

  private reloadSoon(): void {
    if (this.reloadTimer) clearTimeout(this.reloadTimer);
    this.reloadTimer = setTimeout(() => this.load(this.id(), true), 400);
  }

  private loadRelated(character: Character): void {
    this.api.characters().subscribe({
      next: (res) =>
        this.related.set(res.items.filter((c) => c.id !== character.id && (c.origin_id === character.id || c.id === character.origin_id))),
      error: () => undefined,
    });
  }

  private estimate(kind: 'variations' | 'conversion' | 'sheet', count: number, quality: CharacterQuality): void {
    this.api.characterEstimate(kind, count, quality).subscribe({
      next: (e) => this.estimates.update((all) => ({ ...all, [kind]: e })),
      error: () => undefined,
    });
  }

  // --- ficha ------------------------------------------------------------------------------------------------------------------

  protected saveForm(): void {
    const form = this.form();
    if (!form) return;
    this.run(this.api.updateCharacter(this.id(), { form }), () => {
      this.toast.show(this.i18n.t('personagens.saved'));
      this.load(this.id());
    });
  }

  protected saveTechnical(): void {
    this.run(this.api.updateCharacter(this.id(), { technical_prompt: this.technical() }), () => {
      this.toast.show(this.i18n.t('personagens.saved'));
      this.load(this.id());
    });
  }

  protected remove(): void {
    const name = this.character()?.name ?? '';
    if (!window.confirm(this.i18n.t('personagens.remove.confirm', { name }))) return;
    this.run(this.api.deleteCharacter(this.id()), () => void this.router.navigate(['/personagens']));
  }

  // --- variações --------------------------------------------------------------------------------------------------------

  protected onCount(event: Event): void {
    const n = Number((event.target as HTMLSelectElement).value);
    this.varCount.set(Math.min(4, Math.max(1, n || 1)));
  }

  protected onVarQuality(event: Event): void {
    this.varQuality.set((event.target as HTMLSelectElement).value as CharacterQuality);
  }

  protected onSheetQuality(event: Event): void {
    this.sheetQuality.set((event.target as HTMLSelectElement).value as CharacterQuality);
  }

  protected generateVariations(): void {
    const technical = this.technicalDirty() ? this.technical().trim() || null : null;
    this.startJob(
      this.api.generateVariations(this.id(), {
        count: this.varCount(),
        quality: this.varQuality(),
        seed: parseSeed(this.varSeed()),
        technical_prompt: technical,
      }),
    );
  }

  protected choose(media: Media): void {
    this.run(this.api.chooseVariation(this.id(), media.id), (res) => {
      if (res.job) this.jobs.merge(res.job);
      this.toast.show(this.i18n.t(res.job ? 'personagens.chosen.cutout' : 'personagens.chosen'));
      this.load(this.id());
    });
  }

  protected isMain(media: Media): boolean {
    return this.character()?.main_image_id === media.id;
  }

  protected retryCutout(): void {
    const main = this.character()?.main_image_id;
    if (!main) return;
    this.run(this.api.chooseVariation(this.id(), main), (res) => {
      if (res.job) this.jobs.merge(res.job);
      else this.toast.show(this.i18n.t('personagens.cutout.none'), 'info');
    });
  }

  // --- folha de referência --------------------------------------------------------------------------------------------------

  protected toggleSlot(slot: string): void {
    this.slots.update((list) => (list.includes(slot) ? list.filter((s) => s !== slot) : [...list, slot]));
  }

  protected generateSheet(): void {
    this.startJob(this.api.generateSheet(this.id(), this.slots(), this.sheetQuality()));
  }

  protected facingOf(cutout: Media): string {
    return String(cutout.metadata['facing'] ?? 'right');
  }

  protected onFacing(cutout: Media, event: Event): void {
    const facing = (event.target as HTMLSelectElement).value as 'front' | 'left' | 'right';
    this.run(this.api.setFacing(this.id(), cutout.id, facing), () => this.load(this.id(), true));
  }

  protected slotDone(slot: string): boolean {
    return this.sheetSlots().some((s) => s.slot === slot && s.cutout !== null);
  }

  // --- voz ---------------------------------------------------------------------------------------------------------------------

  protected languages(): string[] {
    return Object.keys(this.voices());
  }

  protected voiceOptions(language: string): VoiceOption[] {
    return this.voices()[language] ?? [];
  }

  protected onVoice(event: Event): void {
    this.voice.update((v) => ({ ...v, id: (event.target as HTMLSelectElement).value }));
  }

  protected onSpeed(event: Event): void {
    this.voice.update((v) => ({ ...v, speed: Number((event.target as HTMLInputElement).value) }));
  }

  protected onPitch(event: Event): void {
    this.voice.update((v) => ({ ...v, pitch: Number((event.target as HTMLInputElement).value) }));
  }

  protected saveVoice(): void {
    this.run(this.api.setVoice(this.id(), this.voice()), () => {
      this.toast.show(this.i18n.t('personagens.voice.saved'));
      this.load(this.id());
    });
  }

  protected listen(): void {
    this.startJob(this.api.testVoice(this.id(), this.testText().trim(), this.voice()));
  }

  // --- outra versão -------------------------------------------------------------------------------------------------------------

  protected convert(): void {
    this.run(this.api.convertCharacter(this.id(), 2, 'rascunho'), (res) => {
      if (res.job) this.jobs.merge(res.job);
      void this.router.navigate(['/personagens', res.character.id]);
    });
  }

  // --- ajuda ---------------------------------------------------------------------------------------------------------------------

  private startJob(request: Observable<Job>): void {
    this.run(request, (job) => this.jobs.merge(job));
  }

  private run<T>(request: Observable<T>, done: (value: T) => void): void {
    this.error.set(null);
    this.busy.set(true);
    request.subscribe({
      next: (value) => {
        this.busy.set(false);
        done(value);
      },
      error: (e: unknown) => {
        this.busy.set(false);
        this.error.set(errorMessage(e));
        const existing = existingId(e);
        if (existing) void this.router.navigate(['/personagens', existing]);
      },
    });
  }
}
