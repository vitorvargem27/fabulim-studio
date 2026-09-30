/** Formatação pt-BR: memória, duração e datas. Funções puras (fáceis de testar). */

export function formatGb(mb: number | null | undefined, digits = 1): string {
  if (mb === null || mb === undefined) return '-';
  return `${(mb / 1024).toLocaleString('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits })} GB`;
}

export function formatMb(mb: number | null | undefined): string {
  return mb === null || mb === undefined ? '-' : `${mb.toLocaleString('pt-BR')} MB`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '-';
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} GB`;
  return `${Math.round(bytes / 1024 ** 2).toLocaleString('pt-BR')} MB`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '';
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ${String(s % 60).padStart(2, '0')} s`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')} min`;
}

export function formatPercent(fraction: number): string {
  return `${Math.round(Math.max(0, Math.min(1, fraction)) * 100)}%`;
}

export function formatDateTime(iso: string | null | undefined, locale = 'pt-BR'): string {
  if (!iso) return '-';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(locale, { dateStyle: 'short', timeStyle: 'medium' });
}

export function formatTime(iso: string | null | undefined, locale = 'pt-BR'): string {
  if (!iso) return '';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleTimeString(locale, { timeStyle: 'medium' });
}

/** Rola suavemente até o elemento com este id (não faz nada se ele não existe ou se o navegador não sabe rolar). */
export function scrollToId(id: string): void {
  document.getElementById(id)?.scrollIntoView?.({ behavior: 'smooth' });
}
