import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-moderator-layout',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './moderator-layout.html',
  styleUrl: './moderator-layout.scss'
})
export class ModeratorLayoutComponent {
  private authService = inject(AuthService);

  navSections = [
    {
      title: 'HỆ THỐNG',
      icon: 'bi bi-hdd-network',
      items: [
        { path: 'dashboard', label: 'Dashboard', icon: 'bi bi-speedometer2' }
      ]
    },
    {
      title: 'QUẢN LÝ NỘI DUNG',
      icon: 'bi bi-grid-fill',
      items: [
        { path: 'user-manage', label: 'Quản lý người dùng', icon: 'bi bi-people' },
        { path: 'product-manage', label: 'Kiểm duyệt sản phẩm', icon: 'bi bi-box-seam' },
        { path: 'review-manage', label: 'Quản lý báo cáo vi phạm', icon: 'bi-box-arrow-in-down' },
        { path: 'profile', label: 'Thông tin cá nhân', icon: 'bi bi-person' }
      ]
    }
  ];

  constructor(private router: Router) {}

  logout(): void {
    this.authService.logout();
  }
}
