import { Pipe, PipeTransform, inject } from '@angular/core';

import { I18nService } from './i18n.service';

/** `{{ 'nav.fila' | t }}` ou `{{ 'fila.eta' | t: { time: '2 min' } }}`. Impuro de propósito: precisa reagir à troca de idioma. */
@Pipe({ name: 't', pure: false })
export class TPipe implements PipeTransform {
  private readonly i18n = inject(I18nService);

  transform(key: string, params?: Record<string, string | number>): string {
    return this.i18n.t(key, params);
  }
}
