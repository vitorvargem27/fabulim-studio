import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, TitleStrategy, provideRouter } from '@angular/router';

import { I18nService } from './i18n/i18n.service';
import { FabTitleStrategy } from './title.strategy';

@Component({ template: '' })
class VaziaPage {}

describe('FabTitleStrategy', () => {
  let router: Router;
  let i18n: I18nService;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'criar', title: 'nav.criar', component: VaziaPage },
          { path: 'sem-titulo', component: VaziaPage },
        ]),
        { provide: TitleStrategy, useClass: FabTitleStrategy },
      ],
    });
    router = TestBed.inject(Router);
    i18n = TestBed.inject(I18nService);
    document.title = '';
  });

  it('monta "Página · Fabulim Studio" traduzindo a chave da rota', async () => {
    await router.navigateByUrl('/criar');
    expect(document.title).toBe('Criar vídeo · Fabulim Studio');
  });

  it('usa só o nome do produto quando a rota não tem título', async () => {
    await router.navigateByUrl('/sem-titulo');
    expect(document.title).toBe('Fabulim Studio');
  });

  it('acompanha a troca de idioma sem precisar navegar de novo', async () => {
    await router.navigateByUrl('/criar');
    i18n.set('en');
    TestBed.tick();
    expect(document.title).toBe('Create video · Fabulim Studio');
    i18n.set('pt-BR');
    TestBed.tick();
    expect(document.title).toBe('Criar vídeo · Fabulim Studio');
  });
});
