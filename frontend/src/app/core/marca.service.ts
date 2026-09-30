import { DOCUMENT } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';

export interface MarcaAssets {
  icon: boolean;
  icon_png: boolean;
  logo: boolean;
  logo_dark: boolean;
}

const NONE: MarcaAssets = { icon: false, icon_png: false, logo: false, logo_dark: false };

/**
 * Arquivos oficiais da marca. `scripts/copiar-marca.mjs` copia `marca/*` para `public/marca/` e grava o manifest.json.
 * Sem os arquivos, a interface usa o logotipo em texto (o briefing proíbe redesenhar o logo).
 */
@Injectable({ providedIn: 'root' })
export class MarcaService {
  private readonly http = inject(HttpClient);
  private readonly doc = inject(DOCUMENT);
  readonly assets = signal<MarcaAssets>(NONE);

  load(): void {
    this.http.get<MarcaAssets>('marca/manifest.json').subscribe({
      next: (assets) => {
        this.assets.set({ ...NONE, ...assets });
        if (assets.icon) {
          const link = this.doc.querySelector<HTMLLinkElement>('link[rel="icon"]');
          if (link) {
            link.href = 'marca/fabulim-icone.svg';
            link.type = 'image/svg+xml';
          }
        }
      },
      error: () => this.assets.set(NONE),
    });
  }
}
