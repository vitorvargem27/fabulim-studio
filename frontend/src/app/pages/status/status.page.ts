import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { TPipe } from '../../core/i18n/t.pipe';
import { PageHeaderComponent } from '../../ui/page-header';

/** Casca da área Status: três abas por rota (Serviços, Sua máquina, Logs). */
@Component({
  selector: 'fab-status-page',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, TPipe, PageHeaderComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <fab-page-header [title]="'nav.status' | t" [subtitle]="'status.lead' | t" />
    <nav class="tabs" [attr.aria-label]="'status.tabs' | t">
      <a class="tab" routerLink="servicos" routerLinkActive="active" ariaCurrentWhenActive="page">{{ 'status.tab.servicos' | t }}</a>
      <a class="tab" routerLink="maquina" routerLinkActive="active" ariaCurrentWhenActive="page">{{ 'status.tab.maquina' | t }}</a>
      <a class="tab" routerLink="logs" routerLinkActive="active" ariaCurrentWhenActive="page">{{ 'status.tab.logs' | t }}</a>
    </nav>
    <div class="tab-body pt-8"><router-outlet /></div>
  `,
})
export class StatusPage {}
