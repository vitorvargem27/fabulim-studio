import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';

import { TPipe } from '../core/i18n/t.pipe';
import { Media } from '../core/models';
import { ViewerService } from '../core/viewer.service';
import { IconComponent } from './icon';

/**
 * Uma mídia da biblioteca como miniatura: clicar abre em tela grande. Recortes (PNG transparente) aparecem sobre xadrez;
 * vídeo ganha o símbolo de tocar; áudio mostra o tocador. As ações da página entram pelo conteúdo projetado.
 */
@Component({
  selector: 'fab-media-tile',
  imports: [IconComponent, TPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <figure class="m-0 grid content-start gap-2 border-2 bg-panel p-2" [class]="selected() ? 'border-ink shadow-hard' : 'border-rule-soft'">
      @if (media().kind === 'audio') {
        <audio class="w-full" [src]="media().url" controls preload="none" [attr.aria-label]="caption() || media().role"></audio>
      } @else {
        <button
          type="button"
          class="relative block w-full cursor-zoom-in overflow-hidden border-0 bg-transparent p-0"
          (click)="open()"
          [attr.aria-label]="('tile.open' | t) + ': ' + (caption() || media().role)"
        >
          @if (media().thumb_url; as src) {
            <img
              [src]="src"
              [alt]="media().prompt || caption() || media().role"
              loading="lazy"
              class="block w-full object-contain"
              [class]="isTransparent() ? 'checker' : 'bg-wash'"
              [style.aspect-ratio]="ratio()"
            />
          } @else {
            <span class="grid w-full place-items-center bg-wash text-ink-soft" [style.aspect-ratio]="ratio()">
              <fab-icon [name]="media().kind === 'video' ? 'film' : 'image'" [size]="32" />
            </span>
          }
          @if (media().kind === 'video') {
            <span class="absolute bottom-2 left-2 inline-flex items-center gap-1 border-2 border-ink bg-accent px-2 py-0.5 text-meta font-extrabold text-on-accent">
              <fab-icon name="play" [size]="12" />
              {{ length() }}
            </span>
          }
        </button>
      }
      @if (caption() || hasBadge()) {
        <figcaption class="grid gap-0.5 text-small">
          @if (caption()) {
            <strong class="font-display text-[1rem] font-semibold">{{ caption() }}</strong>
          }
          @if (detail()) {
            <span class="text-meta text-ink-soft">{{ detail() }}</span>
          }
        </figcaption>
      }
      <div class="flex flex-wrap gap-2 empty:hidden"><ng-content /></div>
    </figure>
  `,
  host: { class: 'block min-w-0' },
})
export class MediaTileComponent {
  readonly media = input.required<Media>();
  readonly caption = input('');
  readonly detail = input('');
  readonly selected = input(false);
  readonly transparent = input<boolean | null>(null);

  private readonly viewer = inject(ViewerService);

  protected readonly ratio = computed(() => {
    const { width, height } = this.media();
    return width && height ? `${width} / ${height}` : '1 / 1';
  });
  protected readonly isTransparent = computed(() => this.transparent() ?? this.media().role === 'recorte');
  protected readonly hasBadge = computed(() => !!this.detail());
  protected readonly length = computed(() => {
    const s = Math.round(this.media().duration_s ?? 0);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  });

  protected open(): void {
    this.viewer.open(this.media(), this.caption() || undefined);
  }
}
