import { Component, signal, OnInit, OnDestroy, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CommonModule } from '@angular/common';
import { AuthService } from '../../core/services/auth.service';

/**
 * Home Component - Professional E-commerce Landing Page
 * Manages product carousel, authentication state, and customer interactions
 */
@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './home.html',
  styleUrl: './home.scss'
})
export class HomeComponent implements OnInit, OnDestroy {
  private authService = inject(AuthService);

  // ===== AUTHENTICATION STATE =====
  /** User authentication state */
  isLoggedIn = this.authService.isLoggedIn;

  /** Current logged-in user's full name */
  currentUser = this.authService.currentUser;

  // ===== CAROUSEL STATE =====
  /** Current slide index for product carousel */
  currentSlide = signal(0);

  /** Support agent online status */
  isAgentOnline = signal(true);

  /** Product showcase carousel data */
  carouselImages = [
    { src: '/assets/images/carousel-1.png', alt: 'Sản phẩm mỹ phẩm chính hãng' },
    { src: '/assets/images/carousel-2.png', alt: 'Sản phẩm điện tử đã qua sử dụng' }
  ];

  /** Auto-slide interval reference */
  private slideInterval?: number;

  // ===== LIFECYCLE HOOKS =====
  /**
   * Initialize component - Set up carousel and load user data
   */
  ngOnInit() {
    this.startAutoSlide();
    this.loadUserData();
  }

  logoutHero() {
    this.authService.logout();
  }

  /**
   * Cleanup - Stop auto-slide interval
   */
  ngOnDestroy() {
    this.stopAutoSlide();
  }

  // ===== CAROUSEL CONTROL METHODS =====
  /**
   * Start automatic carousel sliding every 5 seconds
   * Respects user pause when manually navigating
   */
  private startAutoSlide() {
    this.slideInterval = window.setInterval(() => {
      this.nextSlide();
    }, 5000);
  }

  /**
   * Stop the auto-slide interval
   */
  private stopAutoSlide() {
    if (this.slideInterval) {
      clearInterval(this.slideInterval);
    }
  }

  /**
   * Navigate to next slide in carousel
   */
  nextSlide() {
    this.currentSlide.update(current =>
      (current + 1) % this.carouselImages.length
    );
  }

  /**
   * Navigate to previous slide in carousel
   */
  prevSlide() {
    this.currentSlide.update(current =>
      current === 0 ? this.carouselImages.length - 1 : current - 1
    );
  }

  /**
   * Jump directly to a specific slide
   * @param index Slide index (0-based)
   */
  goToSlide(index: number) {
    if (index >= 0 && index < this.carouselImages.length) {
      this.currentSlide.set(index);
    }
  }

  // ===== AUTHENTICATION METHODS =====
  /**
   * No need to sync from localStorage; AuthService manages session state using sessionStorage.
   */
  private loadUserData() {
    // intentionally empty; AuthService signals handle current login status
  }
}
