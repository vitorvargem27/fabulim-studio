import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export type IconName =
  | 'menu'
  | 'close'
  | 'sun'
  | 'moon'
  | 'check'
  | 'alert'
  | 'info'
  | 'x-circle'
  | 'video'
  | 'users'
  | 'image'
  | 'film'
  | 'folder'
  | 'list'
  | 'cpu'
  | 'activity'
  | 'settings'
  | 'sparkles'
  | 'refresh'
  | 'pause'
  | 'play'
  | 'stop'
  | 'trash'
  | 'grip'
  | 'arrow-up'
  | 'arrow-down'
  | 'chevron-right'
  | 'clock'
  | 'laptop'
  | 'plug'
  | 'globe'
  | 'bolt';

/** Ícones de traço simples (24x24). Decorativos por padrão (aria-hidden); o texto ao lado dá o significado. */
@Component({
  selector: 'fab-icon',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg
      [attr.width]="size()"
      [attr.height]="size()"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      @switch (name()) {
        @case ('menu') {
          <path d="M4 6h16M4 12h16M4 18h16" />
        }
        @case ('close') {
          <path d="M6 6l12 12M18 6L6 18" />
        }
        @case ('sun') {
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        }
        @case ('moon') {
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        }
        @case ('check') {
          <path d="M5 12.5l4.5 4.5L19 7.5" />
        }
        @case ('alert') {
          <path d="M12 3.5l9.5 16.5h-19z" />
          <path d="M12 10v4M12 17.2v.1" />
        }
        @case ('info') {
          <circle cx="12" cy="12" r="9" />
          <path d="M12 11v5M12 8v.1" />
        }
        @case ('x-circle') {
          <circle cx="12" cy="12" r="9" />
          <path d="M9 9l6 6M15 9l-6 6" />
        }
        @case ('video') {
          <rect x="3" y="5" width="18" height="14" rx="3" />
          <path d="M10 9.5l5 2.5-5 2.5z" />
        }
        @case ('users') {
          <circle cx="9" cy="8" r="3.2" />
          <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" />
          <circle cx="17" cy="9" r="2.4" />
          <path d="M17 14.2c2.4.3 4 2.1 4 4.8" />
        }
        @case ('image') {
          <rect x="3" y="4" width="18" height="16" rx="3" />
          <circle cx="9" cy="10" r="1.8" />
          <path d="M4 18l5.5-5 4 3.5 3-2.5L21 17" />
        }
        @case ('film') {
          <rect x="3" y="4" width="18" height="16" rx="2.5" />
          <path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4" />
        }
        @case ('folder') {
          <path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        }
        @case ('list') {
          <path d="M9 6h11M9 12h11M9 18h11" />
          <circle cx="4.5" cy="6" r="1" />
          <circle cx="4.5" cy="12" r="1" />
          <circle cx="4.5" cy="18" r="1" />
        }
        @case ('cpu') {
          <rect x="6" y="6" width="12" height="12" rx="2" />
          <rect x="9.5" y="9.5" width="5" height="5" rx="1" />
          <path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" />
        }
        @case ('activity') {
          <path d="M3 12h4l3-7 4 14 3-7h4" />
        }
        @case ('settings') {
          <path d="M4 7h10M18 7h2M4 17h2M10 17h10" />
          <circle cx="16" cy="7" r="2" />
          <circle cx="8" cy="17" r="2" />
        }
        @case ('sparkles') {
          <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />
          <path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z" />
        }
        @case ('refresh') {
          <path d="M20 11a8 8 0 0 0-14.5-4M4 5v4h4" />
          <path d="M4 13a8 8 0 0 0 14.5 4M20 19v-4h-4" />
        }
        @case ('pause') {
          <path d="M8 5v14M16 5v14" />
        }
        @case ('play') {
          <path d="M7 5l12 7-12 7z" />
        }
        @case ('stop') {
          <rect x="6" y="6" width="12" height="12" rx="2" />
        }
        @case ('trash') {
          <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6" />
        }
        @case ('grip') {
          <circle cx="9" cy="6" r="1.2" fill="currentColor" />
          <circle cx="15" cy="6" r="1.2" fill="currentColor" />
          <circle cx="9" cy="12" r="1.2" fill="currentColor" />
          <circle cx="15" cy="12" r="1.2" fill="currentColor" />
          <circle cx="9" cy="18" r="1.2" fill="currentColor" />
          <circle cx="15" cy="18" r="1.2" fill="currentColor" />
        }
        @case ('arrow-up') {
          <path d="M12 19V5M6 11l6-6 6 6" />
        }
        @case ('arrow-down') {
          <path d="M12 5v14M6 13l6 6 6-6" />
        }
        @case ('chevron-right') {
          <path d="M9 5l7 7-7 7" />
        }
        @case ('clock') {
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        }
        @case ('laptop') {
          <rect x="5" y="5" width="14" height="10" rx="1.5" />
          <path d="M2.5 19h19" />
        }
        @case ('plug') {
          <path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0zM12 17v4" />
        }
        @case ('globe') {
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18" />
        }
        @case ('bolt') {
          <path d="M13 3L5 13.5h6L10 21l8-10.5h-6z" />
        }
      }
    </svg>
  `,
  styles: [
    `
      :host {
        display: inline-flex;
        flex: none;
        line-height: 0;
      }
    `,
  ],
})
export class IconComponent {
  readonly name = input.required<IconName>();
  readonly size = input(20);
}
