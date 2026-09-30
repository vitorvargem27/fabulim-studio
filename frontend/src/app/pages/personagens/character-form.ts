import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

import { TPipe } from '../../core/i18n/t.pipe';
import { CharacterForm, Style } from '../../core/models';
import { FieldComponent } from '../../ui/field';
import { SegmentedComponent, SegmentedOption } from '../../ui/segmented';

export const EMPTY_CHARACTER: CharacterForm = {
  name: '',
  style: '2D',
  species: '',
  apparent_age: '',
  appearance: '',
  clothing: '',
  palette: '',
  personality: '',
  voice: '',
  expressions: '',
  notes: '',
};

const STYLES: SegmentedOption[] = [
  { value: '2D', label: '2D' },
  { value: '3D', label: '3D' },
];

/** A ficha do personagem (briefing 7.2): os mesmos campos do prompt de personagem, para criar e para editar. */
@Component({
  selector: 'fab-character-form',
  imports: [FieldComponent, SegmentedComponent, TPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="grid gap-5">
      <div class="field-row">
        <fab-field [label]="'personagens.f.name' | t" [required]="true" [maxlength]="80" [value]="form().name" (valueChange)="patch('name', $event)" />
        <div class="field">
          <span class="field-label">{{ 'personagens.f.style' | t }}</span>
          @if (styleLocked()) {
            <p class="min-h-11 py-2 font-bold">{{ form().style }} <span class="font-normal text-ink-soft">· {{ 'personagens.f.style.locked' | t }}</span></p>
          } @else {
            <fab-segmented [options]="styles" [label]="'personagens.f.style' | t" [value]="form().style" (valueChange)="patch('style', $event)" />
          }
        </div>
      </div>
      <div class="field-row">
        <fab-field [label]="'personagens.f.species' | t" [hint]="'personagens.f.species.hint' | t" [maxlength]="200" [value]="form().species" (valueChange)="patch('species', $event)" />
        <fab-field [label]="'personagens.f.age' | t" [maxlength]="120" [value]="form().apparent_age" (valueChange)="patch('apparent_age', $event)" />
      </div>
      <fab-field
        [label]="'personagens.f.appearance' | t"
        [hint]="'personagens.f.appearance.hint' | t"
        [multiline]="true"
        [rows]="3"
        [required]="true"
        [maxlength]="1500"
        [value]="form().appearance"
        (valueChange)="patch('appearance', $event)"
      />
      <div class="field-row">
        <fab-field [label]="'personagens.f.clothing' | t" [multiline]="true" [rows]="2" [maxlength]="800" [value]="form().clothing" (valueChange)="patch('clothing', $event)" />
        <fab-field [label]="'personagens.f.palette' | t" [multiline]="true" [rows]="2" [maxlength]="400" [value]="form().palette" (valueChange)="patch('palette', $event)" />
      </div>
      <div class="field-row">
        <fab-field [label]="'personagens.f.personality' | t" [multiline]="true" [rows]="2" [maxlength]="800" [value]="form().personality" (valueChange)="patch('personality', $event)" />
        <fab-field [label]="'personagens.f.voice' | t" [hint]="'personagens.f.voice.hint' | t" [multiline]="true" [rows]="2" [maxlength]="400" [value]="form().voice" (valueChange)="patch('voice', $event)" />
      </div>
      <div class="field-row">
        <fab-field [label]="'personagens.f.expressions' | t" [maxlength]="400" [value]="form().expressions" (valueChange)="patch('expressions', $event)" />
        <fab-field [label]="'personagens.f.notes' | t" [maxlength]="1500" [value]="form().notes" (valueChange)="patch('notes', $event)" />
      </div>
    </div>
  `,
})
export class CharacterFormComponent {
  readonly form = model.required<CharacterForm>();
  /** Na edição o estilo não muda: para trocar de 2D para 3D existe a «versão» (as imagens seguem o estilo). */
  readonly styleLocked = input(false);

  protected readonly styles = STYLES;

  protected patch(key: keyof CharacterForm, value: string): void {
    this.form.update((f) => ({ ...f, [key]: key === 'style' ? (value as Style) : value }));
  }
}
