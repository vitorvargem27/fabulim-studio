import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export type BadgeTone = 'ok' | 'warning' | 'error' | 'info' | 'neutral';

/**
 * Marcador de estado: uma forma + a palavra, sem fundo colorido. A forma muda com o estado (círculo com visto,
 * triângulo, quadrado com X, losango, círculo vazio), então nunca depende só da cor (acessível a daltônicos).
 */
@Component({
  selector: 'fab-badge',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (icon()) {
      <svg class="size-[1.1rem] shrink-0" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
        @switch (tone()) {
          @case ('ok') {
            <circle cx="8" cy="8" r="6.6" class="fill-menta stroke-ink" stroke-width="1.6" />
            <path d="M4.8 8.2l2.2 2.2 4.2-4.6" class="stroke-ink" fill="none" stroke-width="1.8" />
          }
          @case ('warning') {
            <path d="M8 1.6l6.6 11.9H1.4z" class="fill-girassol stroke-ink" stroke-width="1.6" stroke-linejoin="round" />
            <path d="M8 6v3.4M8 11.4v.1" class="stroke-ink" fill="none" stroke-width="1.8" />
          }
          @case ('error') {
            <rect x="1.6" y="1.6" width="12.8" height="12.8" class="fill-coral stroke-ink" stroke-width="1.6" />
            <path d="M5.2 5.2l5.6 5.6M10.8 5.2l-5.6 5.6" class="stroke-ink" fill="none" stroke-width="1.8" />
          }
          @case ('info') {
            <path d="M8 1.2l6.8 6.8L8 14.8 1.2 8z" class="fill-wash stroke-ink" stroke-width="1.6" stroke-linejoin="round" />
            <path d="M8 7.2v3.4M8 5.1v.1" class="stroke-ink" fill="none" stroke-width="1.8" />
          }
          @default {
            <circle cx="8" cy="8" r="6.4" class="fill-transparent stroke-ink-soft" stroke-width="1.6" stroke-dasharray="3 2.2" />
          }
        }
      </svg>
    }
    <ng-content />
  `,
  host: {
    class: 'inline-flex items-center gap-1.5 whitespace-nowrap text-small font-bold leading-snug text-ink',
    '[class]': '"tone-" + tone()',
  },
})
export class BadgeComponent {
  readonly tone = input<BadgeTone>('neutral');
  readonly icon = input(true);
}
