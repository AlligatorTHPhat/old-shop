import { Routes } from '@angular/router';

export const moderatorRoutes: Routes = [
  {
    path: '',
    loadComponent: () => import('./layout/moderator-layout').then(m => m.ModeratorLayoutComponent),
    children: [
      {
        path: '',
        redirectTo: 'dashboard',
        pathMatch: 'full'
      },
      {
        path: 'dashboard',
        loadComponent: () => import('./dashboard/moderator-dashboard').then(m => m.ModeratorDashboardComponent)
      },
      {
        path: 'user-manage',
        loadComponent: () => import('./user-manage/user-manage').then(m => m.ModeratorUserManageComponent)
      },
      {
        path: 'product-manage',
        loadComponent: () => import('./product-manage/product-manage').then(m => m.ModeratorProductManageComponent)
      },
      {
        path: 'profile',
        loadComponent: () => import('./profile/profile').then(m => m.ModeratorProfileComponent)
      },
      {
        path: 'review-manage',
        loadComponent: () => import('./review-manage/review-manage').then(m => m.ReviewManageComponent)
      },
      {
        path: '**',
        redirectTo: 'dashboard'
      }
    ]
  }
];
