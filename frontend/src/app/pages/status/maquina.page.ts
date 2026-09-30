import { ChangeDetectionStrategy, Component, computed, effect, inject, signal } from '@angular/core';

import { ApiService } from '../../core/api.service';
import { formatDateTime, formatGb, formatMb } from '../../core/format';
import { I18nService } from '../../core/i18n/i18n.service';
import { TPipe } from '../../core/i18n/t.pipe';
import { isActive, JobsService } from '../../core/jobs.service';
import { MachineService } from '../../core/machine.service';
import { BenchmarkResult, Capability, CapabilityState } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { BadgeComponent, BadgeTone } from '../../ui/badge';
import { EmptyStateComponent } from '../../ui/empty-state';
import { IconComponent } from '../../ui/icon';
import { ProgressComponent } from '../../ui/progress';
import { SectionComponent } from '../../ui/section';

type CapFilter = 'all' | CapabilityState;

interface Fact {
  key: string;
  lines: string[];
}
interface AccelRow {
  id: string;
  available: boolean;
  detail: string;
}
interface BenchRow {
  task: string;
  status: BenchmarkResult['status'];
  result: string;
  detail: string;
}

const WATCHED_KINDS = ['system.diagnostico', 'benchmark.calibracao'];

/** Ordem em que o benchmark mede e a tela mostra (o servidor devolve em ordem alfabética). */
const BENCH_ORDER = ['llm_ollama', 'tts', 'cutout', 'image', 'music', 'video'];
const benchRank = (task: string): number => {
  const i = BENCH_ORDER.indexOf(task);
  return i === -1 ? BENCH_ORDER.length : i;
};
const ACCEL_IDS = ['cuda', 'rocm', 'directml', 'vulkan', 'metal', 'openvino'];

/** Perfil (A a D) com justificativa, hardware detectado, aceleração, benchmark de calibração e matriz de capacidades. */
@Component({
  selector: 'fab-maquina-page',
  imports: [TPipe, BadgeComponent, EmptyStateComponent, IconComponent, ProgressComponent, SectionComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './maquina.page.html',
})
export class MaquinaPage {
  protected readonly machine = inject(MachineService);
  private readonly jobs = inject(JobsService);
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);
  private readonly i18n = inject(I18nService);

  protected readonly snap = this.machine.snapshot;
  protected readonly filter = signal<CapFilter>('all');
  protected readonly filters: CapFilter[] = ['all', 'available', 'slow', 'unavailable'];
  protected readonly date = formatDateTime;
  protected readonly gb = formatGb;

  protected readonly diagJob = computed(() => this.jobs.active().find((j) => j.kind === 'system.diagnostico') ?? null);
  protected readonly benchJob = computed(() => this.jobs.active().find((j) => j.kind === 'benchmark.calibracao') ?? null);

  private readonly seenActive = new Set<string>();
  private readonly handled = new Set<string>();

  protected readonly capabilities = computed(() => {
    const all = this.machine.capabilities();
    const f = this.filter();
    return f === 'all' ? all : all.filter((c) => c.state === f);
  });

  protected readonly counts = computed<Record<CapFilter, number>>(() => {
    const all = this.machine.capabilities();
    const count = (s: CapabilityState): number => all.filter((c) => c.state === s).length;
    return { all: all.length, available: count('available'), slow: count('slow'), unavailable: count('unavailable') };
  });

  protected readonly facts = computed<Fact[]>(() => {
    const hw = this.snap()?.hardware;
    if (!hw) return [];
    const t = (key: string, params?: Record<string, string | number>): string => this.i18n.t(key, params);
    const features = (
      [
        [hw.cpu.features.avx, 'AVX'],
        [hw.cpu.features.avx2, 'AVX2'],
        [hw.cpu.features.avx512, 'AVX-512'],
        [hw.cpu.features.neon, 'NEON'],
      ] as [boolean, string][]
    )
      .filter(([on]) => on)
      .map(([, name]) => name);
    const cpuLines = [
      hw.cpu.model,
      `${hw.cpu.cores} ${t('maquina.cores')} · ${hw.cpu.threads} threads${features.length ? ' · ' + features.join(', ') : ''}`,
      hw.cpu.npu.present ? `NPU: ${hw.cpu.npu.name ?? ''}` : t('maquina.no.npu'),
    ];
    const gpuLines = hw.gpus.length
      ? hw.gpus.map((g) => {
          const kind = t(`maquina.gpu.${g.kind}`);
          const memory =
            g.kind === 'discrete'
              ? formatGb(g.dedicated_mb) + ' VRAM'
              : g.kind === 'unified'
                ? t('maquina.gpu.unified.note')
                : `${formatMb(g.dedicated_mb)} ${t('maquina.gpu.dedicated')} + ${formatMb(g.shared_mb)} ${t('maquina.gpu.shared')}`;
          return `${g.name} · ${kind} · ${memory}`;
        })
      : [t('maquina.none')];
    const battery = hw.system.battery;
    const power = battery.present
      ? `${battery.percent ?? '?'}% · ${battery.on_ac ? t('maquina.ac') : t('maquina.battery')}`
      : t('maquina.no.battery');
    return [
      {
        key: 'maquina.fact.machine',
        lines: [
          `${hw.system.vendor} ${hw.system.marketing_name ?? hw.system.model}${hw.system.is_laptop ? ' · ' + t('maquina.laptop') : ''}`,
        ],
      },
      { key: 'maquina.fact.os', lines: [`${hw.os.name} ${hw.os.version} (${hw.os.arch})`] },
      { key: 'maquina.fact.cpu', lines: cpuLines },
      {
        key: 'maquina.fact.ram',
        lines: [`${formatGb(hw.memory.ram_total_mb)} · ${t('maquina.free', { v: formatGb(hw.memory.ram_free_mb) })}`],
      },
      { key: 'maquina.fact.gpu', lines: gpuLines },
      {
        key: 'maquina.fact.disk',
        lines: [
          `${t('maquina.free', { v: formatGb(hw.disk.free_mb) })} / ${formatGb(hw.disk.total_mb)} · ${hw.disk.drive ?? ''} · ${hw.disk.kind}`,
        ],
      },
      { key: 'maquina.fact.power', lines: [power, `${t('maquina.plan')}: ${hw.system.power_plan ?? '-'}`] },
    ];
  });

  protected readonly accel = computed<AccelRow[]>(() => {
    const acc = this.snap()?.hardware?.acceleration ?? {};
    return ACCEL_IDS.map((id) => {
      const a = acc[id];
      let detail = a?.detail ?? '';
      if (id === 'vulkan' && a?.available) {
        detail = `API ${a.api_version ?? '?'} · ${(a.devices ?? []).map((d) => d.name).join(', ')}`;
      } else if (id === 'openvino') {
        detail = a?.available ? `v${a.version}` : a?.candidate ? this.i18n.t('maquina.accel.candidate') : '';
      }
      return { id, available: !!a?.available, detail };
    });
  });

  protected readonly bench = computed<BenchRow[]>(() =>
    [...(this.machine.benchmark()?.results ?? [])]
      .sort((a, b) => benchRank(a.task) - benchRank(b.task))
      .map((r) => ({
        task: r.task,
        status: r.status,
        result: this.benchResult(r),
        detail: r.detail ?? '',
      })),
  );

  constructor() {
    this.machine.refresh();
    effect(() => {
      for (const job of this.jobs.jobs()) {
        if (!WATCHED_KINDS.includes(job.kind)) continue;
        if (isActive(job)) {
          this.seenActive.add(job.id);
        } else if (this.seenActive.has(job.id) && !this.handled.has(job.id)) {
          this.handled.add(job.id);
          this.machine.refresh();
          const ok = job.status === 'done';
          this.toast.show(
            this.i18n.t(ok ? 'maquina.job.done' : 'maquina.job.failed', { title: job.title }),
            ok ? 'success' : 'error',
          );
        }
      }
    });
  }

  protected redo(): void {
    this.api.startDiagnostic(false).subscribe({
      next: (job) => {
        this.jobs.merge(job);
        this.toast.show(this.i18n.t('maquina.diag.started'), 'info');
      },
      error: () => this.toast.show(this.i18n.t('common.error.request'), 'error'),
    });
  }

  protected runBenchmark(): void {
    this.api.runBenchmark().subscribe({
      next: (job) => {
        this.jobs.merge(job);
        this.toast.show(this.i18n.t('maquina.bench.started'), 'info');
      },
      error: () => this.toast.show(this.i18n.t('common.error.request'), 'error'),
    });
  }

  protected tone(cap: Capability): BadgeTone {
    return cap.state === 'available' ? 'ok' : cap.state === 'slow' ? 'warning' : 'error';
  }

  protected benchTone(status: BenchRow['status']): BadgeTone {
    return status === 'ok' ? 'ok' : status === 'error' ? 'error' : 'neutral';
  }

  private benchResult(r: BenchmarkResult): string {
    if (r.status !== 'ok' || r.task !== 'llm_ollama') return '';
    const num = (v: unknown): string => (typeof v === 'number' ? v.toLocaleString('pt-BR', { maximumFractionDigits: 1 }) : '-');
    const unit = this.i18n.t('maquina.bench.unit');
    const cpuOrGpu = r.metrics['processor'] === 'gpu' ? 'GPU' : 'CPU';
    return `${num(r.metrics['gen_tok_s'])} ${unit} · prefill ${num(r.metrics['prefill_tok_s'])} ${unit} · ${r.model ?? ''} · ${cpuOrGpu}`;
  }
}
