import { HttpEventType } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, output, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService } from '../core/api.service';
import { errorMessage } from '../core/http-error';
import { TPipe } from '../core/i18n/t.pipe';
import { ImportReport } from '../core/models';
import { IconComponent } from './icon';
import { ProgressComponent } from './progress';

/**
 * Importar um pacote .fabulim (projeto ou personagens) de outra máquina. O servidor confere tudo (estrutura, tamanhos, tipos
 * reais dos arquivos) e nunca sobrescreve nada: o que já existe ganha outro nome. O resultado mostra o que entrou e os avisos.
 */
@Component({
  selector: 'fab-package-import',
  imports: [RouterLink, TPipe, IconComponent, ProgressComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="grid max-w-xl gap-4">
      <div class="field">
        <label class="field-label" for="package-file">{{ 'pkg.file' | t }}</label>
        <input id="package-file" type="file" accept=".fabulim,.zip,application/zip" (change)="onFile($event)" [disabled]="busy()" />
        <span class="field-hint">{{ 'pkg.hint' | t }}</span>
      </div>
      @if (busy()) {
        <fab-progress [value]="progress()" [label]="'pkg.sending' | t" />
      }
      <div>
        <button type="button" class="btn btn-primary" (click)="send()" [disabled]="busy() || !file()">
          <fab-icon name="arrow-up" [size]="18" />
          {{ 'pkg.import' | t }}
        </button>
      </div>
      @if (error(); as message) {
        <p class="banner banner-error" role="alert">{{ message }}</p>
      }
      @if (report(); as r) {
        <div class="banner banner-info grid gap-2" role="status">
          @if (r.kind === 'project' && r.project) {
            <p>
              {{ 'pkg.done.project' | t: { title: r.project.title, scenes: r.scenes, media: r.media } }}
              <a [routerLink]="['/projetos', r.project.id]">{{ 'pkg.open.project' | t }}</a>
            </p>
          } @else {
            <p>
              {{ 'pkg.done.characters' | t: { n: r.characters.length, media: r.media } }}
              <a routerLink="/personagens">{{ 'pkg.open.characters' | t }}</a>
            </p>
          }
          @if (r.warnings.length) {
            <ul class="m-0 grid list-none gap-1 p-0 font-normal">
              @for (warning of r.warnings; track warning) {
                <li>{{ warning }}</li>
              }
            </ul>
          }
        </div>
      }
    </div>
  `,
})
export class PackageImportComponent {
  readonly imported = output<ImportReport>();

  private readonly api = inject(ApiService);

  protected readonly file = signal<File | null>(null);
  protected readonly busy = signal(false);
  protected readonly progress = signal(0);
  protected readonly error = signal<string | null>(null);
  protected readonly report = signal<ImportReport | null>(null);

  protected onFile(event: Event): void {
    this.file.set((event.target as HTMLInputElement).files?.[0] ?? null);
    this.error.set(null);
    this.report.set(null);
  }

  protected send(): void {
    const file = this.file();
    if (!file) return;
    this.error.set(null);
    this.report.set(null);
    this.busy.set(true);
    this.progress.set(0);
    this.api.importPackage(file).subscribe({
      next: (event) => {
        if (event.type === HttpEventType.UploadProgress && event.total) this.progress.set(event.loaded / event.total);
        else if (event.type === HttpEventType.Response && event.body) {
          this.busy.set(false);
          this.file.set(null);
          this.report.set(event.body);
          this.imported.emit(event.body);
        }
      },
      error: (e: unknown) => {
        this.busy.set(false);
        this.error.set(errorMessage(e));
      },
    });
  }
}
