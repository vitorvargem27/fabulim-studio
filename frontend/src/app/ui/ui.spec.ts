import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { ToastService } from '../core/toast.service';
import { BadgeComponent } from './badge';
import { EmptyStateComponent } from './empty-state';
import { ProgressComponent } from './progress';
import { SegmentedComponent } from './segmented';
import { ToastHostComponent } from './toast-host';

@Component({
  imports: [BadgeComponent, ProgressComponent, SegmentedComponent, EmptyStateComponent],
  template: `
    <fab-badge tone="warning">Atenção</fab-badge>
    <fab-badge tone="ok" [icon]="false">Ok</fab-badge>
    <fab-progress [value]="value()" label="Enviando" [paused]="paused()" />
    <fab-segmented
      [options]="[
        { value: 'a', label: 'A' },
        { value: 'b', label: 'B' },
        { value: 'c', label: 'C' },
      ]"
      label="Escolha"
      [value]="choice()"
      (valueChange)="choice.set($event)"
    />
    <fab-empty title="Vazio" text="Nada por aqui"><button type="button" class="acao">Fazer</button></fab-empty>
  `,
})
class Host {
  readonly value = signal(0.42);
  readonly paused = signal(false);
  readonly choice = signal('a');
}

describe('componentes de interface', () => {
  const montar = async () => {
    const fixture = TestBed.createComponent(Host);
    await fixture.whenStable();
    return fixture;
  };

  it('Badge usa o tom certo e sempre tem ícone, salvo quando desligado (nunca só cor)', async () => {
    const el: HTMLElement = (await montar()).nativeElement;
    const [warn, ok] = [...el.querySelectorAll('fab-badge')];
    expect(warn.classList).toContain('tone-warning');
    expect(warn.querySelector('svg')).not.toBeNull();
    expect(warn.textContent).toContain('Atenção');
    expect(ok.classList).toContain('tone-ok');
    expect(ok.querySelector('svg')).toBeNull();
  });

  it('Progress expõe aria-valuenow e limita o valor entre 0 e 100', async () => {
    const fixture = await montar();
    const barra = (fixture.nativeElement as HTMLElement).querySelector('[role="progressbar"]')!;
    expect(barra.getAttribute('aria-valuenow')).toBe('42');
    expect(barra.getAttribute('aria-label')).toBe('Enviando');
    fixture.componentInstance.value.set(7);
    await fixture.whenStable();
    expect(barra.getAttribute('aria-valuenow')).toBe('100');
    fixture.componentInstance.value.set(-3);
    await fixture.whenStable();
    expect(barra.getAttribute('aria-valuenow')).toBe('0');
  });

  it('Progress pausado muda de cor', async () => {
    const fixture = await montar();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('.fill')?.classList).not.toContain('paused');
    fixture.componentInstance.paused.set(true);
    await fixture.whenStable();
    expect(el.querySelector('.fill')?.classList).toContain('paused');
  });

  it('Segmentado funciona como grupo de rádio com setas, Home e End', async () => {
    const fixture = await montar();
    const el: HTMLElement = fixture.nativeElement;
    const grupo = el.querySelector('[role="radiogroup"]')!;
    const marcado = (): string => el.querySelector('[role="radio"][aria-checked="true"]')!.textContent!.trim();
    expect(grupo.getAttribute('aria-label')).toBe('Escolha');
    expect(marcado()).toBe('A');
    const tecla = async (key: string): Promise<void> => {
      grupo.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
      await fixture.whenStable();
    };
    await tecla('ArrowRight');
    expect(marcado()).toBe('B');
    await tecla('ArrowDown');
    expect(marcado()).toBe('C');
    await tecla('ArrowRight'); // dá a volta
    expect(marcado()).toBe('A');
    await tecla('ArrowLeft');
    expect(marcado()).toBe('C');
    await tecla('Home');
    expect(marcado()).toBe('A');
    await tecla('End');
    expect(marcado()).toBe('C');
    await tecla('x'); // outras teclas não mudam nada
    expect(marcado()).toBe('C');
  });

  it('Segmentado: só o item marcado entra na ordem de tabulação e o clique seleciona', async () => {
    const fixture = await montar();
    const botoes = [...(fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('[role="radio"]')];
    expect(botoes.map((b) => b.getAttribute('tabindex'))).toEqual(['0', '-1', '-1']);
    botoes[1].click();
    await fixture.whenStable();
    expect(fixture.componentInstance.choice()).toBe('b');
  });

  it('EmptyState mostra título, texto e as ações projetadas', async () => {
    const el: HTMLElement = (await montar()).nativeElement;
    const vazio = el.querySelector('fab-empty')!;
    expect(vazio.querySelector('h2')?.textContent).toBe('Vazio');
    expect(vazio.textContent).toContain('Nada por aqui');
    expect(vazio.querySelector('.acao')?.textContent).toBe('Fazer');
  });
});

describe('avisos (toast)', () => {
  it('aparece, fica na região aria-live e some sozinho', async () => {
    const fixture = TestBed.createComponent(ToastHostComponent);
    const toasts = TestBed.inject(ToastService);
    toasts.show('Cena aprovada', 'success', 60);
    await fixture.whenStable();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('[aria-live="polite"]')).not.toBeNull();
    expect(el.textContent).toContain('Cena aprovada');
    await new Promise((resolve) => setTimeout(resolve, 150));
    await fixture.whenStable();
    expect(el.textContent).not.toContain('Cena aprovada');
  });

  it('mantém no máximo quatro avisos e permite fechar um', () => {
    const toasts = TestBed.inject(ToastService);
    for (let i = 0; i < 6; i++) toasts.show(`aviso ${i}`, 'info', 60_000);
    expect(toasts.toasts()).toHaveLength(4);
    const primeiro = toasts.toasts()[0].id;
    toasts.dismiss(primeiro);
    expect(toasts.toasts().some((t) => t.id === primeiro)).toBe(false);
  });
});
