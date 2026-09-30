import { CdkDrag, CdkDragDrop, CdkDragHandle, CdkDropList, moveItemInArray } from '@angular/cdk/drag-drop';
import { HttpEventType } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';

import { ApiService, SizePreset, Transition } from '../../core/api.service';
import { formatDuration, scrollToId } from '../../core/format';
import { errorMessage } from '../../core/http-error';
import { I18nService } from '../../core/i18n/i18n.service';
import { TPipe } from '../../core/i18n/t.pipe';
import { JobsService } from '../../core/jobs.service';
import { MachineService } from '../../core/machine.service';
import { parseSeed } from '../../core/match';
import { Character, Clip } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { downloadUrl } from '../../core/viewer.service';
import { CharacterPickerComponent } from '../../ui/character-picker';
import { EmptyStateComponent } from '../../ui/empty-state';
import { FieldComponent } from '../../ui/field';
import { IconComponent } from '../../ui/icon';
import { JobProgressComponent } from '../../ui/job-progress';
import { MediaTileComponent } from '../../ui/media-tile';
import { PageHeaderComponent } from '../../ui/page-header';
import { ProgressComponent } from '../../ui/progress';
import { SectionComponent } from '../../ui/section';

const ROLES = ['clipe_rapido', 'clipe_enviado', 'clipe_unido', 'clipe_reenquadrado', 'video_final'] as const;
const PRESETS: SizePreset[] = ['9:16', '16:9', '1:1', '720p'];
const TRANSITIONS: Transition[] = ['corte', 'fade', 'suave'];
const PAGE_SIZE = 24;

type Panel = { kind: 'reframe' | 'continue'; clip: Clip };

/**
 * Biblioteca de clipes (briefing 7.7 e 7.8): clipe rápido de um personagem, vídeos enviados, unir na ordem que você quiser,
 * gerar em outro formato e continuar uma história a partir do último quadro.
 */
@Component({
  selector: 'fab-clipes-page',
  imports: [
    CdkDrag,
    CdkDragHandle,
    CdkDropList,
    RouterLink,
    TPipe,
    CharacterPickerComponent,
    EmptyStateComponent,
    FieldComponent,
    IconComponent,
    JobProgressComponent,
    MediaTileComponent,
    PageHeaderComponent,
    ProgressComponent,
    SectionComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './clipes.page.html',
})
export class ClipesPage {
  private readonly api = inject(ApiService);
  private readonly jobs = inject(JobsService);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);
  private readonly i18n = inject(I18nService);
  private readonly machine = inject(MachineService);

  protected readonly roles = ROLES;
  protected readonly presets = PRESETS;
  protected readonly transitions = TRANSITIONS;
  protected readonly download = downloadUrl;
  protected readonly duration = formatDuration;

  protected readonly characters = signal<Character[]>([]);
  protected readonly clips = signal<Clip[]>([]);
  protected readonly total = signal(0);
  protected readonly loaded = signal(false);
  protected readonly roleFilter = signal<string>('todos');
  protected readonly search = signal('');
  protected readonly error = signal<string | null>(null);

  // clipe rápido
  protected readonly quickCharacter = signal('');
  protected readonly quickPrompt = signal('');
  protected readonly quickDuration = signal(5);
  protected readonly quickFormat = signal<'16:9' | '9:16'>('9:16');
  protected readonly quickQuality = signal<'rascunho' | 'padrao'>('rascunho');
  protected readonly quickSeed = signal('');
  protected readonly quickJob = signal<string | null>(null);
  protected readonly quickBusy = signal(false);

  // unir
  protected readonly selected = signal<string[]>([]);
  protected readonly joinTransition = signal<Transition>('corte');
  protected readonly joinSize = signal<'auto' | SizePreset>('auto');
  protected readonly joinJob = signal<string | null>(null);

  // ações sobre um clipe
  protected readonly panel = signal<Panel | null>(null);
  protected readonly reframePreset = signal<SizePreset>('9:16');
  protected readonly reframeMode = signal<'fit' | 'crop'>('fit');
  protected readonly reframeJob = signal<string | null>(null);
  protected readonly continuePrompt = signal('');
  protected readonly continueTitle = signal('');
  protected readonly continueLast = signal('');
  protected readonly continueCharacters = signal<string[]>([]);
  protected readonly continueBusy = signal(false);

  // enviar vídeo
  protected readonly uploadFile = signal<File | null>(null);
  protected readonly uploadRights = signal(false);
  protected readonly uploading = signal(false);
  protected readonly uploadProgress = signal(0);

  protected readonly ready = computed(() => this.characters().filter((c) => c.has_cutout));
  protected readonly canQuick = computed(
    () => !this.quickBusy() && !!this.quickCharacter() && this.quickPrompt().trim().length >= 3,
  );
  protected readonly selectedClips = computed(() => {
    const byId = new Map(this.clips().map((c) => [c.id, c]));
    return this.selected().map((id) => byId.get(id)).filter((c): c is Clip => c !== undefined);
  });
  protected readonly hasMore = computed(() => this.clips().length < this.total());
  protected readonly capability = computed(() => this.machine.capability('clipe_rapido'));

  constructor() {
    this.api.characters().subscribe({ next: (r) => this.characters.set(r.items), error: () => undefined });
    this.load(true);

    const destroyed = inject(DestroyRef);
    this.jobs.media$.pipe(takeUntilDestroyed(destroyed)).subscribe((event) => {
      if (event.type === 'deleted') {
        this.forget(event.id);
        return;
      }
      const media = event.media;
      if (media.kind !== 'video' || !(ROLES as readonly string[]).includes(media.role)) return;
      if (this.roleFilter() !== 'todos' && this.roleFilter() !== media.role) return;
      this.clips.update((l) => (l.some((c) => c.id === media.id) ? l : [{ ...media, project_title: null, variants: [] } as Clip, ...l]));
      this.total.update((n) => n + 1);
    });
    this.jobs.finished$.pipe(takeUntilDestroyed(destroyed)).subscribe((job) => {
      if (!job.kind.startsWith('clipe.')) return;
      if (job.id === this.quickJob()) this.quickBusy.set(false);
      if (job.status === 'done') this.toast.show(this.i18n.t('clipes.job.done'));
      else if (job.status === 'failed') this.error.set(job.error ?? this.i18n.t('clipes.job.failed'));
    });
  }

  // --- biblioteca ---------------------------------------------------------------------------------------------------------

  protected load(reset: boolean): void {
    const filter = this.roleFilter();
    const offset = reset ? 0 : this.clips().length;
    this.api
      .clips({ role: filter === 'todos' ? undefined : [filter], q: this.search().trim() || undefined, limit: PAGE_SIZE, offset })
      .subscribe({
        next: (page) => {
          this.total.set(page.total);
          this.clips.update((l) => (reset ? page.items : [...l, ...page.items]));
          this.loaded.set(true);
        },
        error: (e: unknown) => {
          this.loaded.set(true);
          this.error.set(errorMessage(e));
        },
      });
  }

  protected setRole(role: string): void {
    this.roleFilter.set(role);
    this.load(true);
  }

  protected onSearch(value: string): void {
    this.search.set(value);
    this.load(true);
  }

  protected remove(clip: Clip): void {
    if (!window.confirm(this.i18n.t('clipes.remove.confirm'))) return;
    this.api.deleteClip(clip.id).subscribe({
      next: () => this.forget(clip.id),
      error: (e: unknown) => this.toast.show(errorMessage(e), 'error'),
    });
  }

  /**
   * Tira o clipe das listas. O contador só cai se ele ainda estava na biblioteca: o evento do servidor e a resposta do pedido de
   * apagar chegam em qualquer ordem, e o segundo a chegar não pode contar de novo.
   */
  private forget(id: string): void {
    const estava = this.clips().some((c) => c.id === id);
    this.clips.update((l) => l.filter((c) => c.id !== id));
    this.selected.update((l) => l.filter((x) => x !== id));
    if (estava) this.total.update((n) => Math.max(0, n - 1));
  }

  protected roleOf(clip: Clip): string {
    return this.i18n.t(`clipes.role.${clip.role}`);
  }

  protected detailOf(clip: Clip): string {
    const parts = [clip.width && clip.height ? `${clip.width}×${clip.height}` : '', this.duration(clip.duration_s)];
    if (clip.project_title) parts.push(clip.project_title);
    return parts.filter(Boolean).join(' · ');
  }

  // --- clipe rápido ---------------------------------------------------------------------------------------------------------

  protected onQuickCharacter(event: Event): void {
    this.quickCharacter.set((event.target as HTMLSelectElement).value);
  }

  protected onQuickDuration(event: Event): void {
    this.quickDuration.set(Number((event.target as HTMLInputElement).value));
  }

  protected onQuickFormat(event: Event): void {
    this.quickFormat.set((event.target as HTMLSelectElement).value as '16:9' | '9:16');
  }

  protected onQuickQuality(event: Event): void {
    this.quickQuality.set((event.target as HTMLSelectElement).value as 'rascunho' | 'padrao');
  }

  protected quick(): void {
    this.error.set(null);
    this.quickBusy.set(true);
    this.api
      .quickClip({
        character_id: this.quickCharacter(),
        prompt: this.quickPrompt().trim(),
        duration_s: this.quickDuration(),
        format: this.quickFormat(),
        quality: this.quickQuality(),
        seed: parseSeed(this.quickSeed()),
      })
      .subscribe({
        next: (job) => {
          this.jobs.merge(job);
          this.quickJob.set(job.id);
        },
        error: (e: unknown) => {
          this.quickBusy.set(false);
          this.error.set(errorMessage(e));
        },
      });
  }

  // --- unir -----------------------------------------------------------------------------------------------------------------

  protected isSelected(clip: Clip): boolean {
    return this.selected().includes(clip.id);
  }

  protected toggleSelect(clip: Clip): void {
    this.selected.update((l) => (l.includes(clip.id) ? l.filter((id) => id !== clip.id) : l.length < 12 ? [...l, clip.id] : l));
  }

  protected dropSelected(event: CdkDragDrop<Clip[]>): void {
    const ids = [...this.selected()];
    moveItemInArray(ids, event.previousIndex, event.currentIndex);
    this.selected.set(ids);
  }

  protected move(index: number, delta: -1 | 1): void {
    const ids = [...this.selected()];
    const to = index + delta;
    if (to < 0 || to >= ids.length) return;
    moveItemInArray(ids, index, to);
    this.selected.set(ids);
  }

  protected onTransition(event: Event): void {
    this.joinTransition.set((event.target as HTMLSelectElement).value as Transition);
  }

  protected onJoinSize(event: Event): void {
    this.joinSize.set((event.target as HTMLSelectElement).value as 'auto' | SizePreset);
  }

  protected join(): void {
    this.error.set(null);
    this.api.joinClips(this.selected(), this.joinTransition(), this.joinSize()).subscribe({
      next: (job) => {
        this.jobs.merge(job);
        this.joinJob.set(job.id);
      },
      error: (e: unknown) => this.error.set(errorMessage(e)),
    });
  }

  // --- gerar em outro formato e continuar -----------------------------------------------------------------------------------

  protected openPanel(kind: 'reframe' | 'continue', clip: Clip): void {
    this.panel.set({ kind, clip });
    this.error.set(null);
    if (kind === 'continue') this.continueTitle.set('');
    queueMicrotask(() => scrollToId('acao'));
  }

  protected closePanel(): void {
    this.panel.set(null);
  }

  protected onReframePreset(event: Event): void {
    this.reframePreset.set((event.target as HTMLSelectElement).value as SizePreset);
  }

  protected onReframeMode(event: Event): void {
    this.reframeMode.set((event.target as HTMLSelectElement).value as 'fit' | 'crop');
  }

  protected reframe(): void {
    const panel = this.panel();
    if (!panel) return;
    this.error.set(null);
    this.api.reframeClip(panel.clip.id, this.reframePreset(), this.reframeMode()).subscribe({
      next: (job) => {
        this.jobs.merge(job);
        this.reframeJob.set(job.id);
      },
      error: (e: unknown) => this.error.set(errorMessage(e)),
    });
  }

  protected continueVideo(): void {
    const panel = this.panel();
    if (!panel) return;
    this.error.set(null);
    this.continueBusy.set(true);
    this.api
      .continueClip(panel.clip.id, {
        prompt: this.continuePrompt().trim(),
        character_ids: this.continueCharacters(),
        title: this.continueTitle().trim(),
        last_scene: this.continueLast().trim(),
      })
      .subscribe({
        next: (res) => void this.router.navigate(['/projetos', res.project.id]),
        error: (e: unknown) => {
          this.continueBusy.set(false);
          this.error.set(errorMessage(e));
        },
      });
  }

  // --- enviar vídeo -----------------------------------------------------------------------------------------------------------

  protected onFile(event: Event): void {
    this.uploadFile.set((event.target as HTMLInputElement).files?.[0] ?? null);
  }

  protected onRights(event: Event): void {
    this.uploadRights.set((event.target as HTMLInputElement).checked);
  }

  protected upload(): void {
    const file = this.uploadFile();
    if (!file) return;
    this.error.set(null);
    this.uploading.set(true);
    this.uploadProgress.set(0);
    this.api.uploadClip(file, this.uploadRights()).subscribe({
      next: (event) => {
        if (event.type === HttpEventType.UploadProgress && event.total) this.uploadProgress.set(event.loaded / event.total);
        else if (event.type === HttpEventType.Response && event.body) {
          this.uploading.set(false);
          this.uploadFile.set(null);
          this.uploadRights.set(false);
          const clip = event.body;
          this.clips.update((l) => (l.some((c) => c.id === clip.id) ? l : [clip, ...l]));
          this.toast.show(this.i18n.t('clipes.upload.done'));
        }
      },
      error: (e: unknown) => {
        this.uploading.set(false);
        this.error.set(errorMessage(e));
      },
    });
  }
}
