import { Injectable, OnDestroy, computed, inject, signal } from '@angular/core';
import { Observable, Subject } from 'rxjs';

import { ApiService } from './api.service';
import { Job, JobStatus, Media } from './models';

export const ACTIVE_STATUSES: readonly JobStatus[] = ['running', 'paused', 'queued'];

export function isActive(job: Job): boolean {
  return ACTIVE_STATUSES.includes(job.status);
}

/** Mesma ordem do backend: executando primeiro, depois a fila (prioridade, posição); finalizados do mais novo ao mais antigo. */
export function sortJobs(jobs: Job[]): Job[] {
  const rank = (j: Job): number => (j.status === 'running' ? 0 : isActive(j) ? 1 : 2);
  return [...jobs].sort((a, b) => {
    const r = rank(a) - rank(b);
    if (r !== 0) return r;
    if (rank(a) === 1) return b.priority - a.priority || a.position - b.position;
    return (b.finished_at ?? '').localeCompare(a.finished_at ?? '');
  });
}

/** Insere ou substitui um job pelo id, sem duplicar, e mantém a ordem. */
export function mergeJob(jobs: Job[], job: Job): Job[] {
  const i = jobs.findIndex((j) => j.id === job.id);
  const next = i === -1 ? [...jobs, job] : jobs.map((j, k) => (k === i ? job : j));
  return sortJobs(next);
}

/** Aplica localmente a nova ordem da fila (posição 1..n e prioridade 0), igual ao que o backend grava. */
export function applyReorder(jobs: Job[], ids: string[]): Job[] {
  const order = new Map(ids.map((id, i) => [id, i + 1]));
  return sortJobs(jobs.map((j) => (order.has(j.id) ? { ...j, position: order.get(j.id) ?? j.position, priority: 0 } : j)));
}

/** Job que o worker está segurando: executando ou pausado por pedido do usuário. */
export function heldByWorker(job: Job): boolean {
  return job.status === 'running' || (job.status === 'paused' && job.pause_requested);
}

export type MediaEvent = { type: 'created'; media: Media } | { type: 'deleted'; id: string };

/** Fila de jobs ao vivo: um retrato inicial e cada mudança chegam por SSE (`/api/events`). */
@Injectable({ providedIn: 'root' })
export class JobsService implements OnDestroy {
  private readonly api = inject(ApiService);
  private source: EventSource | null = null;

  private readonly finishedSubject = new Subject<Job>();
  private readonly mediaSubject = new Subject<MediaEvent>();

  readonly jobs = signal<Job[]>([]);
  readonly connected = signal(false);
  readonly loaded = signal(false);

  readonly active = computed(() => this.jobs().filter(isActive));
  readonly finished = computed(() => this.jobs().filter((j) => !isActive(j)));
  readonly activeCount = computed(() => this.active().length);
  readonly running = computed(() => this.jobs().find((j) => j.status === 'running') ?? null);

  /** Cada tarefa que termina (concluída, com erro ou cancelada) é anunciada uma vez: as páginas recarregam o que mudou. */
  readonly finished$: Observable<Job> = this.finishedSubject.asObservable();
  /** Mídias criadas ou apagadas na biblioteca (chegam pelo mesmo fluxo ao vivo). */
  readonly media$: Observable<MediaEvent> = this.mediaSubject.asObservable();

  connect(): void {
    if (this.source || typeof EventSource === 'undefined') return;
    const source = new EventSource('/api/events');
    this.source = source;
    source.onopen = () => this.connected.set(true);
    source.onerror = () => this.connected.set(false); // o EventSource reconecta sozinho
    source.addEventListener('snapshot', (e) => {
      const data = JSON.parse((e as MessageEvent<string>).data) as { jobs: Job[] };
      this.jobs.set(sortJobs(data.jobs));
      this.loaded.set(true);
    });
    source.addEventListener('job.updated', (e) => {
      this.merge(JSON.parse((e as MessageEvent<string>).data) as Job);
    });
    source.addEventListener('media.created', (e) => {
      this.mediaSubject.next({ type: 'created', media: JSON.parse((e as MessageEvent<string>).data) as Media });
    });
    source.addEventListener('media.deleted', (e) => {
      this.mediaSubject.next({ type: 'deleted', id: (JSON.parse((e as MessageEvent<string>).data) as { id: string }).id });
    });
  }

  /** A tarefa com este id (ou `undefined` se a fila ainda não a conhece). */
  byId(id: string | null | undefined): Job | undefined {
    return id ? this.jobs().find((j) => j.id === id) : undefined;
  }

  disconnect(): void {
    this.source?.close();
    this.source = null;
    this.connected.set(false);
  }

  ngOnDestroy(): void {
    this.disconnect();
  }

  merge(job: Job): void {
    const before = this.jobs().find((j) => j.id === job.id);
    this.jobs.update((list) => mergeJob(list, job));
    if (!isActive(job) && (before === undefined || isActive(before))) this.finishedSubject.next(job);
  }

  create(kind: string, params: Record<string, unknown> = {}, title?: string): void {
    this.api.createJob(kind, params, title).subscribe((job) => this.merge(job));
  }

  act(job: Job, action: 'pause' | 'resume' | 'cancel'): void {
    this.api.jobAction(job.id, action).subscribe((updated) => this.merge(updated));
  }

  reorder(ids: string[]): void {
    this.jobs.update((list) => applyReorder(list, ids)); // otimista: a tela já mostra a nova ordem
    this.api.reorder(ids).subscribe();
  }

  clearFinished(): void {
    this.api.clearFinished().subscribe(() => this.jobs.update((list) => list.filter(isActive)));
  }
}
