import { formatBytes, formatDateTime, formatDuration, formatGb, formatMb, formatPercent, formatTime } from './format';

describe('format', () => {
  it('formata tamanhos de arquivo em MB e GB', () => {
    expect(formatBytes(null)).toBe('-');
    expect(formatBytes(undefined)).toBe('-');
    expect(formatBytes(0)).toBe('0 MB');
    expect(formatBytes(150 * 1024 ** 2)).toBe('150 MB');
    expect(formatBytes(Math.round(2.5 * 1024 ** 3))).toBe('2,5 GB');
  });

  it('formata memória em GB com vírgula decimal', () => {
    expect(formatGb(32475)).toBe('31,7 GB');
    expect(formatGb(61 * 1024 + 205)).toBe('61,2 GB');
    expect(formatGb(2048, 0)).toBe('2 GB');
    expect(formatGb(null)).toBe('-');
    expect(formatGb(undefined)).toBe('-');
  });

  it('formata MB com separador de milhar', () => {
    expect(formatMb(16237)).toMatch(/^16\.237 MB$/);
    expect(formatMb(128)).toBe('128 MB');
    expect(formatMb(null)).toBe('-');
  });

  it('formata duração em segundos, minutos e horas', () => {
    expect(formatDuration(5)).toBe('5 s');
    expect(formatDuration(59.6)).toBe('1 min 00 s');
    expect(formatDuration(150)).toBe('2 min 30 s');
    expect(formatDuration(3720)).toBe('1 h 02 min');
    expect(formatDuration(-4)).toBe('0 s');
    expect(formatDuration(null)).toBe('');
    expect(formatDuration(Number.NaN)).toBe('');
  });

  it('limita a porcentagem entre 0 e 100', () => {
    expect(formatPercent(0.456)).toBe('46%');
    expect(formatPercent(1.7)).toBe('100%');
    expect(formatPercent(-1)).toBe('0%');
  });

  it('formata datas e devolve o texto original quando é inválido', () => {
    expect(formatDateTime('2026-09-29T12:30:00Z')).toMatch(/29\/09\/2026/);
    expect(formatDateTime('lixo')).toBe('lixo');
    expect(formatDateTime(null)).toBe('-');
    expect(formatTime('2026-09-29T12:30:00Z')).toMatch(/\d{2}:\d{2}:\d{2}/);
    expect(formatTime('')).toBe('');
    expect(formatTime('lixo')).toBe('lixo');
  });
});
