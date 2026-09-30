import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

import { TPipe } from '../core/i18n/t.pipe';
import { PageHeaderComponent } from '../ui/page-header';

@Component({
  selector: 'fab-not-found-page',
  imports: [RouterLink, TPipe, PageHeaderComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <fab-page-header [title]="'notfound.title' | t" [subtitle]="'notfound.text' | t">
      <a class="btn btn-primary" routerLink="/criar">{{ 'notfound.home' | t }}</a>
    </fab-page-header>
  `,
})
export class NotFoundPage {}
