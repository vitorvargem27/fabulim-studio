import { ChangeDetectionStrategy, Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { ApiService } from '../../../core/api.service';
import { formatBytes, formatDuration } from '../../../core/format';
import { I18nService } from '../../../core/i18n/i18n.service';
import { TPipe } from '../../../core/i18n/t.pipe';
import { ChecklistItem, MetadataLanguage, MetadataText, ProjectMetadata } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';
import { downloadUrl } from '../../../core/viewer.service';
import { BadgeComponent, BadgeTone } from '../../../ui/badge';
import { FieldComponent } from '../../../ui/field';
import { IconComponent } from '../../../ui/icon';
import { MediaTileComponent } from '../../../ui/media-tile';
import { SectionComponent } from '../../../ui/section';
import { ProjectStore } from '../project.store';
import { StageApprovalComponent } from './stage-approval';

const TONES: Record<ChecklistItem['status'], BadgeTone> = { ok: 'ok', warning: 'warning', error: 'error' };
const LANGUAGES: MetadataLanguage[] = ['pt-BR', 'en'];
const TITLE_LIMIT = 100;
const DESCRIPTION_LIMIT = 4500;
const TAG_LIMIT = 15;

/** O texto de um idioma na tela: as tags viram uma linha separada por vírgula (mais fácil de editar). */
export interface MetadataDraftText {
  title: string;
  description: string;
  tags: string;
}
export type MetadataDraft = Record<MetadataLanguage, MetadataDraftText>;

export function draftOf(metadata: ProjectMetadata | null): MetadataDraft {
  const one = (text: MetadataText | undefined): MetadataDraftText => ({
    title: text?.title ?? '',
    description: text?.description ?? '',
    tags: (text?.tags ?? []).join(', '),
  });
  return { 'pt-BR': one(metadata?.['pt-BR']), en: one(metadata?.en) };
}

/** As tags digitadas numa linha viram uma lista limpa (sem # e sem repetir); o servidor ainda confere os limites do YouTube. */
export function tagsOf(text: string): string[] {
  const seen = new Set<string>();
  const tags: string[] = [];
  for (const raw of text.split(/[,\n]/)) {
    const tag = raw.replace(/#/g, '').trim();
    const key = tag.toLowerCase();
    if (tag && !seen.has(key)) {
      seen.add(key);
      tags.push(tag);
    }
  }
  return tags;
}

/**
 * Etapa 7: revisão e exportação (briefing 7.10 e 7.11): checklist de qualidade, o vídeo final e as legendas, miniaturas
 * 1280×720 com os personagens, título, descrição e tags em PT e EN, a versão em outro idioma e formato, e o pacote .fabulim.
 */
@Component({
  selector: 'fab-etapa-revisao',
  imports: [RouterLink, TPipe, BadgeComponent, FieldComponent, IconComponent, MediaTileComponent, SectionComponent, StageApprovalComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './etapa-revisao.html',
})
export class EtapaRevisao {
  protected readonly store = inject(ProjectStore);
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);
  private readonly i18n = inject(I18nService);

  protected readonly languages = LANGUAGES;
  protected readonly titleLimit = TITLE_LIMIT;
  protected readonly descriptionLimit = DESCRIPTION_LIMIT;
  protected readonly tagLimit = TAG_LIMIT;
  protected readonly download = downloadUrl;
  protected readonly duration = formatDuration;
  protected readonly bytes = formatBytes;

  protected readonly checklist = signal<ChecklistItem[]>([]);
  protected readonly reminder = signal('');
  protected readonly thumbCount = signal(3);
  protected readonly thumbText = signal('');
  protected readonly withRenders = signal(false);
  protected readonly draft = signal<MetadataDraft>(draftOf(null));

  protected readonly final = computed(() => this.store.detail()?.files.final ?? null);
  protected readonly subtitles = computed(() => this.store.detail()?.files.subtitles ?? null);
  protected readonly thumbnails = computed(() => this.store.detail()?.files.thumbnails ?? []);
  protected readonly variants = computed(() => this.store.detail()?.variants ?? []);
  protected readonly metadata = computed(() => this.store.detail()?.metadata ?? null);
  protected readonly portrait = computed(() => this.store.project()?.format === 'short');
  protected readonly hasScenery = computed(() => this.store.scenes().some((s) => !!s.data.background));
  protected readonly hasScenes = computed(() => this.store.scenes().length > 0);
  protected readonly otherLanguage = computed<MetadataLanguage>(() => (this.store.project()?.language === 'en' ? 'pt-BR' : 'en'));
  protected readonly otherFormat = computed<'short' | 'longo'>(() => (this.store.project()?.format === 'short' ? 'longo' : 'short'));
  /** Como o rascunho estava na última vez que veio do servidor: tem mudança não salva quando ele é diferente disso. */
  private readonly synced = signal(JSON.stringify(draftOf(null)));
  protected readonly dirty = computed(() => JSON.stringify(this.draft()) !== this.synced());
  protected readonly slug = computed(() =>
    (this.store.project()?.title ?? 'video')
      .normalize('NFD')
      .replace(/\p{Diacritic}/gu, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 60) || 'video',
  );
  protected readonly packageUrl = computed(() => this.api.projectPackageUrl(this.store.id(), this.withRenders()));

  constructor() {
    effect(() => {
      this.store.detail(); // o checklist é recalculado a cada mudança do projeto
      untracked(() => this.loadReview());
    });
    effect(() => {
      const fresh = draftOf(this.metadata());
      untracked(() => {
        if (this.dirty()) return; // não pisa no que o usuário está digitando
        this.draft.set(fresh);
        this.synced.set(JSON.stringify(fresh));
      });
    });
  }

  private loadReview(): void {
    const id = this.store.id();
    if (!id) return;
    this.api.review(id).subscribe({
      next: (review) => {
        this.checklist.set(review.checklist);
        this.reminder.set(review.reminder);
      },
      error: () => undefined,
    });
  }

  protected tone(item: ChecklistItem): BadgeTone {
    return TONES[item.status];
  }

  // --- miniaturas ---------------------------------------------------------------------------------------------------------

  protected onThumbCount(event: Event): void {
    this.thumbCount.set(Number((event.target as HTMLSelectElement).value));
  }

  protected generateThumbnails(): void {
    this.store.startJob(this.api.generateThumbnails(this.store.id(), { count: this.thumbCount(), text: this.thumbText().trim() || null }));
  }

  protected removeThumbnail(mediaId: string): void {
    if (!window.confirm(this.i18n.t('proj.review.thumbs.remove.confirm'))) return;
    this.store.run(this.api.deleteThumbnail(this.store.id(), mediaId), () => this.store.load(this.store.id()));
  }

  // --- título, descrição e tags ----------------------------------------------------------------------------------------------

  protected suggest(mode: 'ia' | 'simples'): void {
    this.store.startJob(this.api.generateMetadata(this.store.id(), mode));
  }

  protected patch(language: MetadataLanguage, key: keyof MetadataDraftText, value: string): void {
    this.draft.update((d) => ({ ...d, [language]: { ...d[language], [key]: value } }));
  }

  protected tagCount(language: MetadataLanguage): number {
    return tagsOf(this.draft()[language].tags).length;
  }

  protected saveMetadata(): void {
    const d = this.draft();
    const text = (language: MetadataLanguage): MetadataText => ({
      title: d[language].title.trim(),
      description: d[language].description.trim(),
      tags: tagsOf(d[language].tags),
    });
    this.store.run(this.api.saveMetadata(this.store.id(), { 'pt-BR': text('pt-BR'), en: text('en') }), (detail) => {
      this.store.applyDetail(detail);
      this.toast.show(this.i18n.t('proj.review.meta.saved'));
    });
  }

  protected async copy(text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      this.toast.show(this.i18n.t('proj.review.meta.copied'));
    } catch {
      this.toast.show(this.i18n.t('imagem.copy.failed'), 'error');
    }
  }

  // --- outras versões -------------------------------------------------------------------------------------------------------

  protected createLanguageVersion(mode: 'ia' | 'simples'): void {
    this.store.startJob(this.api.languageVersion(this.store.id(), this.otherLanguage(), mode));
  }

  protected createVariant(): void {
    this.store.run(this.api.createVariant(this.store.id(), this.otherFormat()), (res) => {
      this.toast.show(this.i18n.t('proj.review.versions.created'));
      if (res.warnings.length) this.store.notices.set(res.warnings);
      this.store.load(this.store.id());
      void this.router.navigate(['/projetos', res.project.id]);
    });
  }
}
