import { ViewportScroller } from '@angular/common';
import { ChangeDetectionStrategy, Component, Injector, afterNextRender, computed, effect, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { formatBytes } from '../../core/format';
import { I18nService } from '../../core/i18n/i18n.service';
import { TPipe } from '../../core/i18n/t.pipe';
import { isActive, JobsService } from '../../core/jobs.service';
import { Job, ToolItem } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { BadgeComponent } from '../../ui/badge';
import { IconComponent } from '../../ui/icon';
import { PageHeaderComponent } from '../../ui/page-header';
import { ProgressComponent } from '../../ui/progress';
import { SectionComponent } from '../../ui/section';

const GROUPS = ['ffmpeg', 'imagem', 'voz', 'recorte'] as const;
const KIND = 'ferramentas.instalar';

interface Group {
  id: string;
  items: ToolItem[];
}

/**
 * Os programas e modelos que o estúdio usa, com estado, tamanho e licença. Instalar é sempre um clique do usuário e
 * vira um job na Fila (com progresso ao vivo); só itens do catálogo, de fonte oficial, com o SHA-256 conferido.
 */
@Component({
  selector: 'fab-modelos-page',
  imports: [TPipe, BadgeComponent, IconComponent, PageHeaderComponent, ProgressComponent, SectionComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './modelos.page.html',
})
export class ModelosPage {
  private readonly api = inject(ApiService);
  private readonly jobs = inject(JobsService);
  private readonly toast = inject(ToastService);
  private readonly i18n = inject(I18nService);
  private readonly route = inject(ActivatedRoute);
  private readonly viewport = inject(ViewportScroller);
  private readonly injector = inject(Injector);

  protected readonly items = signal<ToolItem[]>([]);
  protected readonly failed = signal(false);
  protected readonly loaded = signal(false);
  protected readonly bytes = formatBytes;

  protected readonly groups = computed<Group[]>(() =>
    GROUPS.map((id) => ({ id, items: this.items().filter((item) => item.group === id) })).filter((g) => g.items.length),
  );
  protected readonly missing = computed(() => this.items().filter((item) => !item.installed && !this.jobFor(item)));

  private readonly seenActive = new Set<string>();
  private readonly handled = new Set<string>();

  constructor() {
    this.load();
    // O link "Ver as vozes" (Criar vídeo) chega com `#voz`, mas os grupos só existem depois que a lista carrega:
    // o roteador já tentou rolar e não achou nada, então rolamos até o grupo assim que ele aparece na tela.
    effect(() => {
      const fragment = this.route.snapshot.fragment;
      if (this.loaded() && fragment) afterNextRender(() => this.viewport.scrollToAnchor(fragment), { injector: this.injector });
    });
    effect(() => {
      for (const job of this.jobs.jobs()) {
        if (job.kind !== KIND) continue;
        if (isActive(job)) {
          this.seenActive.add(job.id);
        } else if (this.seenActive.has(job.id) && !this.handled.has(job.id)) {
          this.handled.add(job.id);
          this.load();
          const name = this.nameOf(String(job.params['id']));
          const ok = job.status === 'done';
          if (job.status !== 'canceled') {
            this.toast.show(this.i18n.t(ok ? 'modelos.job.done' : 'modelos.job.failed', { name }), ok ? 'success' : 'error');
          }
        }
      }
    });
  }

  protected jobFor(item: ToolItem): Job | null {
    return this.jobs.active().find((j) => j.kind === KIND && j.params['id'] === item.id) ?? null;
  }

  protected install(item: ToolItem): void {
    this.api.installTool(item.id).subscribe({
      next: (job) => {
        this.jobs.merge(job);
        this.toast.show(this.i18n.t('modelos.job.queued', { name: item.name }), 'info');
      },
      error: () => this.toast.show(this.i18n.t('common.error.request'), 'error'),
    });
  }

  protected installAll(): void {
    for (const item of this.missing()) this.install(item);
  }

  private load(): void {
    this.api.tools().subscribe({
      next: (report) => {
        this.items.set(report.items);
        this.failed.set(false);
        this.loaded.set(true);
      },
      error: () => {
        this.failed.set(true);
        this.loaded.set(true);
      },
    });
  }

  private nameOf(id: string): string {
    return this.items().find((item) => item.id === id)?.name ?? id;
  }
}
