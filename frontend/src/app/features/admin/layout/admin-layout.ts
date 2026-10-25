import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-admin-layout',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './admin-layout.html',
  styleUrl: './admin-layout.scss'
})
export class AdminLayoutComponent {
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
      title: 'QUẢN LÝ THÔNG TIN',
      icon: 'bi bi-grid-fill',
      items: [
        { path: 'moderator-manage', label: 'Quản lý kiểm duyệt viên', icon: 'bi bi-people' },
        { path: 'category-manage', label: 'Danh mục sản phẩm', icon: 'bi bi-tags' },
        { path: 'voucher-manage', label: 'Quản lý mã giảm giá', icon: 'bi bi-percent' }
      ]
    },
    {
      title: 'NHẬT KÝ QUẢN TRỊ',
      icon: 'bi bi-chat-quote-fill',
      items: [
        { path: 'violation-log', label: 'Nhật ký quản trị', icon: 'bi bi-chat-dots' }
      ]
    },
    {
      title: 'Hồ sơ cá nhân',
      icon: 'bi bi-person-fill',
      items: [
        { path: 'profile', label: 'Thông tin cá nhân', icon: 'bi bi-person' }
      ]
    }
  ];

  constructor(private router: Router) {}

  logout() {
    this.authService.logout();
  }
}
