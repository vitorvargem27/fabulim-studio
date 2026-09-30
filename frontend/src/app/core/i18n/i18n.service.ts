import { DOCUMENT } from '@angular/common';
import { Injectable, effect, inject, signal } from '@angular/core';

import { EN } from './en';
import { PT_BR } from './pt-br';

export type Lang = 'pt-BR' | 'en';

const STORAGE_KEY = 'fabulim.lang';
const DICTIONARIES: Record<Lang, Record<string, string>> = { 'pt-BR': PT_BR, en: EN };

/** Traduções em tempo de execução (PT-BR é o padrão; EN já está preparado). Chave ausente cai no PT-BR e por fim na própria chave. */
@Injectable({ providedIn: 'root' })
export class I18nService {
  private readonly doc = inject(DOCUMENT);
  readonly lang = signal<Lang>(this.read());

  constructor() {
    effect(() => {
      this.doc.documentElement.lang = this.lang();
    });
  }

  set(lang: Lang): void {
    this.lang.set(lang);
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch {
      /* armazenamento bloqueado: vale só nesta sessão */
    }
  }

  /**
   * Lê o idioma atual (o signal é lido aqui, então templates que chamam `t` reagem à troca de idioma).
   * `{nome}` vira o valor do parâmetro; `{nome#singular|plural}` escolhe a palavra pelo valor (1 é singular).
   */
  t(key: string, params?: Record<string, string | number>): string {
    const text = DICTIONARIES[this.lang()][key] ?? PT_BR[key] ?? key;
    if (!params) return text;
    return text.replace(/\{(\w+)(?:#([^|}]*)\|([^}]*))?\}/g, (marcador: string, name: string, one?: string, many?: string) => {
      const value = params[name];
      if (one !== undefined && many !== undefined) return value === undefined ? marcador : Number(value) === 1 ? one : many;
      return String(value ?? marcador);
    });
  }

  private read(): Lang {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === 'pt-BR' || saved === 'en') return saved;
    } catch {
      /* sem armazenamento */
    }
    return 'pt-BR';
  }
}
