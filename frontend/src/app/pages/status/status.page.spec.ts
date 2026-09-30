import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { StatusPage } from './status.page';

@Component({ template: '<p>conteúdo da aba</p>' })
class AbaPage {}

describe('StatusPage (casca com abas)', () => {
  beforeEach(() => localStorage.clear()); // o idioma guardado por outro teste não pode vazar para este

  const abrir = async (url: string): Promise<HTMLElement> => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          {
            path: 'status',
            component: StatusPage,
            children: [
              { path: 'servicos', component: AbaPage },
              { path: 'maquina', component: AbaPage },
              { path: 'logs', component: AbaPage },
            ],
          },
        ]),
      ],
    });
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl(url);
    return harness.routeNativeElement as HTMLElement;
  };

  it('mostra as três abas por rota, dentro de uma navegação com nome', async () => {
    const el = await abrir('/status/servicos');
    expect(el.querySelector('nav.tabs')?.getAttribute('aria-label')).toBe('Seções do Status');
    expect([...el.querySelectorAll('nav.tabs a')].map((a) => a.textContent?.trim())).toEqual(['Serviços', 'Sua máquina', 'Logs']);
    expect(el.querySelector('h1')?.textContent).toContain('Status');
  });

  it('marca só a aba da rota atual com aria-current e mostra o conteúdo dela', async () => {
    const el = await abrir('/status/maquina');
    const atuais = [...el.querySelectorAll('nav.tabs a[aria-current="page"]')].map((a) => a.textContent?.trim());
    expect(atuais).toEqual(['Sua máquina']);
    expect(el.querySelector('.tab-body')?.textContent).toContain('conteúdo da aba');
  });
});
