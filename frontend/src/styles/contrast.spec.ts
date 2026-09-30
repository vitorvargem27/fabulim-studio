import { readFileSync } from 'node:fs';
import { join } from 'node:path';

// Contraste WCAG 2.x calculado direto do arquivo de tokens: se alguém mudar uma cor, o teste avisa se deixou de passar em AA.

const TOKENS = readFileSync(join(process.cwd(), 'src', 'styles', 'tokens.css'), 'utf-8');

function bloco(regex: RegExp): Record<string, string> {
  const cores: Record<string, string> = {};
  for (const m of (TOKENS.match(regex)?.[1] ?? '').matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) cores[m[1]] = m[2];
  return cores;
}

/** Cores do tema como o navegador as enxerga: o bloco escuro só sobrescreve o claro (cascata), não o substitui. */
function ler(tema: 'light' | 'dark'): Record<string, string> {
  const claro = bloco(/:root\s*\{([\s\S]*?)\n\}/);
  return tema === 'light' ? claro : { ...claro, ...bloco(/:root\[data-theme='dark'\]\s*\{([\s\S]*?)\n\}/) };
}

function luminancia(hex: string): number {
  const canais = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = canais.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contraste(a: string, b: string): number {
  const [claro, escuro] = [luminancia(a), luminancia(b)].sort((x, y) => y - x);
  return (claro + 0.05) / (escuro + 0.05);
}

describe('contraste WCAG AA dos tokens', () => {
  it('calcula o contraste como a especificação (preto no branco é 21:1)', () => {
    expect(contraste('#000000', '#ffffff')).toBeCloseTo(21, 0);
    expect(contraste('#2b2d6e', '#f6f4ff')).toBeGreaterThan(11); // Anil sobre Nuvem: 11,3:1 no briefing
  });

  for (const tema of ['light', 'dark'] as const) {
    describe(`tema ${tema}`, () => {
      const c = ler(tema);

      const TEXTO: [string, string][] = [
        // texto e tinta
        ['ink', 'paper'],
        ['ink', 'panel'],
        ['ink', 'wash'],
        ['ink-soft', 'paper'],
        ['ink-soft', 'panel'],
        ['ink-soft', 'wash'],
        // marcador ativo (fundo de tinta, texto de papel) e ação principal
        ['paper', 'ink'],
        ['on-accent', 'accent'],
        ['on-accent', 'accent-hover'],
        // texto de estado
        ['ok-ink', 'paper'],
        ['ok-ink', 'panel'],
        ['ok-ink', 'wash'],
        ['warn-ink', 'paper'],
        ['warn-ink', 'panel'],
        ['warn-ink', 'wash'],
        ['bad-ink', 'paper'],
        ['bad-ink', 'panel'],
        ['bad-ink', 'wash'],
        // barra lateral
        ['on-rail', 'rail'],
        ['on-rail-soft', 'rail'],
        ['rail-accent', 'rail'],
        ['on-accent', 'rail-accent'],
        ['brand-coral', 'rail'],
      ];
      for (const [fg, bg] of TEXTO) {
        it(`texto ${fg} sobre ${bg} tem pelo menos 4,5:1`, () => {
          expect(c[fg], `token ${fg} não encontrado`).toBeDefined();
          expect(c[bg], `token ${bg} não encontrado`).toBeDefined();
          expect(contraste(c[fg], c[bg])).toBeGreaterThanOrEqual(4.5);
        });
      }

      const NAO_TEXTO: [string, string][] = [
        ['focus', 'paper'],
        ['focus', 'panel'],
        ['focus', 'wash'],
        ['rail-accent', 'rail'], // anel de foco dentro da barra lateral (o foco padrão some sobre a tinta)
        ['on-accent', 'rail-accent'], // anel de foco sobre o item ativo da barra lateral
        ['ink', 'paper'], // contorno de controles e filetes fortes
        ['ink', 'panel'],
        ['ink-soft', 'paper'], // marcador vazio (círculo tracejado)
      ];
      for (const [fg, bg] of NAO_TEXTO) {
        it(`elemento ${fg} sobre ${bg} tem pelo menos 3:1 (foco, contornos e formas)`, () => {
          expect(c[fg], `token ${fg} não encontrado`).toBeDefined();
          expect(contraste(c[fg], c[bg])).toBeGreaterThanOrEqual(3);
        });
      }
    });
  }

  it('o foco tem regra própria dentro da barra lateral (o foco comum, de tinta, não aparece sobre a tinta)', () => {
    const base = readFileSync(join(process.cwd(), 'src', 'styles', 'base.css'), 'utf-8');
    const componentes = readFileSync(join(process.cwd(), 'src', 'styles', 'components.css'), 'utf-8');
    expect(base).toMatch(/:focus-visible\s*\{[^}]*var\(--focus\)/);
    expect(componentes).toMatch(/\.sidebar :focus-visible\s*\{[^}]*var\(--rail-accent\)/);
    expect(componentes).toMatch(/\.sidebar a\.active:focus-visible\s*\{[^}]*var\(--on-accent\)/);
    // no tema claro o foco comum e a barra lateral têm a mesma cor: sem a regra própria, o anel ficaria invisível
    const c = ler('light');
    expect(c['focus']).toBe(c['rail']);
  });

  it('a etapa atual do projeto mantém o texto legível com o mouse em cima (no tema escuro o Lavanda escuro caía sobre o mesmo azul)', () => {
    const componentes = readFileSync(join(process.cwd(), 'src', 'styles', 'components.css'), 'utf-8');
    // o «hover» comum não pode valer para a etapa atual: ele trocaria o fundo por --wash e deixaria o texto (--on-accent) sem contraste
    expect(componentes).toMatch(/\.stage-bar > button:hover:not\(:disabled\):not\(\[aria-current='step'\]\)\s*\{[^}]*var\(--wash\)/);
    expect(componentes).toMatch(/\.stage-bar > button\[aria-current='step'\]:hover\s*\{[^}]*var\(--accent-hover\)/);
    for (const tema of ['light', 'dark'] as const) {
      const c = ler(tema);
      expect(contraste(c['on-accent'], c['accent']), `${tema}: --on-accent sobre --accent`).toBeGreaterThanOrEqual(4.5);
      expect(contraste(c['on-accent'], c['accent-hover']), `${tema}: --on-accent sobre --accent-hover`).toBeGreaterThanOrEqual(4.5);
    }
    // o defeito que existia: no tema escuro o fundo do hover (--wash) e o texto da etapa atual quase não se distinguem
    expect(contraste(ler('dark')['on-accent'], ler('dark')['wash'])).toBeLessThan(3);
  });

  it('Girassol e Menta não são usados como cor de texto no tema claro', () => {
    const c = ler('light');
    expect(contraste(c['brand-girassol'], c['paper'])).toBeLessThan(4.5);
    expect(contraste(c['brand-menta'], c['paper'])).toBeLessThan(4.5);
    for (const token of ['ink', 'ink-soft', 'ok-ink', 'warn-ink', 'bad-ink']) {
      expect([c['brand-girassol'], c['brand-menta']]).not.toContain(c[token]);
    }
  });
});
