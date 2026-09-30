import { ChangeDetectionStrategy, Component, DestroyRef, inject, input, output, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ApiService } from '../core/api.service';
import { errorMessage } from '../core/http-error';
import { I18nService } from '../core/i18n/i18n.service';
import { TPipe } from '../core/i18n/t.pipe';
import { JobsService } from '../core/jobs.service';
import { ParsedPrompt, ParseResponse, PromptHistoryItem, PromptType } from '../core/models';
import { FieldComponent } from './field';
import { IconComponent } from './icon';
import { JobProgressComponent } from './job-progress';
import { PROMPT_EXAMPLES } from './prompt-examples';

export interface ReadPrompt {
  result: ParsedPrompt<Record<string, unknown>>;
  /** o texto colado, do jeito que o usuário colou (guardado com o personagem ou o projeto) */
  text: string;
}

/**
 * Área de colar o prompt do personagem, do enredo ou da imagem (briefing, seção 6). O formato estruturado (### PERSONAGEM...)
 * é lido na hora; o texto livre vai para o modelo local, como tarefa da fila, e o formulário volta preenchido para revisão.
 * Nada é gerado aqui: só preenche o formulário da página.
 */
@Component({
  selector: 'fab-prompt-box',
  imports: [FieldComponent, IconComponent, JobProgressComponent, TPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="grid gap-3">
      <fab-field
        [label]="'prompt.label.' + type() | t"
        [hint]="'prompt.hint' | t"
        [multiline]="true"
        [rows]="7"
        [maxlength]="30000"
        [placeholder]="'prompt.placeholder.' + type() | t"
        [(value)]="text"
      />
      <div class="flex flex-wrap items-center gap-2">
        <button type="button" class="btn btn-primary" (click)="read()" [disabled]="busy() || !text().trim()">
          <fab-icon name="sparkles" [size]="18" />
          {{ 'prompt.read' | t }}
        </button>
        <button type="button" class="btn btn-sm" (click)="example('structured')">{{ 'prompt.example.structured' | t }}</button>
        <button type="button" class="btn btn-sm" (click)="example('free')">{{ 'prompt.example.free' | t }}</button>
        <button type="button" class="btn btn-sm btn-quiet" (click)="toggleHistory()" [attr.aria-expanded]="showHistory()">
          <fab-icon name="clock" [size]="16" />
          {{ 'prompt.history' | t }}
        </button>
        @if (text()) {
          <button type="button" class="btn btn-sm btn-quiet" (click)="text.set('')">{{ 'prompt.clear' | t }}</button>
        }
      </div>

      @if (showHistory()) {
        <div class="border-2 border-rule-soft bg-panel p-3">
          @if (history().length) {
            <ul class="rule-list m-0 grid gap-0 p-0">
              @for (item of history(); track item.id) {
                <li class="flex items-start justify-between gap-3 py-2">
                  <button type="button" class="btn btn-quiet min-h-0 flex-1 justify-start text-left text-small" (click)="useHistory(item)">
                    {{ preview(item.text) }}
                  </button>
                  <button type="button" class="btn btn-icon btn-sm btn-quiet" (click)="removeHistory(item)" [attr.aria-label]="'prompt.history.remove' | t">
                    <fab-icon name="trash" [size]="16" />
                  </button>
                </li>
              }
            </ul>
          } @else {
            <p class="text-small text-ink-soft">{{ 'prompt.history.empty' | t }}</p>
          }
        </div>
      }

      <fab-job-progress [jobId]="jobId()" />

      @if (error(); as message) {
        <p class="banner banner-error" role="alert">{{ message }}</p>
      }
      @if (notes().length) {
        <ul class="banner banner-info m-0 list-none flex-col gap-1 p-3" role="status">
          @for (note of notes(); track note) {
            <li>{{ note }}</li>
          }
        </ul>
      }
    </div>
  `,
})
export class PromptBoxComponent {
  readonly type = input.required<PromptType>();
  readonly parsed = output<ReadPrompt>();

  private readonly api = inject(ApiService);
  private readonly jobs = inject(JobsService);
  private readonly i18n = inject(I18nService);

  protected readonly text = signal('');
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly notes = signal<string[]>([]);
  protected readonly jobId = signal<string | null>(null);
  protected readonly showHistory = signal(false);
  protected readonly history = signal<PromptHistoryItem[]>([]);
  private pendingText = '';

  constructor() {
    this.jobs.finished$.pipe(takeUntilDestroyed(inject(DestroyRef))).subscribe((job) => {
      if (job.id !== this.jobId()) return;
      this.busy.set(false);
      if (job.status === 'done' && job.result) this.handle(job.result as unknown as ParseResponse, this.pendingText);
      else if (job.status === 'failed') this.error.set(job.error ?? 'Não consegui ler o prompt.');
    });
  }

  /** Coloca um texto na caixa (usado pelo histórico e pelos exemplos, e por quem embute o componente). */
  fill(text: string): void {
    this.text.set(text);
  }

  protected example(kind: 'structured' | 'free'): void {
    this.text.set(PROMPT_EXAMPLES[this.type()][kind]);
    this.error.set(null);
    this.notes.set([]);
  }

  protected read(): void {
    const text = this.text().trim();
    if (!text) return;
    this.error.set(null);
    this.notes.set([]);
    this.jobId.set(null);
    this.busy.set(true);
    this.api.parsePrompt(text, this.type()).subscribe({
      next: (response) => {
        if (response.status === 'queued' && response.job) {
          this.pendingText = text;
          this.jobs.merge(response.job);
          this.jobId.set(response.job.id); // segue ocupado até a tarefa terminar
          return;
        }
        this.busy.set(false);
        this.handle(response, text);
      },
      error: (e: unknown) => {
        this.busy.set(false);
        this.error.set(errorMessage(e));
      },
    });
  }

  private handle(response: ParseResponse, text: string): void {
    if (response.status === 'blocked') {
      this.error.set(String(response.blocked?.reason ?? 'Este texto não pode ser usado.'));
      return;
    }
    const result = response.result;
    if (!result) {
      this.error.set('Não consegui ler o prompt.');
      return;
    }
    if (response.detected_type !== this.type()) {
      this.error.set(
        this.i18n.t('prompt.wrongType', {
          found: this.i18n.t(`prompt.type.${response.detected_type}`),
          expected: this.i18n.t(`prompt.type.${this.type()}`),
        }),
      );
      return;
    }
    const blocked = (response as { blocked?: { reason?: string } | null }).blocked;
    if (blocked?.reason) {
      this.error.set(blocked.reason);
      return;
    }
    this.notes.set([...result.warnings]);
    this.parsed.emit({ result: result as ParsedPrompt<Record<string, unknown>>, text });
  }

  protected toggleHistory(): void {
    const open = !this.showHistory();
    this.showHistory.set(open);
    if (open) this.api.promptHistory(this.type()).subscribe({ next: (items) => this.history.set(items), error: () => this.history.set([]) });
  }

  protected useHistory(item: PromptHistoryItem): void {
    this.text.set(item.text);
    this.showHistory.set(false);
  }

  protected removeHistory(item: PromptHistoryItem): void {
    this.api.deleteFromHistory(item.id).subscribe(() => this.history.update((list) => list.filter((h) => h.id !== item.id)));
  }

  protected preview(text: string): string {
    const flat = text.replace(/\s+/g, ' ').trim();
    return flat.length > 140 ? `${flat.slice(0, 140)}…` : flat;
  }
}
