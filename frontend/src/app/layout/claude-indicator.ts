import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { TPipe } from '../core/i18n/t.pipe';
import { StatusService } from '../core/status.service';
import { BadgeComponent } from '../ui/badge';

/** "Claude: conectado / desconectado", fixo no topo de todas as páginas; leva ao card "Conta do Claude". */
@Component({
  selector: 'fab-claude-indicator',
  imports: [RouterLink, BadgeComponent, TPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <a class="util" routerLink="/configuracoes" fragment="claude" [title]="'topbar.claude.title' | t">
      <fab-badge [tone]="connected() ? 'ok' : 'neutral'">
        <span class="max-sm:sr-only">{{ (connected() ? 'topbar.claude.on' : 'topbar.claude.off') | t }}</span>
      </fab-badge>
    </a>
  `,
  host: { class: 'contents' },
})
export class ClaudeIndicatorComponent {
  private readonly status = inject(StatusService);
  protected readonly connected = computed(() => this.status.claude()?.state === 'ok');
}
