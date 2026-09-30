import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

let nextId = 1;

/**
 * Campo de texto com rótulo em cima e dica embaixo (a dica é ligada por `aria-describedby`). Uma linha ou várias.
 * O valor é sempre texto: quem precisa de número converte ao usar.
 */
@Component({
  selector: 'fab-field',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="field">
      <label class="field-label" [attr.for]="id">
        {{ label() }}
        @if (required()) {
          <span aria-hidden="true">*</span>
        }
      </label>
      @if (multiline()) {
        <textarea
          [id]="id"
          [rows]="rows()"
          [value]="value()"
          [disabled]="disabled()"
          [attr.maxlength]="maxlength()"
          [attr.placeholder]="placeholder() || null"
          [attr.aria-describedby]="hint() ? id + '-hint' : null"
          [attr.aria-required]="required() || null"
          (input)="value.set(read($event))"
        ></textarea>
      } @else {
        <input
          [id]="id"
          [type]="type()"
          [value]="value()"
          [disabled]="disabled()"
          [attr.maxlength]="maxlength()"
          [attr.placeholder]="placeholder() || null"
          [attr.min]="min()"
          [attr.max]="max()"
          [attr.step]="step()"
          [attr.aria-describedby]="hint() ? id + '-hint' : null"
          [attr.aria-required]="required() || null"
          (input)="value.set(read($event))"
        />
      }
      @if (hint()) {
        <span class="field-hint" [id]="id + '-hint'">{{ hint() }}</span>
      }
    </div>
  `,
  host: { class: 'block min-w-0' },
})
export class FieldComponent {
  readonly label = input.required<string>();
  readonly hint = input('');
  readonly value = model('');
  readonly multiline = input(false);
  readonly rows = input(3);
  readonly maxlength = input<number | null>(null);
  readonly placeholder = input('');
  readonly disabled = input(false);
  readonly required = input(false);
  readonly type = input<'text' | 'search' | 'number'>('text');
  readonly min = input<number | null>(null);
  readonly max = input<number | null>(null);
  readonly step = input<number | null>(null);

  protected readonly id = `fab-field-${nextId++}`;

  protected read(event: Event): string {
    return (event.target as HTMLInputElement | HTMLTextAreaElement).value;
  }
}
