import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';

import { MarcaService } from '../core/marca.service';

/**
 * Logo do Fabulim Studio, sempre sobre a barra lateral escura. Usa os arquivos oficiais de `marca/` quando existem
 * (a versão para fundo escuro); sem eles mostra o nome em texto (Fredoka), sem inventar um desenho de logo. Abaixo de
 * 120 px de largura usa só o ícone (regra da marca).
 */
@Component({
  selector: 'fab-logo',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (mode() === 'icon') {
      @if (assets().icon) {
        <img src="marca/fabulim-icone.svg" alt="Fabulim" width="40" height="40" class="block" />
      } @else {
        <span
          class="grid size-11 place-items-center border-2 border-on-rail bg-rail-accent font-display text-[1.6rem] font-semibold leading-none text-on-accent"
          aria-label="Fabulim"
          role="img"
          >F</span
        >
      }
    } @else if (logoFile(); as file) {
      <img [src]="file" alt="Fabulim Studio" height="34" class="block h-[34px] w-auto" />
    } @else {
      <span class="inline-flex items-baseline gap-[0.3em] font-display leading-none" role="img" aria-label="Fabulim Studio">
        <span class="text-[1.7rem] font-semibold tracking-tight text-on-rail">Fabulim</span
        ><span class="text-[1.05rem] font-medium text-coral">studio</span>
      </span>
    }
  `,
  host: { class: 'inline-flex items-center min-h-11' },
})
export class LogoComponent {
  readonly mode = input<'full' | 'icon'>('full');
  private readonly marca = inject(MarcaService);
  protected readonly assets = this.marca.assets;
  protected readonly logoFile = computed(() => (this.assets().logo_dark ? 'marca/fabulim-logo-escuro.svg' : null));
}
