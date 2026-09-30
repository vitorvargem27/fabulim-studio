import { TestBed } from '@angular/core/testing';

import { ThemeService } from './theme.service';

describe('ThemeService', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('começa seguindo o sistema quando não há preferência guardada', () => {
    const theme = TestBed.inject(ThemeService);
    expect(theme.preference()).toBe('system');
    expect(['light', 'dark']).toContain(theme.effective());
  });

  it('aplica o tema escolhido no <html> e guarda a preferência', () => {
    const theme = TestBed.inject(ThemeService);
    theme.set('dark');
    TestBed.tick();
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(localStorage.getItem('fabulim.theme')).toBe('dark');
    theme.set('light');
    TestBed.tick();
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('alterna entre claro e escuro', () => {
    const theme = TestBed.inject(ThemeService);
    theme.set('light');
    theme.toggle();
    expect(theme.preference()).toBe('dark');
    theme.toggle();
    expect(theme.preference()).toBe('light');
  });

  it('lê a preferência guardada ao iniciar', () => {
    localStorage.setItem('fabulim.theme', 'dark');
    expect(TestBed.inject(ThemeService).preference()).toBe('dark');
  });

  it('ignora valor guardado inválido', () => {
    localStorage.setItem('fabulim.theme', 'roxo');
    expect(TestBed.inject(ThemeService).preference()).toBe('system');
  });

  it('funciona mesmo com o armazenamento bloqueado (janela privada)', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('bloqueado');
    });
    const theme = TestBed.inject(ThemeService);
    expect(() => theme.set('dark')).not.toThrow();
    expect(theme.preference()).toBe('dark');
    spy.mockRestore();
  });
});
