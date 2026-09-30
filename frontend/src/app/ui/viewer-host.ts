import { ChangeDetectionStrategy, Component, ElementRef, effect, inject, viewChild } from '@angular/core';

import { formatBytes, formatDuration } from '../core/format';
import { TPipe } from '../core/i18n/t.pipe';
import { downloadUrl, ViewerService } from '../core/viewer.service';
import { IconComponent } from './icon';

/**
 * Visualizador em tela grande, feito com o elemento nativo `<dialog>`: o navegador cuida do foco preso, do Esc e do fundo.
 * Mostra imagem (com xadrez atrás, para ver a transparência), vídeo ou áudio, os dados da geração e o botão de baixar.
 */
@Component({
  selector: 'fab-viewer-host',
  imports: [IconComponent, TPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <dialog #dialog class="viewer" [attr.aria-label]="'viewer.label' | t" (close)="viewer.close()" (click)="backdrop($event)">
      @if (viewer.current(); as item) {
        <div class="flex items-center justify-between gap-3 border-b-2 border-ink px-4 py-2">
          <strong class="font-display text-[1.125rem] font-semibold">{{ item.title || item.media.role }}</strong>
          <div class="flex items-center gap-2">
            <a class="btn btn-sm" [href]="download(item.media)" download>{{ 'viewer.download' | t }}</a>
            <button type="button" class="btn btn-icon btn-sm" (click)="viewer.close()" [attr.aria-label]="'viewer.close' | t">
              <fab-icon name="close" [size]="18" />
            </button>
          </div>
        </div>
        <div class="grid place-items-center bg-wash p-3">
          @switch (item.media.kind) {
            @case ('video') {
              <video class="max-h-[70dvh] max-w-full bg-anil" [src]="item.media.url" controls autoplay playsinline></video>
            }
            @case ('audio') {
              <audio class="w-full" [src]="item.media.url" controls autoplay></audio>
            }
            @case ('imagem') {
              <img class="checker max-h-[70dvh] max-w-full object-contain" [src]="item.media.url" [alt]="item.media.prompt || item.title || item.media.role" />
            }
            @default {
              <a [href]="item.media.url">{{ item.media.url }}</a>
            }
          }
        </div>
        <dl class="facts m-0 px-4 py-3 text-small">
          @if (item.media.width && item.media.height) {
            <dt>{{ 'viewer.size' | t }}</dt>
            <dd>{{ item.media.width }} × {{ item.media.height }}</dd>
          }
          @if (item.media.duration_s) {
            <dt>{{ 'viewer.duration' | t }}</dt>
            <dd>{{ duration(item.media.duration_s) }}</dd>
          }
          @if (item.media.size_bytes) {
            <dt>{{ 'viewer.file' | t }}</dt>
            <dd>{{ bytes(item.media.size_bytes) }}</dd>
          }
          @if (item.media.seed !== null) {
            <dt>{{ 'viewer.seed' | t }}</dt>
            <dd>{{ item.media.seed }}</dd>
          }
          @if (item.media.model) {
            <dt>{{ 'viewer.model' | t }}</dt>
            <dd>{{ item.media.model }}</dd>
          }
          @if (item.media.prompt) {
            <dt>{{ 'viewer.prompt' | t }}</dt>
            <dd>{{ item.media.prompt }}</dd>
          }
        </dl>
      }
    </dialog>
  `,
})
export class ViewerHostComponent {
  protected readonly viewer = inject(ViewerService);
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  protected readonly bytes = formatBytes;
  protected readonly duration = formatDuration;

  constructor() {
    effect(() => {
      const element = this.dialog().nativeElement;
      const open = this.viewer.current() !== null;
      if (open && !element.open) {
        if (typeof element.showModal === 'function') element.showModal();
        else element.setAttribute('open', ''); // ambientes sem <dialog> modal (testes)
      } else if (!open && element.open) {
        if (typeof element.close === 'function') element.close();
        else element.removeAttribute('open');
      }
    });
  }

  protected readonly download = downloadUrl;

  /** Clicar no fundo escuro (fora da caixa) fecha. */
  protected backdrop(event: MouseEvent): void {
    if (event.target === this.dialog().nativeElement) this.viewer.close();
  }
}
