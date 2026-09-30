import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, computed, effect, inject, input, signal, untracked, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { scrollToId } from '../../core/format';
import { errorMessage, existingId } from '../../core/http-error';
import { I18nService } from '../../core/i18n/i18n.service';
import { TPipe } from '../../core/i18n/t.pipe';
import { JobsService } from '../../core/jobs.service';
import { Character, CharacterForm, Style } from '../../core/models';
import { BadgeComponent, BadgeTone } from '../../ui/badge';
import { EmptyStateComponent } from '../../ui/empty-state';
import { FieldComponent } from '../../ui/field';
import { IconComponent } from '../../ui/icon';
import { PackageImportComponent } from '../../ui/package-import';
import { PageHeaderComponent } from '../../ui/page-header';
import { PromptBoxComponent, ReadPrompt } from '../../ui/prompt-box';
import { SectionComponent } from '../../ui/section';
import { SegmentedComponent, SegmentedOption } from '../../ui/segmented';
import { CharacterFormComponent, EMPTY_CHARACTER } from './character-form';

export type CharacterStatus = 'ready' | 'cutout' | 'choose';

/** O que falta para o personagem entrar num vídeo: escolher a imagem, recortar o fundo ou nada (pronto). */
export function statusOf(character: Character): CharacterStatus {
  if (!character.main_image_id) return 'choose';
  return character.has_cutout ? 'ready' : 'cutout';
}

const STATUS_TONE: Record<CharacterStatus, BadgeTone> = { ready: 'ok', cutout: 'warning', choose: 'neutral' };

/** Biblioteca de personagens (briefing 7.2) e a criação de um novo: por descrição, por prompt colado ou por uma imagem que você já tem. */
@Component({
  selector: 'fab-personagens-page',
  imports: [
    RouterLink,
    TPipe,
    BadgeComponent,
    CharacterFormComponent,
    EmptyStateComponent,
    FieldComponent,
    IconComponent,
    PackageImportComponent,
    PageHeaderComponent,
    PromptBoxComponent,
    SectionComponent,
    SegmentedComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './personagens.page.html',
})
export class PersonagensPage {
  /** `?nome=Bia` (vem de «Criar este personagem agora» no enredo): já deixa o nome preenchido. */
  readonly nome = input<string | undefined>(undefined);

  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly i18n = inject(I18nService);
  private readonly jobs = inject(JobsService);
  private readonly picker = viewChild.required<ElementRef<HTMLInputElement>>('picker');

  protected readonly exportUrl = this.api.charactersPackageUrl();
  protected readonly items = signal<Character[]>([]);
  protected readonly loaded = signal(false);
  protected readonly search = signal('');
  protected readonly styleFilter = signal<'todos' | Style>('todos');
  protected readonly mode = signal<'describe' | 'upload'>('describe');
  protected readonly form = signal<CharacterForm>({ ...EMPTY_CHARACTER });
  protected readonly originalPrompt = signal('');
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly existing = signal<string | null>(null);

  // envio de imagem
  protected readonly uploadName = signal('');
  protected readonly uploadStyle = signal<Style>('2D');
  protected readonly uploadRights = signal(false);
  protected readonly file = signal<File | null>(null);

  protected readonly modeOptions = computed<SegmentedOption[]>(() => [
    { value: 'describe', label: this.i18n.t('personagens.mode.describe') },
    { value: 'upload', label: this.i18n.t('personagens.mode.upload') },
  ]);
  protected readonly filterOptions = computed<SegmentedOption[]>(() => [
    { value: 'todos', label: this.i18n.t('personagens.filter.all') },
    { value: '2D', label: '2D' },
    { value: '3D', label: '3D' },
  ]);
  protected readonly styleOptions: SegmentedOption[] = [
    { value: '2D', label: '2D' },
    { value: '3D', label: '3D' },
  ];
  protected readonly visible = computed(() => {
    const filter = this.styleFilter();
    const q = this.search().trim().toLowerCase();
    return this.items().filter((c) => (filter === 'todos' || c.style === filter) && (!q || c.name.toLowerCase().includes(q)));
  });
  protected readonly canCreate = computed(
    () => !this.busy() && this.form().name.trim().length > 0 && this.form().appearance.trim().length > 0,
  );
  protected readonly canUpload = computed(
    () => !this.busy() && this.file() !== null && this.uploadName().trim().length > 0 && this.uploadRights(),
  );

  constructor() {
    this.load();
    effect(() => {
      const nome = this.nome()?.trim();
      if (nome) untracked(() => this.form.update((f) => ({ ...f, name: nome.slice(0, 80) })));
    });
    const destroyed = inject(DestroyRef);
    // um recorte que termina muda o estado de um cartão: recarrega a lista
    this.jobs.finished$.pipe(takeUntilDestroyed(destroyed)).subscribe((job) => {
      if (job.kind.startsWith('personagem.')) this.load();
    });
  }

  protected load(): void {
    this.api.characters().subscribe({
      next: (res) => {
        this.items.set(res.items);
        this.loaded.set(true);
      },
      error: (e: unknown) => {
        this.loaded.set(true);
        this.error.set(errorMessage(e));
      },
    });
  }

  protected status(character: Character): CharacterStatus {
    return statusOf(character);
  }

  protected tone(character: Character): BadgeTone {
    return STATUS_TONE[statusOf(character)];
  }

  protected setFilter(value: string): void {
    this.styleFilter.set(value as 'todos' | Style);
  }

  protected setMode(value: string): void {
    this.mode.set(value as 'describe' | 'upload');
    this.error.set(null);
    this.existing.set(null);
  }

  protected onParsed({ result, text }: ReadPrompt): void {
    const parsed = result.form as Partial<CharacterForm>;
    this.form.set({ ...EMPTY_CHARACTER, ...parsed });
    this.originalPrompt.set(text);
    this.error.set(null);
    this.existing.set(null);
    scrollToId('ficha');
  }

  protected create(): void {
    this.busy.set(true);
    this.error.set(null);
    this.existing.set(null);
    this.api.createCharacter({ ...this.form(), name: this.form().name.trim() }, this.originalPrompt()).subscribe({
      next: (character) => void this.router.navigate(['/personagens', character.id]),
      error: (e: unknown) => {
        this.busy.set(false);
        this.error.set(errorMessage(e));
        this.existing.set(existingId(e));
      },
    });
  }

  /** Abre o seletor de arquivos do Windows (o Explorer); vale para o botão do topo e para o da seção de criar. */
  protected pickFile(): void {
    this.picker().nativeElement.click();
  }

  /** A imagem escolhida no Explorer: passa para «enviar uma imagem», já com o nome do arquivo, e leva até o formulário. */
  protected onFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const chosen = input.files?.[0] ?? null;
    this.file.set(chosen);
    if (!chosen) return;
    if (!this.uploadName().trim()) this.uploadName.set(chosen.name.replace(/\.[^.]+$/, '').slice(0, 80));
    this.mode.set('upload');
    this.error.set(null);
    this.existing.set(null);
    scrollToId('novo');
  }

  protected setUploadStyle(value: string): void {
    this.uploadStyle.set(value as Style);
  }

  protected onRights(event: Event): void {
    this.uploadRights.set((event.target as HTMLInputElement).checked);
  }

  protected upload(): void {
    const file = this.file();
    if (!file) return;
    this.busy.set(true);
    this.error.set(null);
    this.existing.set(null);
    this.api.uploadCharacter(file, this.uploadName().trim(), this.uploadStyle(), this.uploadRights()).subscribe({
      next: (res) => {
        if (res.job) this.jobs.merge(res.job);
        void this.router.navigate(['/personagens', res.character.id]);
      },
      error: (e: unknown) => {
        this.busy.set(false);
        this.error.set(errorMessage(e));
        this.existing.set(existingId(e));
      },
    });
  }
}
