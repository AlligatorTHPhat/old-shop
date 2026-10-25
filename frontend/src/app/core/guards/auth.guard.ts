import { inject } from '@angular/core';
import { Router, CanActivateFn } from '@angular/router';
import { AuthService } from '../services/auth.service';

export const authGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (authService.isAuthenticated()) {
    return true;
  }
  router.navigate(['/auth/login']);
  return false;
};

// src/app/core/guards/auth.guard.ts
export const adminGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  const isAuthenticated = authService.isAuthenticated();
  const role = authService.getUserRole();
  const isInitialized = authService.isInitialized();

  console.log('[adminGuard] Debug:', { isAuthenticated, role, isInitialized });

  if (!isInitialized) {
    console.log('[adminGuard] Blocked: Not initialized yet');
    return false;
  }

  if (isAuthenticated && Number(role) === 1) {
    console.log('[adminGuard] Access granted');
    return true;
  }

  console.warn('[adminGuard] Access denied. role:', role);
  router.navigate(['/home']);
  return false;
};


export const moderatorGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  const isAuthenticated = authService.isAuthenticated();
  const role = authService.getUserRole();
  const isInitialized = authService.isInitialized();

  console.log('[moderatorGuard] Debug:', { isAuthenticated, role, isInitialized });

  if (!isInitialized) {
    console.log('[moderatorGuard] Blocked: Not initialized yet');
    return false;
  }

  if (!isAuthenticated) {
    console.log('[moderatorGuard] Blocked: Not authenticated');
    router.navigate(['/auth/login']);
    return false;
  }

  if (role !== null && (Number(role) === 1 || Number(role) === 2)) {
    console.log('[moderatorGuard] Access granted');
    return true;
  }

  console.warn('[moderatorGuard] Access denied. role:', role);
  alert('Bạn không có quyền truy cập trang moderator.');
  router.navigate(['/home']);
  return false;
};


export const guestGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);
  const role = authService.getUserRole();

  if (authService.isAuthenticated()) {
    if (Number(role) === 1) {
      router.navigate(['/admin/dashboard']);
    } else {
      router.navigate(['/home']);
    }
    return false;
  }
  return true;
};

export const sellerGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  const isAuthenticated = authService.isAuthenticated();
  const role = authService.getUserRole();
  const isInitialized = authService.isInitialized();

  if (!isInitialized) return false;

  if (isAuthenticated && (Number(role) === 1 || Number(role) === 3)) {
    return true;
  }

  console.warn('[sellerGuard] Access denied. role:', role);
  router.navigate(['/home']);
  return false;
};