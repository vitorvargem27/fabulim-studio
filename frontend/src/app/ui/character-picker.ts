import { ChangeDetectionStrategy, Component, computed, input, model } from '@angular/core';
import { RouterLink } from '@angular/router';

import { TPipe } from '../core/i18n/t.pipe';
import { Character } from '../core/models';

/**
 * Escolha de personagens da biblioteca (botões que ligam e desligam). Só entram os que já têm uma imagem escolhida,
 * porque é dela que o modelo parte para manter a aparência. Respeita o limite de `max` personagens.
 */
@Component({
  selector: 'fab-character-picker',
  imports: [RouterLink, TPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <fieldset class="m-0 min-w-0 border-0 p-0">
      <legend class="field-label mb-2 p-0">{{ label() }}</legend>
      @if (choices().length) {
        <div class="flex flex-wrap gap-2">
          @for (c of choices(); track c.id) {
            <button
              type="button"
              class="inline-flex min-h-11 items-center gap-2 border-2 border-ink bg-panel py-1 pl-1 pr-3 text-left font-ui text-small font-bold aria-pressed:bg-ink aria-pressed:text-paper disabled:cursor-not-allowed disabled:opacity-50"
              [attr.aria-pressed]="isOn(c.id)"
              [disabled]="!isOn(c.id) && atLimit()"
              (click)="toggle(c.id)"
            >
              @if (c.main_image_url) {
                <img [src]="c.main_image_url" alt="" class="size-9 bg-wash object-contain" />
              }
              <span>{{ c.name }} <span class="font-normal opacity-80">· {{ c.style }}</span></span>
            </button>
          }
        </div>
        <p class="field-hint mt-2">{{ hint() || ('picker.hint' | t: { max: max() }) }}</p>
      } @else {
        <p class="text-small text-ink-soft">
          {{ 'picker.empty' | t }} <a routerLink="/personagens">{{ 'picker.empty.link' | t }}</a>
        </p>
      }
    </fieldset>
  `,
  host: { class: 'block' },
})
export class CharacterPickerComponent {
  readonly characters = input.required<Character[]>();
  readonly selected = model<string[]>([]);
  readonly label = input.required<string>();
  readonly max = input(3);
  readonly hint = input('');
  readonly requireImage = input(true);
  /** Para vídeos: só personagens com o PNG transparente pronto (é o que a animação usa). */
  readonly requireCutout = input(false);

  protected readonly choices = computed(() =>
    this.characters().filter(
      (c) => (!this.requireImage() || c.main_image_id !== null) && (!this.requireCutout() || c.has_cutout),
    ),
  );
  protected readonly atLimit = computed(() => this.selected().length >= this.max());

  protected isOn(id: string): boolean {
    return this.selected().includes(id);
  }

  protected toggle(id: string): void {
    this.selected.update((list) => (list.includes(id) ? list.filter((x) => x !== id) : this.atLimit() ? list : [...list, id]));
  }
}
