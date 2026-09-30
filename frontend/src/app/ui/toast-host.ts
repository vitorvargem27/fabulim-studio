import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { I18nService } from '../core/i18n/i18n.service';
import { TPipe } from '../core/i18n/t.pipe';
import { ToastService } from '../core/toast.service';
import { BadgeComponent } from './badge';
import { IconComponent } from './icon';

/** Região aria-live: os avisos são lidos por leitores de tela sem tirar o foco de onde o usuário está. */
@Component({
  selector: 'fab-toast-host',
  imports: [BadgeComponent, IconComponent, TPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div
      class="pointer-events-none fixed inset-x-3 bottom-3 z-60 grid gap-3 md:inset-x-auto md:right-5 md:bottom-5 md:w-[24rem]"
      role="region"
      aria-live="polite"
      [attr.aria-label]="'toast.region' | t"
    >
      @for (toast of toasts.toasts(); track toast.id) {
        <div
          class="toast pointer-events-auto flex items-center gap-3 border-2 border-ink bg-panel py-2 pl-3 pr-2 font-semibold shadow-hard"
          [class]="'tone-' + toast.tone"
        >
          <fab-badge [tone]="toast.tone === 'error' ? 'error' : toast.tone === 'info' ? 'info' : 'ok'" />
          <span class="flex-1">{{ toast.text }}</span>
          <button type="button" class="btn btn-quiet btn-icon btn-sm" (click)="toasts.dismiss(toast.id)" [attr.aria-label]="i18n.t('toast.close')">
            <fab-icon name="close" [size]="16" />
          </button>
        </div>
      }
    </div>
  `,
})
export class ToastHostComponent {
  protected readonly toasts = inject(ToastService);
  protected readonly i18n = inject(I18nService);
}
