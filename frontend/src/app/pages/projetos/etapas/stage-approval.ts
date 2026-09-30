import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';

import { TPipe } from '../../../core/i18n/t.pipe';
import { StageId } from '../../../core/models';
import { BadgeComponent } from '../../../ui/badge';
import { IconComponent } from '../../../ui/icon';
import { ProjectStore } from '../project.store';

/**
 * O rodapé de cada etapa: aprovar (com o que falta, se faltar algo) ou reabrir. Nada avança sem a aprovação do usuário
 * (briefing 7.4); reabrir não apaga o que foi gerado, só volta a pedir aprovação daqui para a frente.
 */
@Component({
  selector: 'fab-stage-approval',
  imports: [BadgeComponent, IconComponent, TPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (info(); as s) {
      <div class="flex flex-wrap items-center gap-3 border-t-2 border-rule-soft pt-5">
        @if (s.approved) {
          <fab-badge tone="ok">{{ 'proj.approval.done' | t }}</fab-badge>
          <button type="button" class="btn btn-sm" (click)="store.reopenStage(stage())" [disabled]="store.busy()">{{ 'proj.approval.reopen' | t }}</button>
        } @else {
          @if (hasScenes() && pending() > 0) {
            <button type="button" class="btn" (click)="store.approveStage(stage(), true)" [disabled]="store.busy() || !s.ready">
              <fab-icon name="check" [size]="18" />
              {{ 'proj.approval.all' | t: { n: pending() } }}
            </button>
          }
          <button type="button" class="btn btn-primary" (click)="store.approveStage(stage(), false)" [disabled]="store.busy() || !s.ready || (hasScenes() && pending() > 0)">
            <fab-icon name="check" [size]="18" />
            {{ 'proj.approval.approve' | t }}
          </button>
          @if (!s.ready && s.missing) {
            <span class="text-small text-ink-soft">{{ s.missing }}</span>
          } @else if (hasScenes() && pending() > 0) {
            <span class="text-small text-ink-soft">{{ 'proj.approval.pending' | t: { n: pending() } }}</span>
          }
        }
      </div>
    }
  `,
})
export class StageApprovalComponent {
  readonly stage = input.required<StageId>();
  protected readonly store = inject(ProjectStore);

  protected readonly info = computed(() => this.store.stage(this.stage()));
  protected readonly hasScenes = computed(() => this.info()?.scenes_total !== undefined);
  protected readonly pending = computed(() => {
    const s = this.info();
    return s?.scenes_total !== undefined ? s.scenes_total - (s.scenes_approved ?? 0) : 0;
  });
}
