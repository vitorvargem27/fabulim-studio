import { AccordionContent, AccordionGroup, AccordionPanel, AccordionTrigger } from '@angular/aria/accordion';
import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { formatTime } from '../../core/format';
import { TPipe } from '../../core/i18n/t.pipe';
import { ServiceState } from '../../core/models';
import { StatusService } from '../../core/status.service';
import { BadgeComponent, BadgeTone } from '../../ui/badge';
import { IconComponent } from '../../ui/icon';
import { SectionComponent } from '../../ui/section';

const TONES: Record<ServiceState, BadgeTone> = { ok: 'ok', warning: 'warning', error: 'error', inactive: 'neutral' };

/**
 * Cada serviço com estado, detalhe, "como corrigir" (acordeão do Angular Aria, sem estilo próprio) e atalho para os
 * logs dele. Os que estão em uso vêm primeiro; os que ainda não foram instalados ou conectados ficam num bloco à parte.
 */
@Component({
  selector: 'fab-servicos-page',
  imports: [
    AccordionContent,
    AccordionGroup,
    AccordionPanel,
    AccordionTrigger,
    NgTemplateOutlet,
    RouterLink,
    TPipe,
    BadgeComponent,
    IconComponent,
    SectionComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './servicos.page.html',
})
export class ServicosPage {
  protected readonly status = inject(StatusService);
  protected readonly time = formatTime;
  protected readonly attention = computed(() => this.status.services().filter((s) => s.state === 'warning' || s.state === 'error'));
  protected readonly working = computed(() => this.status.services().filter((s) => s.state === 'ok'));
  protected readonly notActive = computed(() => this.status.services().filter((s) => s.state === 'inactive'));

  protected tone(state: ServiceState): BadgeTone {
    return TONES[state];
  }
}
