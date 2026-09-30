import { Injectable, signal } from '@angular/core';

export type ToastTone = 'success' | 'error' | 'info';

export interface Toast {
  id: number;
  tone: ToastTone;
  text: string;
}

/** Avisos curtos ("Cena aprovada", "Diagnóstico iniciado"). Anunciados a leitores de tela pela região aria-live. */
@Injectable({ providedIn: 'root' })
export class ToastService {
  private nextId = 1;
  readonly toasts = signal<Toast[]>([]);

  show(text: string, tone: ToastTone = 'success', ms = 4500): void {
    const toast: Toast = { id: this.nextId++, tone, text };
    this.toasts.update((list) => [...list.slice(-3), toast]);
    setTimeout(() => this.dismiss(toast.id), ms);
  }

  dismiss(id: number): void {
    this.toasts.update((list) => list.filter((t) => t.id !== id));
  }
}
