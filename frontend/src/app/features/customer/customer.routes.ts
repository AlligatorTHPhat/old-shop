import { Routes } from '@angular/router';
import { authGuard, guestGuard } from '../../core/guards/auth.guard';

export const customerRoutes: Routes = [
  {
    path: 'cart',
    loadComponent: () => import('./cart/cart').then(m => m.CartComponent),
    canActivate: [authGuard]
  },
  {
    path: 'checkout',
    loadComponent: () => import('./checkout/checkout').then(m => m.CheckoutComponent),
    canActivate: [authGuard]
  },
  {
    path: 'profile',
    loadComponent: () => import('./profile/profile').then(m => m.ProfileComponent),
    canActivate: [authGuard]
  },
  { 
    path: '', 
    canActivate: [guestGuard],
    loadComponent: () => import('../home/home').then(m => m.HomeComponent)
  },
  {
    path: 'my-orders',
    loadComponent: () => import('./my-orders/my-orders').then(m => m.MyOrdersComponent),
    canActivate: [authGuard]
  }
];