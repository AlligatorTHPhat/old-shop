import { Component, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterOutlet, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { HeaderComponent } from './layout/components/header/header';
import { FooterComponent } from './layout/components/footer/footer';
import { UIService, ModalConfig } from './core/services/ui.service';

declare var bootstrap: any;

import { AuthService } from './core/services/auth.service';
import { RegisterComponent } from './features/auth/register/register';
import { LoginComponent } from './features/auth/login/login';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, HeaderComponent, FooterComponent, RegisterComponent, LoginComponent],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})

export class App {
  protected readonly title = signal('Oldshop Ecommerce');
  protected showShell = signal(true);
  modalConfig: ModalConfig | null = null;
  authService = inject(AuthService);

  constructor(private router: Router, private uiService: UIService) {
    const initialUrl = window.location.pathname;
    const isSpecialRoute = initialUrl.startsWith('/moderator') || initialUrl.startsWith('/admin') || initialUrl.startsWith('/seller');
    this.showShell.set(!isSpecialRoute);

    this.router.events.pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd)).subscribe((event) => {
      const isSpecialRoute = event.urlAfterRedirects.startsWith('/moderator') || 
                             event.urlAfterRedirects.startsWith('/admin') ||
                             event.urlAfterRedirects.startsWith('/seller');
      this.showShell.set(!isSpecialRoute);
    });

    this.uiService.modal$.subscribe(config => {
      setTimeout(() => {
        this.modalConfig = config;
      });
    });

  }
}
