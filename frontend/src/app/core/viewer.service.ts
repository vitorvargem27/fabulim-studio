import { Injectable, signal } from '@angular/core';

import { Media } from './models';

export interface ViewerItem {
  media: Media;
  /** título opcional (senão, o papel da mídia) */
  title?: string;
}

/** Abre uma imagem, vídeo ou áudio em tela grande, de qualquer página. O visualizador fica no `app.html`. */
@Injectable({ providedIn: 'root' })
export class ViewerService {
  readonly current = signal<ViewerItem | null>(null);

  open(media: Media, title?: string): void {
    this.current.set({ media, title });
  }

  close(): void {
    this.current.set(null);
  }
}

/** Endereço de download da mídia, com um nome de arquivo sugerido. */
export function downloadUrl(media: Media, name?: string): string {
  const suffix = name ? `&name=${encodeURIComponent(name)}` : '';
  return `${media.url}?download=true${suffix}`;
}
