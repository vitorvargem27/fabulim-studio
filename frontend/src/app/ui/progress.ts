import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/** Barra de progresso (0 a 1) com semântica de `progressbar`: trilho de tinta; pausada fica listrada de girassol. */
@Component({
  selector: 'fab-progress',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div
      class="h-4 border-2 border-ink bg-panel"
      role="progressbar"
      aria-valuemin="0"
      aria-valuemax="100"
      [attr.aria-valuenow]="percent()"
      [attr.aria-label]="label()"
    >
      <div
        class="fill h-full transition-[width] duration-200 ease-out"
        [class]="
          paused()
            ? 'paused bg-girassol [background-image:repeating-linear-gradient(135deg,var(--brand-anil)_0_3px,transparent_3px_9px)]'
            : 'bg-menta'
        "
        [style.width.%]="percent()"
      ></div>
    </div>
  `,
  host: { class: 'block' },
})
export class ProgressComponent {
  readonly value = input(0);
  readonly label = input('Progresso');
  readonly paused = input(false);
  protected readonly percent = computed(() => Math.round(Math.max(0, Math.min(1, this.value())) * 100));
}
