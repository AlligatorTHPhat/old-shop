import { Routes } from '@angular/router';

export const sellerRoutes: Routes = [
  {
    path: '',
    loadComponent: () => import('./layout/seller-layout').then(m => m.SellerLayoutComponent),
    children: [
      { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
      { path: 'dashboard', loadComponent: () => import('./dashboard/dashboard').then(m => m.SellerDashboardComponent) },
      { path: 'product-manage', loadComponent: () => import('./product-manage/product-manage').then(m => m.ProductManageComponent) },
      { path: 'order-manage', loadComponent: () => import('./order-manage/order-manage').then(m => m.OrderManageComponent) }
    ]
  }
];
