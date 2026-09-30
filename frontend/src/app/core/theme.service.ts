import { DOCUMENT } from '@angular/common';
import { Injectable, computed, effect, inject, signal } from '@angular/core';

export type ThemePreference = 'light' | 'dark' | 'system';

const STORAGE_KEY = 'fabulim.theme';
const COLORS = { light: '#f6f4ff', dark: '#15163a' } as const;

/** Tema claro/escuro. A escolha fica no navegador; "system" segue o sistema operacional. */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly doc = inject(DOCUMENT);
  private readonly media = this.doc.defaultView?.matchMedia?.('(prefers-color-scheme: dark)') ?? null;
  private readonly systemDark = signal(this.media?.matches ?? false);

  readonly preference = signal<ThemePreference>(this.read());
  readonly effective = computed<'light' | 'dark'>(() => {
    const pref = this.preference();
    return pref === 'system' ? (this.systemDark() ? 'dark' : 'light') : pref;
  });

  constructor() {
    this.media?.addEventListener('change', (e) => this.systemDark.set(e.matches));
    effect(() => {
      const theme = this.effective();
      this.doc.documentElement.setAttribute('data-theme', theme);
      this.doc.querySelector('meta[name="theme-color"]')?.setAttribute('content', COLORS[theme]);
    });
  }

  set(pref: ThemePreference): void {
    this.preference.set(pref);
    try {
      localStorage.setItem(STORAGE_KEY, pref);
    } catch {
      /* armazenamento bloqueado (janela privada): a escolha vale só nesta sessão */
    }
  }

  toggle(): void {
    this.set(this.effective() === 'dark' ? 'light' : 'dark');
  }

  private read(): ThemePreference {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === 'light' || saved === 'dark' || saved === 'system') return saved;
    } catch {
      /* sem armazenamento: segue o sistema */
    }
    return 'system';
  }
}
