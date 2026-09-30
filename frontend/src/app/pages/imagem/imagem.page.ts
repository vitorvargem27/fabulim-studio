import { ChangeDetectionStrategy, Component, DestroyRef, computed, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subscription } from 'rxjs';

import { ApiService, ImageRequest, Quality } from '../../core/api.service';
import { scrollToId } from '../../core/format';
import { errorMessage } from '../../core/http-error';
import { I18nService } from '../../core/i18n/i18n.service';
import { TPipe } from '../../core/i18n/t.pipe';
import { JobsService } from '../../core/jobs.service';
import { matchCharacters, parseSeed } from '../../core/match';
import { Character, Estimate, ImageForm, ImageFormat, ImageKind, Media, Style } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { downloadUrl } from '../../core/viewer.service';
import { CharacterPickerComponent } from '../../ui/character-picker';
import { EmptyStateComponent } from '../../ui/empty-state';
import { FieldComponent } from '../../ui/field';
import { IconComponent } from '../../ui/icon';
import { JobProgressComponent } from '../../ui/job-progress';
import { MediaTileComponent } from '../../ui/media-tile';
import { PageHeaderComponent } from '../../ui/page-header';
import { PromptBoxComponent, ReadPrompt } from '../../ui/prompt-box';
import { SectionComponent } from '../../ui/section';
import { SegmentedComponent, SegmentedOption } from '../../ui/segmented';

const KINDS: ImageKind[] = ['cenario', 'objeto', 'thumbnail', 'livre'];
const FORMATS: ImageFormat[] = ['16:9', '9:16', '1:1'];
const QUALITIES: Quality[] = ['rascunho', 'padrao', 'alta'];
const LIBRARY_ROLES = ['cenario', 'objeto', 'thumbnail', 'livre'];
const PAGE_SIZE = 24;

const EMPTY_FORM: ImageForm = { kind: 'livre', style: '2D', format: '16:9', characters: [], description: '', notes: '' };

/**
 * Gerar imagem avulsa (briefing 7.5): descreva ou cole o prompt, escolha formato, estilo e personagens da biblioteca, veja
 * e edite o prompt técnico, compare as variações lado a lado e guarde as melhores na biblioteca.
 */
@Component({
  selector: 'fab-imagem-page',
  imports: [
    TPipe,
    CharacterPickerComponent,
    EmptyStateComponent,
    FieldComponent,
    IconComponent,
    JobProgressComponent,
    MediaTileComponent,
    PageHeaderComponent,
    PromptBoxComponent,
    SectionComponent,
    SegmentedComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './imagem.page.html',
})
export class ImagemPage {
  private readonly api = inject(ApiService);
  private readonly jobs = inject(JobsService);
  private readonly toast = inject(ToastService);
  private readonly i18n = inject(I18nService);

  protected readonly kinds = KINDS;
  protected readonly formats = FORMATS;
  protected readonly qualities = QUALITIES;
  protected readonly download = downloadUrl;

  protected readonly form = signal<ImageForm>({ ...EMPTY_FORM });
  protected readonly quality = signal<Quality>('padrao');
  protected readonly count = signal(1);
  protected readonly seed = signal('');
  protected readonly technical = signal('');
  protected readonly technicalEdited = signal(false);
  protected readonly characters = signal<Character[]>([]);
  protected readonly selectedIds = signal<string[]>([]);
  protected readonly basedOn = signal<Media | null>(null);
  protected readonly notFound = signal<string[]>([]);
  protected readonly estimate = signal<Estimate | null>(null);
  protected readonly jobId = signal<string | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly results = signal<Media[]>([]);
  protected readonly library = signal<Media[]>([]);
  protected readonly libraryTotal = signal(0);
  protected readonly search = signal('');
  protected readonly loadingTechnical = signal(false);

  protected readonly styleOptions = computed<SegmentedOption[]>(() => [
    { value: '2D', label: '2D' },
    { value: '3D', label: '3D' },
  ]);
  protected readonly canGenerate = computed(
    () => !this.busy() && (this.form().description.trim().length > 0 || this.technical().trim().length > 0),
  );
  protected readonly references = computed(() => this.selectedIds().length + (this.basedOn() ? 1 : 0));
  protected readonly hasMore = computed(() => this.library().length < this.libraryTotal());

  private estimateSub?: Subscription;

  constructor() {
    this.api.characters().subscribe({ next: (list) => this.characters.set(list.items), error: () => undefined });
    this.loadLibrary(true);

    // o tempo estimado acompanha formato, qualidade, quantidade e número de referências
    effect(() => {
      const { format } = this.form();
      const quality = this.quality();
      const count = this.count();
      const references = this.references();
      this.estimateSub?.unsubscribe();
      this.estimateSub = this.api.imageEstimate(format, quality, count, references).subscribe({
        next: (estimate) => this.estimate.set(estimate),
        error: () => this.estimate.set(null),
      });
    });

    const destroyed = inject(DestroyRef);
    destroyed.onDestroy(() => this.estimateSub?.unsubscribe());

    // cada variação aparece assim que fica pronta; ao fim da tarefa, avisa
    this.jobs.media$.pipe(takeUntilDestroyed(destroyed)).subscribe((event) => {
      if (event.type === 'deleted') {
        this.forget(event.id);
        return;
      }
      const media = event.media;
      if (media.kind !== 'imagem' || media.owner_type !== null || !LIBRARY_ROLES.includes(media.role)) return;
      this.library.update((l) => (l.some((m) => m.id === media.id) ? l : [media, ...l]));
      this.libraryTotal.update((n) => n + 1);
      if (media.job_id && media.job_id === this.jobId()) this.results.update((l) => [...l, media]);
    });
    this.jobs.finished$.pipe(takeUntilDestroyed(destroyed)).subscribe((job) => {
      if (job.id !== this.jobId()) return;
      this.busy.set(false);
      if (job.status === 'done') this.toast.show(this.i18n.t('imagem.done'));
      else if (job.status === 'failed') this.error.set(job.error ?? this.i18n.t('imagem.failed'));
    });
  }

  // --- formulário ------------------------------------------------------------------------------------------------------

  protected patch<K extends keyof ImageForm>(key: K, value: ImageForm[K]): void {
    this.form.update((f) => ({ ...f, [key]: value }));
  }

  protected onKind(event: Event): void {
    this.patch('kind', (event.target as HTMLSelectElement).value as ImageKind);
  }

  protected onFormat(event: Event): void {
    this.patch('format', (event.target as HTMLSelectElement).value as ImageFormat);
  }

  protected onQuality(event: Event): void {
    this.quality.set((event.target as HTMLSelectElement).value as Quality);
  }

  protected onCount(event: Event): void {
    const value = Number((event.target as HTMLInputElement).value);
    this.count.set(Math.min(4, Math.max(1, Number.isFinite(value) ? Math.round(value) : 1)));
  }

  protected onTechnical(value: string): void {
    this.technical.set(value);
    this.technicalEdited.set(true);
  }

  protected onParsed({ result }: ReadPrompt): void {
    const parsed = result.form as Partial<ImageForm>;
    const next: ImageForm = { ...EMPTY_FORM, ...parsed, characters: parsed.characters ?? [] };
    this.form.set(next);
    const { found, missing } = matchCharacters(next.characters, this.characters(), next.style);
    this.selectedIds.set(found.filter((c) => c.main_image_id).map((c) => c.id).slice(0, 3));
    this.notFound.set([...missing, ...found.filter((c) => !c.main_image_id).map((c) => c.name)]);
    this.technical.set('');
    this.technicalEdited.set(false);
    this.toast.show(this.i18n.t('imagem.filled'), 'info');
  }

  protected setStyle(value: string): void {
    this.patch('style', value as Style);
  }

  protected refreshTechnical(): void {
    this.loadingTechnical.set(true);
    const selected = this.selectedIds();
    const names = this.characters().filter((c) => selected.includes(c.id)).map((c) => c.name);
    this.api.technicalPrompt({ ...this.form(), characters: names }, selected, this.basedOn()?.id ?? null).subscribe({
      next: (res) => {
        this.technical.set(res.technical_prompt);
        this.technicalEdited.set(false);
        this.loadingTechnical.set(false);
      },
      error: (e: unknown) => {
        this.error.set(errorMessage(e));
        this.loadingTechnical.set(false);
      },
    });
  }

  // --- gerar --------------------------------------------------------------------------------------------------------------

  protected generate(): void {
    this.error.set(null);
    this.busy.set(true);
    this.results.set([]);
    const selected = this.selectedIds();
    const names = this.characters().filter((c) => selected.includes(c.id)).map((c) => c.name);
    const request: ImageRequest = {
      form: { ...this.form(), characters: names },
      technical_prompt: this.technicalEdited() && this.technical().trim() ? this.technical().trim() : null,
      quality: this.quality(),
      count: this.count(),
      seed: parseSeed(this.seed()),
      character_ids: selected,
      based_on: this.basedOn()?.id ?? null,
    };
    this.api.generateImage(request).subscribe({
      next: (job) => {
        this.jobs.merge(job);
        this.jobId.set(job.id);
      },
      error: (e: unknown) => {
        this.busy.set(false);
        this.error.set(errorMessage(e));
      },
    });
  }

  // --- resultados e biblioteca -------------------------------------------------------------------------------------------

  protected similar(media: Media): void {
    this.basedOn.set(media);
    if (media.prompt && !this.form().description.trim()) this.patch('description', media.prompt);
    this.toast.show(this.i18n.t('imagem.similar.set'), 'info');
    scrollToId('descricao');
  }

  protected async copyPrompt(media: Media): Promise<void> {
    const text = media.technical_prompt || media.prompt || '';
    try {
      await navigator.clipboard.writeText(text);
      this.toast.show(this.i18n.t('imagem.copied'));
    } catch {
      this.toast.show(this.i18n.t('imagem.copy.failed'), 'error');
    }
  }

  protected remove(media: Media): void {
    if (!window.confirm(this.i18n.t('imagem.remove.confirm'))) return;
    this.api.deleteMedia(media.id).subscribe({
      next: () => {
        this.forget(media.id);
        if (this.basedOn()?.id === media.id) this.basedOn.set(null);
      },
      error: (e: unknown) => this.toast.show(errorMessage(e), 'error'),
    });
  }

  /**
   * Tira a imagem das listas. O contador só cai se ela ainda estava na biblioteca: o evento do servidor e a resposta do pedido
   * de apagar chegam em qualquer ordem, e o segundo a chegar não pode contar de novo.
   */
  private forget(id: string): void {
    const estava = this.library().some((m) => m.id === id);
    this.results.update((l) => l.filter((m) => m.id !== id));
    this.library.update((l) => l.filter((m) => m.id !== id));
    if (estava) this.libraryTotal.update((n) => Math.max(0, n - 1));
  }

  protected onSearch(value: string): void {
    this.search.set(value);
    this.loadLibrary(true);
  }

  protected loadLibrary(reset: boolean): void {
    const offset = reset ? 0 : this.library().length;
    this.api
      .media({ kind: 'imagem', role: LIBRARY_ROLES, ownerType: 'nenhum', q: this.search().trim() || undefined, limit: PAGE_SIZE, offset })
      .subscribe({
        next: (page) => {
          this.libraryTotal.set(page.total);
          this.library.update((l) => (reset ? page.items : [...l, ...page.items]));
        },
        error: () => undefined,
      });
  }

  protected kindLabel(kind: string): string {
    return this.i18n.t(`imagem.kind.${kind}`);
  }

  protected caption(media: Media): string {
    return `${this.kindLabel(media.role)} · ${media.style ?? ''}`.replace(/ · $/, '');
  }

  protected detail(media: Media): string {
    const format = (media.metadata['format'] as string | undefined) ?? '';
    return [format, media.seed !== null ? `${this.i18n.t('viewer.seed')} ${media.seed}` : ''].filter(Boolean).join(' · ');
  }
}
