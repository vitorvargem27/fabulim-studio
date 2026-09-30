import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { ApiService } from '../../../core/api.service';
import { I18nService } from '../../../core/i18n/i18n.service';
import { TPipe } from '../../../core/i18n/t.pipe';
import { MachineService } from '../../../core/machine.service';
import { EmptyStateComponent } from '../../../ui/empty-state';
import { IconComponent } from '../../../ui/icon';
import { SectionComponent } from '../../../ui/section';
import { ProjectStore } from '../project.store';
import { SceneEditorComponent } from './scene-editor';
import { StageApprovalComponent } from './stage-approval';

/** Etapa 2: o roteiro. O modelo local escreve as cenas (ou o modo simples divide a história sem IA); você edita cada uma. */
@Component({
  selector: 'fab-etapa-roteiro',
  imports: [TPipe, EmptyStateComponent, IconComponent, SceneEditorComponent, SectionComponent, StageApprovalComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <fab-section headingId="roteiro" [title]="'proj.stage.roteiro' | t" [hint]="'proj.roteiro.hint' | t">
      <div class="grid gap-4">
        <div class="flex flex-wrap items-center gap-3">
          <button type="button" class="btn btn-primary" (click)="generate('ia')" [disabled]="store.busy() || store.hasActive('projeto.roteiro')">
            <fab-icon name="sparkles" [size]="18" />
            {{ (hasScenes() ? 'proj.roteiro.again' : 'proj.roteiro.generate') | t }}
          </button>
          <button type="button" class="btn" (click)="generate('simples')" [disabled]="store.busy() || store.hasActive('projeto.roteiro')">
            {{ 'proj.roteiro.simple' | t }}
          </button>
        </div>
        @if (llm(); as cap) {
          <p class="font-text text-small text-ink-soft">{{ cap.reason }}@if (cap.eta) { · {{ cap.eta }} }</p>
        }
        @if (hasScenes()) {
          <p class="text-small text-ink-soft">{{ 'proj.roteiro.replaces' | t }}</p>
        }
        @for (notice of store.notices(); track notice) {
          <p class="banner" role="status">{{ notice }}</p>
        }
      </div>
    </fab-section>

    <fab-section headingId="cenas" [title]="('proj.scenes.title' | t) + ' (' + store.scenes().length + ')'" [hint]="'proj.scenes.hint' | t">
      @if (hasScenes()) {
        <div class="grid gap-5">
          @for (scene of store.scenes(); track scene.id; let i = $index) {
            <fab-scene-editor [scene]="scene" [index]="i" [count]="store.scenes().length" />
          }
          <div><button type="button" class="btn" (click)="addScene()" [disabled]="store.busy()">{{ 'proj.scene.add' | t }}</button></div>
        </div>
      } @else {
        <fab-empty [title]="'proj.scenes.empty.title' | t" [text]="'proj.scenes.empty.text' | t">
          <button type="button" class="btn" (click)="addScene()" [disabled]="store.busy()">{{ 'proj.scene.add' | t }}</button>
        </fab-empty>
      }
    </fab-section>
    <fab-stage-approval stage="roteiro" />
  `,
})
export class EtapaRoteiro {
  protected readonly store = inject(ProjectStore);
  private readonly api = inject(ApiService);
  private readonly machine = inject(MachineService);
  private readonly i18n = inject(I18nService);

  protected readonly hasScenes = computed(() => this.store.scenes().length > 0);
  protected readonly llm = computed(() => this.machine.capability('llm_local'));

  protected generate(mode: 'ia' | 'simples'): void {
    if (this.hasScenes() && !window.confirm(this.i18n.t('proj.roteiro.confirm'))) return;
    this.store.startJob(this.api.generateScript(this.store.id(), mode));
  }

  protected addScene(): void {
    const characters = this.store.characters().slice(0, 1).map((c) => c.id);
    this.store.run(this.api.createScene(this.store.id(), { title: this.i18n.t('proj.scene.new'), characters }), () =>
      this.store.load(this.store.id()),
    );
  }
}
