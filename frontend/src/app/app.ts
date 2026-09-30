import { CdkTrapFocus } from '@angular/cdk/a11y';
import { DOCUMENT } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';

import { ApiService } from './core/api.service';
import { I18nService } from './core/i18n/i18n.service';
import { TPipe } from './core/i18n/t.pipe';
import { JobsService } from './core/jobs.service';
import { MachineService } from './core/machine.service';
import { MarcaService } from './core/marca.service';
import { AppMeta } from './core/models';
import { StatusService } from './core/status.service';
import { ThemeService } from './core/theme.service';
import { ClaudeIndicatorComponent } from './layout/claude-indicator';
import { LogoComponent } from './layout/logo';
import { NAV_ITEMS } from './core/nav';
import { IconComponent } from './ui/icon';
import { ToastHostComponent } from './ui/toast-host';
import { ViewerHostComponent } from './ui/viewer-host';

/** 900 px: abaixo disso a barra lateral vira gaveta (menu hambúrguer). */
const DRAWER_QUERY = '(max-width: 56.24rem)';

@Component({
  selector: 'app-root',
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    CdkTrapFocus,
    IconComponent,
    LogoComponent,
    ClaudeIndicatorComponent,
    ToastHostComponent,
    ViewerHostComponent,
    TPipe,
  ],
  templateUrl: './app.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '(document:keydown.escape)': 'closeNav()' },
})
export class App {
  private readonly router = inject(Router);
  private readonly doc = inject(DOCUMENT);
  private readonly api = inject(ApiService);
  protected readonly jobs = inject(JobsService);
  protected readonly theme = inject(ThemeService);
  protected readonly i18n = inject(I18nService);
  protected readonly machine = inject(MachineService);
  private readonly status = inject(StatusService);
  private readonly marca = inject(MarcaService);

  protected readonly navOpen = signal(false);
  protected readonly meta = signal<AppMeta | null>(null);
  protected readonly profileLetter = computed(() => this.machine.profile()?.letter ?? null);

  protected readonly navItems = NAV_ITEMS;

  constructor() {
    this.marca.load();
    this.jobs.connect();
    this.status.startAutoRefresh();
    this.machine.refresh();
    this.api.meta().subscribe({ next: (meta) => this.meta.set(meta), error: () => undefined });

    let first = true;
    this.router.events
      .pipe(
        filter((e) => e instanceof NavigationEnd),
        takeUntilDestroyed(),
      )
      .subscribe(() => {
        this.navOpen.set(false);
        if (first) first = false;
        else this.focusMain(); // anuncia a nova página para leitores de tela e teclado
      });

    // se a janela crescer com a gaveta aberta, fecha (senão o foco ficaria preso numa barra que já é fixa)
    const media = this.doc.defaultView?.matchMedia?.(DRAWER_QUERY);
    if (media) {
      const onChange = (e: MediaQueryListEvent): void => {
        if (!e.matches) this.navOpen.set(false);
      };
      media.addEventListener('change', onChange);
      inject(DestroyRef).onDestroy(() => media.removeEventListener('change', onChange));
    }
  }

  protected toggleNav(): void {
    this.navOpen.update((open) => !open);
  }

  protected closeNav(): void {
    this.navOpen.set(false);
  }

  protected focusMain(event?: Event): void {
    event?.preventDefault();
    this.doc.getElementById('conteudo')?.focus({ preventScroll: false });
  }

  protected toggleLang(): void {
    this.i18n.set(this.i18n.lang() === 'pt-BR' ? 'en' : 'pt-BR');
  }
}
