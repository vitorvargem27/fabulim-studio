import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { scrollToId } from '../../core/format';
import { errorMessage } from '../../core/http-error';
import { I18nService } from '../../core/i18n/i18n.service';
import { TPipe } from '../../core/i18n/t.pipe';
import { MachineService } from '../../core/machine.service';
import { durationLimit, matchCharacters, parseDurationSeconds } from '../../core/match';
import { Capability, Character, StoryForm } from '../../core/models';
import { BadgeComponent, BadgeTone } from '../../ui/badge';
import { CharacterPickerComponent } from '../../ui/character-picker';
import { FieldComponent } from '../../ui/field';
import { IconComponent } from '../../ui/icon';
import { PageHeaderComponent } from '../../ui/page-header';
import { PromptBoxComponent, ReadPrompt } from '../../ui/prompt-box';
import { SectionComponent } from '../../ui/section';
import { SegmentedComponent, SegmentedOption } from '../../ui/segmented';

interface Step {
  /** chave de tradução do nome; a explicação é `<key>.text` e o botão `<key>.go` */
  key: string;
  path: string;
  fragment?: string;
}

const EMPTY_STORY: StoryForm = {
  title: '',
  format: 'short',
  target_duration: '',
  language: 'pt-BR',
  style: '2D',
  characters: [],
  theme: '',
  settings: '',
  story: '',
  music: '',
  notes: '',
};

/**
 * Página inicial: começa o vídeo pelo enredo (cole o prompt ou escreva, confira os personagens, crie o projeto) e mostra o
 * caminho da ideia ao vídeo em sete etapas, com o que o computador dá conta de fazer rápido ou devagar.
 */
@Component({
  selector: 'fab-criar-video-page',
  imports: [
    RouterLink,
    TPipe,
    BadgeComponent,
    CharacterPickerComponent,
    FieldComponent,
    IconComponent,
    PageHeaderComponent,
    PromptBoxComponent,
    SectionComponent,
    SegmentedComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './criar-video.page.html',
})
export class CriarVideoPage {
  private readonly machine = inject(MachineService);
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly i18n = inject(I18nService);

  protected readonly profile = this.machine.profile;
  protected readonly steps: Step[] = [
    { key: 'criar.step.enredo', path: '/criar', fragment: 'comecar' },
    { key: 'criar.step.roteiro', path: '/projetos' },
    { key: 'criar.step.storyboard', path: '/projetos' },
    { key: 'criar.step.animacao', path: '/projetos' },
    { key: 'criar.step.audio', path: '/projetos' },
    { key: 'criar.step.montagem', path: '/projetos' },
    { key: 'criar.step.revisao', path: '/projetos' },
  ];
  protected readonly highlights = computed<Capability[]>(() =>
    ['llm_local', 'imagem', 'animacao_cena', 'animacao_ia']
      .map((id) => this.machine.capability(id))
      .filter((c): c is Capability => c !== undefined),
  );

  protected readonly form = signal<StoryForm>({ ...EMPTY_STORY });
  protected readonly originalPrompt = signal('');
  protected readonly seconds = signal(45);
  protected readonly library = signal<Character[]>([]);
  protected readonly selectedIds = signal<string[]>([]);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  /** Nomes citados no prompt que ainda não existem na biblioteca (ou existem só no outro estilo). */
  protected readonly missingNames = signal<string[]>([]);

  protected readonly formatOptions = computed<SegmentedOption[]>(() => [
    { value: 'short', label: this.i18n.t('criar.format.short') },
    { value: 'longo', label: this.i18n.t('criar.format.longo') },
  ]);
  protected readonly styleOptions: SegmentedOption[] = [
    { value: '2D', label: '2D' },
    { value: '3D', label: '3D' },
  ];
  protected readonly limit = computed(() => durationLimit(this.form().format));
  protected readonly chosen = computed(() => this.library().filter((c) => this.selectedIds().includes(c.id)));
  protected readonly styleMismatch = computed(() => this.chosen().filter((c) => c.style !== this.form().style));
  protected readonly withoutCutout = computed(() => this.chosen().filter((c) => !c.has_cutout));
  protected readonly canCreate = computed(() => !this.busy() && this.form().story.trim().length > 0);

  constructor() {
    this.api.characters().subscribe({ next: (r) => this.library.set(r.items), error: () => undefined });
  }

  protected tone(cap: Capability): BadgeTone {
    return cap.state === 'available' ? 'ok' : cap.state === 'slow' ? 'warning' : 'error';
  }

  protected patch<K extends keyof StoryForm>(key: K, value: StoryForm[K]): void {
    this.form.update((f) => ({ ...f, [key]: value }));
  }

  protected setFormat(value: string): void {
    const format = value as StoryForm['format'];
    this.patch('format', format);
    this.seconds.update((s) => Math.min(s, durationLimit(format)));
  }

  protected onLanguage(event: Event): void {
    this.patch('language', (event.target as HTMLSelectElement).value as StoryForm['language']);
  }

  protected onSeconds(event: Event): void {
    this.seconds.set(Number((event.target as HTMLInputElement).value));
  }

  protected onParsed({ result, text }: ReadPrompt): void {
    const parsed = result.form as Partial<StoryForm>;
    const next: StoryForm = { ...EMPTY_STORY, ...parsed, characters: parsed.characters ?? [] };
    this.form.set(next);
    this.originalPrompt.set(text);
    this.seconds.set(parseDurationSeconds(next.target_duration, next.format));
    const { found, missing } = matchCharacters(next.characters, this.library(), next.style);
    this.selectedIds.set(found.map((c) => c.id));
    this.missingNames.set(missing);
    this.error.set(null);
    scrollToId('historia');
  }

  protected create(): void {
    this.error.set(null);
    this.busy.set(true);
    const names = this.chosen().map((c) => c.name);
    this.api
      .createProject({
        form: { ...this.form(), characters: names },
        original_prompt: this.originalPrompt(),
        character_ids: this.selectedIds(),
        target_duration_s: this.seconds(),
      })
      .subscribe({
        next: (res) => void this.router.navigate(['/projetos', res.project.id]),
        error: (e: unknown) => {
          this.busy.set(false);
          this.error.set(errorMessage(e));
        },
      });
  }
}
