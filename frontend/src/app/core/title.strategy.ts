import { Injectable, effect, inject } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterStateSnapshot, TitleStrategy } from '@angular/router';

import { I18nService } from './i18n/i18n.service';

/** Título da aba = "Página · Fabulim Studio", traduzido a partir da chave `title` da rota. Acompanha a troca de idioma. */
@Injectable({ providedIn: 'root' })
export class FabTitleStrategy extends TitleStrategy {
  private readonly title = inject(Title);
  private readonly i18n = inject(I18nService);
  private ultima: RouterStateSnapshot | null = null;

  constructor() {
    super();
    // a leitura explícita do idioma é a dependência do efeito (na 1ª execução ainda não há rota): ao trocá-lo, o título acompanha
    effect(() => {
      this.i18n.lang();
      if (this.ultima) this.aplicar(this.ultima);
    });
  }

  override updateTitle(snapshot: RouterStateSnapshot): void {
    this.ultima = snapshot;
    this.aplicar(snapshot);
  }

  private aplicar(snapshot: RouterStateSnapshot): void {
    const key = this.buildTitle(snapshot);
    this.title.setTitle(key ? `${this.i18n.t(key)} · Fabulim Studio` : 'Fabulim Studio');
  }
}
