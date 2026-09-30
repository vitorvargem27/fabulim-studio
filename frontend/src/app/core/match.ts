import { Character, Style } from './models';

/** Minúsculas, sem acento e sem espaços duplicados: o mesmo critério do backend para comparar nomes. */
export function normalize(text: string): string {
  return text
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

export interface NameMatches {
  found: Character[];
  missing: string[];
}

/**
 * Casa nomes citados num prompt com os personagens da biblioteca (sem diferenciar caixa nem acento). Se o mesmo nome
 * existe em 2D e em 3D, prefere o do `style` pedido. Os que não existem voltam em `missing`, na ordem em que apareceram.
 */
export function matchCharacters(names: string[], library: Character[], style?: Style): NameMatches {
  const found: Character[] = [];
  const missing: string[] = [];
  const seen = new Set<string>();
  for (const name of names) {
    const key = normalize(name);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    const same = library.filter((c) => normalize(c.name) === key);
    const pick = same.find((c) => c.style === style) ?? same[0];
    if (pick) {
      if (!found.some((f) => f.id === pick.id)) found.push(pick);
    } else missing.push(name.trim());
  }
  return { found, missing };
}

const SHORT_LIMIT_S = 60;
const LONG_LIMIT_S = 300;

/** Limite de duração de cada formato: Short até 60 s e vídeo longo até 5 min. */
export function durationLimit(format: 'short' | 'longo'): number {
  return format === 'short' ? SHORT_LIMIT_S : LONG_LIMIT_S;
}

/** «60 s», «3 min», «1:30» ou só «45»: a duração alvo em segundos, dentro do limite do formato (mesma regra do backend). */
export function parseDurationSeconds(text: string, format: 'short' | 'longo'): number {
  const limit = durationLimit(format);
  const fallback = Math.min(format === 'short' ? 45 : 120, limit);
  const t = normalize(text);
  let seconds: number | null = null;
  const clock = /(\d+):(\d{2})/.exec(t);
  const minutes = /(\d+(?:[.,]\d+)?)\s*(?:min|minutos?|m\b)/.exec(t);
  const plain = /(\d+(?:[.,]\d+)?)/.exec(t);
  if (clock) seconds = Number(clock[1]) * 60 + Number(clock[2]);
  else if (minutes) seconds = parseFloat(minutes[1].replace(',', '.')) * 60;
  else if (plain) seconds = parseFloat(plain[1].replace(',', '.'));
  if (seconds === null || !(seconds > 0)) return fallback;
  return Math.round(Math.min(Math.max(seconds, 15), limit));
}

/** Semente informada pelo usuário: número inteiro de 0 até 2147483646, ou `null` (o servidor sorteia). */
export function parseSeed(text: string): number | null {
  const trimmed = text.trim();
  if (!/^\d{1,10}$/.test(trimmed)) return null;
  const value = Number(trimmed);
  return value < 2 ** 31 - 1 ? value : null;
}
