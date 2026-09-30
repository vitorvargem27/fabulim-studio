import { ChangeDetectionStrategy, Component, ElementRef, inject, input, model } from '@angular/core';

export interface SegmentedOption {
  value: string;
  label: string;
}

/**
 * Controle segmentado (grupo de rádio): usado para tema e idioma e, depois, para o seletor 2D / 3D, que precisa ter
 * sempre o mesmo visual e a mesma posição. Setas movem a seleção (padrão WAI-ARIA de radiogroup). Botões retos e
 * colados, o marcado fica cheio de tinta.
 */
@Component({
  selector: 'fab-segmented',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="inline-flex border-2 border-ink bg-panel" role="radiogroup" [attr.aria-label]="label()" (keydown)="onKey($event)">
      @for (option of options(); track option.value) {
        <button
          type="button"
          role="radio"
          class="min-h-11 cursor-pointer border-r-2 border-ink px-4 font-ui text-[1rem] font-bold last:border-r-0 max-md:pointer-coarse:min-h-12"
          [class]="option.value === value() ? 'on bg-ink text-paper' : 'bg-transparent text-ink hover:bg-wash'"
          [attr.aria-checked]="option.value === value()"
          [attr.tabindex]="option.value === value() ? 0 : -1"
          (click)="value.set(option.value)"
        >
          {{ option.label }}
        </button>
      }
    </div>
  `,
  host: { class: 'inline-block' },
})
export class SegmentedComponent {
  readonly options = input.required<SegmentedOption[]>();
  readonly label = input.required<string>();
  readonly value = model.required<string>();
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  protected onKey(event: KeyboardEvent): void {
    const options = this.options();
    const current = options.findIndex((o) => o.value === this.value());
    let next = current;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (current + 1) % options.length;
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (current - 1 + options.length) % options.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = options.length - 1;
    else return;
    event.preventDefault();
    this.value.set(options[next].value);
    queueMicrotask(() => this.host.nativeElement.querySelector<HTMLElement>('button[aria-checked="true"]')?.focus());
  }
}
