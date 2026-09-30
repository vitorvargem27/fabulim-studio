import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Estado vazio que convida a agir (briefing 10.3): título, uma linha de explicação e as ações projetadas. */
@Component({
  selector: 'fab-empty',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h2 class="text-h3">{{ title() }}</h2>
    @if (text()) {
      <p class="mt-2 max-w-measure font-text text-ink-soft">{{ text() }}</p>
    }
    <div class="mt-5 flex flex-wrap gap-3 empty:hidden"><ng-content /></div>
  `,
  host: { class: 'block border-l-8 border-accent bg-wash px-6 py-6 md:px-8 md:py-7' },
})
export class EmptyStateComponent {
  readonly title = input.required<string>();
  readonly text = input('');
}
