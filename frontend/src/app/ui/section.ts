import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * Bloco de página: título e explicação numa coluna estreita à esquerda, conteúdo na larga à direita, separados por um
 * filete de tinta em cima. É o lugar dos "cartões": em vez de caixas iguais empilhadas, a página se lê como uma matéria.
 */
@Component({
  selector: 'fab-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section
      class="grid gap-x-10 gap-y-5 border-t-2 border-ink py-9 md:grid-cols-[minmax(0,14rem)_minmax(0,1fr)] xl:grid-cols-[minmax(0,17rem)_minmax(0,1fr)]"
      [attr.aria-labelledby]="headingId()"
    >
      <div>
        <h2 [id]="headingId()">{{ title() }}</h2>
        @if (hint()) {
          <p class="mt-3 font-text text-small text-ink-soft">{{ hint() }}</p>
        }
        <ng-content select="[slot=aside]" />
      </div>
      <div class="min-w-0"><ng-content /></div>
    </section>
  `,
  host: { class: 'block' },
})
export class SectionComponent {
  readonly title = input.required<string>();
  readonly hint = input('');
  readonly headingId = input.required<string>();
}
