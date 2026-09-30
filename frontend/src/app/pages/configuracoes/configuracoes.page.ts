import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { I18nService, Lang } from '../../core/i18n/i18n.service';
import { TPipe } from '../../core/i18n/t.pipe';
import { AppMeta } from '../../core/models';
import { StatusService } from '../../core/status.service';
import { ThemePreference, ThemeService } from '../../core/theme.service';
import { BadgeComponent } from '../../ui/badge';
import { PageHeaderComponent } from '../../ui/page-header';
import { SectionComponent } from '../../ui/section';
import { SegmentedComponent, SegmentedOption } from '../../ui/segmented';

@Component({
  selector: 'fab-configuracoes-page',
  imports: [RouterLink, TPipe, BadgeComponent, PageHeaderComponent, SectionComponent, SegmentedComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './configuracoes.page.html',
})
export class ConfiguracoesPage {
  protected readonly theme = inject(ThemeService);
  protected readonly i18n = inject(I18nService);
  private readonly status = inject(StatusService);

  protected readonly meta = signal<AppMeta | null>(null);
  protected readonly claude = this.status.claude;
  protected readonly connected = computed(() => this.claude()?.state === 'ok');

  protected readonly themeOptions = computed<SegmentedOption[]>(() => {
    this.i18n.lang(); // recalcula os rótulos quando o idioma muda
    return [
      { value: 'light', label: this.i18n.t('theme.light') },
      { value: 'dark', label: this.i18n.t('theme.dark') },
      { value: 'system', label: this.i18n.t('theme.system') },
    ];
  });
  protected readonly langOptions: SegmentedOption[] = [
    { value: 'pt-BR', label: 'Português' },
    { value: 'en', label: 'English' },
  ];

  constructor() {
    inject(ApiService).meta().subscribe({ next: (m) => this.meta.set(m), error: () => undefined });
  }

  protected setTheme(value: string): void {
    this.theme.set(value as ThemePreference);
  }

  protected setLang(value: string): void {
    this.i18n.set(value as Lang);
  }
}
