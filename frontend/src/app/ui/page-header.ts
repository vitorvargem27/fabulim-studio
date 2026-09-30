import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { Router } from '@angular/router';

import { NAV_ITEMS, navIndexOf } from '../core/nav';

/**
 * Cabeçalho de página, estilo revista: número da seção (a mesma numeração do menu), título grande em Fredoka, texto de
 * apoio em Fraunces e um filete de tinta embaixo. Um único h1 por tela; as ações da página ficam à direita.
 */
@Component({
  selector: 'fab-page-header',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="pointer-events-none absolute inset-y-0 right-0 hidden w-2/5 dots [mask-image:linear-gradient(to_left,black,transparent)] md:block" aria-hidden="true"></div>
    <div class="relative min-w-0 flex-1 basis-[22rem]">
      @if (index(); as n) {
        <p class="mb-4 flex items-center gap-2 font-mono text-meta font-bold text-ink-soft" aria-hidden="true">
          <span class="bg-accent px-1.5 py-0.5 text-on-accent">{{ n }}</span>
          <span>/ {{ total }}</span>
        </p>
      }
      <h1>{{ title() }}</h1>
      @if (subtitle()) {
        <p class="mt-5 max-w-measure font-text text-lead text-ink-soft">{{ subtitle() }}</p>
      }
    </div>
    <div class="relative flex flex-wrap items-end gap-3 empty:hidden"><ng-content /></div>
  `,
  host: { class: 'relative mb-10 flex flex-wrap items-end justify-between gap-x-8 gap-y-6 border-b-2 border-ink pb-9' },
})
export class PageHeaderComponent {
  readonly title = input.required<string>();
  readonly subtitle = input('');
  private readonly router = inject(Router);
  protected readonly total = String(NAV_ITEMS.length).padStart(2, '0');
  protected readonly index = computed(() => navIndexOf(this.router.url));
}
