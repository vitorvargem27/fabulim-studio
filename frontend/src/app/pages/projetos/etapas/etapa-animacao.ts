import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';

import { ApiService } from '../../../core/api.service';
import { TPipe } from '../../../core/i18n/t.pipe';
import { MachineService } from '../../../core/machine.service';
import { Scene } from '../../../core/models';
import { BadgeComponent } from '../../../ui/badge';
import { EmptyStateComponent } from '../../../ui/empty-state';
import { IconComponent } from '../../../ui/icon';
import { MediaTileComponent } from '../../../ui/media-tile';
import { SectionComponent } from '../../../ui/section';
import { ProjectStore } from '../project.store';
import { StageApprovalComponent } from './stage-approval';

/**
 * Etapa 4: a animação. Neste computador a animação é feita por código (respirar, pular, andar, entrada, câmera e boca que
 * acompanha a voz), quadro a quadro, e não por um modelo de vídeo de IA, que pede uma placa de vídeo com muita memória.
 */
@Component({
  selector: 'fab-etapa-animacao',
  imports: [TPipe, BadgeComponent, EmptyStateComponent, IconComponent, MediaTileComponent, SectionComponent, StageApprovalComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <fab-section headingId="animacao" [title]="'proj.stage.animacao' | t" [hint]="'proj.anim.hint' | t">
      @if (store.scenes().length) {
        <div class="grid gap-4">
          @if (scene(); as cap) {
            <p class="font-text text-small text-ink-soft">{{ cap.reason }}@if (cap.eta) { · {{ cap.eta }} }</p>
          }
          <div class="flex flex-col gap-2">
            <label class="inline-flex items-center gap-2 font-normal">
              <input type="checkbox" [checked]="draft()" (change)="draft.set($any($event.target).checked)" />
              {{ 'proj.anim.draft' | t }}
            </label>
            <label class="inline-flex items-center gap-2 font-normal">
              <input type="checkbox" [checked]="force()" (change)="force.set($any($event.target).checked)" />
              {{ 'proj.anim.force' | t }}
            </label>
          </div>
          <div class="flex flex-wrap items-center gap-3">
            <button type="button" class="btn btn-primary" (click)="animate()" [disabled]="store.busy() || store.hasActive('projeto.animar')">
              <fab-icon name="film" [size]="18" />
              {{ (picked().length ? 'proj.anim.picked' : 'proj.anim.all') | t: { n: picked().length } }}
            </button>
            @if (picked().length) {
              <button type="button" class="btn btn-sm btn-quiet" (click)="picked.set([])">{{ 'proj.sb.clear' | t }}</button>
            }
          </div>
          @if (ai(); as cap) {
            <p class="banner banner-info" role="note">{{ 'proj.anim.ai' | t }} {{ cap.reason }}</p>
          }
        </div>
      } @else {
        <fab-empty [title]="'proj.sb.noscenes.title' | t" [text]="'proj.sb.noscenes.text' | t" />
      }
    </fab-section>

    @if (store.scenes().length) {
      <fab-section headingId="cenas-anim" [title]="('proj.scenes.title' | t) + ' (' + store.scenes().length + ')'" [hint]="'proj.anim.scenes.hint' | t">
        <div class="tile-grid tile-grid-wide">
          @for (scene of store.scenes(); track scene.id) {
            <div class="grid content-start gap-2 border-2 border-ink bg-panel p-2">
              <div class="flex flex-wrap items-center gap-2">
                <label class="inline-flex items-center gap-2 font-normal">
                  <input type="checkbox" [checked]="picked().includes(scene.id)" (change)="togglePick(scene.id, $any($event.target).checked)" [attr.aria-label]="'proj.sb.pick' | t: { n: scene.order }" />
                </label>
                <span class="bg-accent px-2 py-0.5 font-mono text-meta font-extrabold text-on-accent">{{ scene.order }}</span>
                <strong class="min-w-0 flex-1 font-display font-semibold">{{ scene.data.title }}</strong>
                <fab-badge [tone]="scene.data.approved['animacao'] ? 'ok' : scene.clip_media ? 'info' : 'neutral'">
                  {{ (scene.data.approved['animacao'] ? 'proj.scene.approved' : scene.clip_media ? 'proj.anim.ready' : 'proj.anim.none') | t }}
                </fab-badge>
              </div>
              @if (scene.clip_media; as clip) {
                <fab-media-tile [media]="clip" [detail]="quality(scene)" />
              } @else if (scene.keyframe) {
                <fab-media-tile [media]="scene.keyframe" [detail]="'proj.anim.noclip' | t" />
              } @else {
                <div class="grid aspect-video place-items-center bg-wash p-3 text-center text-small text-ink-soft">{{ 'proj.sb.noimage' | t }}</div>
              }
              <div class="flex flex-wrap gap-2">
                <button type="button" class="btn btn-sm" (click)="animateOne(scene)" [disabled]="store.busy() || store.hasActive('projeto.animar') || !scene.data.background">
                  <fab-icon name="refresh" [size]="16" />
                  {{ 'proj.anim.one' | t }}
                </button>
                <button
                  type="button"
                  class="btn btn-sm btn-primary"
                  (click)="store.approveScene(scene, 'animacao', !scene.data.approved['animacao'])"
                  [disabled]="store.busy() || (!scene.data.clip && !scene.data.approved['animacao'])"
                >
                  {{ (scene.data.approved['animacao'] ? 'proj.scene.unapprove' : 'proj.scene.approve') | t }}
                </button>
              </div>
            </div>
          }
        </div>
      </fab-section>
      <fab-stage-approval stage="animacao" />
    }
  `,
})
export class EtapaAnimacao {
  protected readonly store = inject(ProjectStore);
  private readonly api = inject(ApiService);
  private readonly machine = inject(MachineService);

  protected readonly draft = signal(false);
  protected readonly force = signal(false);
  protected readonly picked = signal<string[]>([]);

  protected readonly scene = computed(() => this.machine.capability('animacao_cena'));
  protected readonly ai = computed(() => {
    const cap = this.machine.capability('animacao_ia');
    return cap && cap.state === 'unavailable' ? cap : undefined;
  });

  protected togglePick(id: string, on: boolean): void {
    this.picked.update((l) => (on ? [...l.filter((x) => x !== id), id] : l.filter((x) => x !== id)));
  }

  protected quality(scene: Scene): string {
    const clip = scene.data.clip;
    return clip ? `${clip.quality} · ${clip.duration_s.toFixed(1)} s` : '';
  }

  protected animate(): void {
    const chosen = this.picked();
    this.store.startJob(this.api.animateScenes(this.store.id(), { scene_ids: chosen.length ? chosen : null, draft: this.draft(), force: this.force() }));
  }

  protected animateOne(scene: Scene): void {
    this.store.startJob(this.api.animateScenes(this.store.id(), { scene_ids: [scene.id], draft: this.draft(), force: true }));
  }
}
