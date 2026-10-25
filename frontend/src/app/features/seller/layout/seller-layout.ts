import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-seller-layout',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './seller-layout.html',
  styleUrl: './seller-layout.scss'
})
export class SellerLayoutComponent {
  private authService = inject(AuthService);

  navSections = [
    {
      title: 'BẢNG ĐIỀU KHIỂN',
      icon: 'bi bi-clipboard-data-fill',
      items: [
        { path: 'dashboard', label: 'Tổng quan', icon: 'bi bi-pie-chart-fill' }
      ]
    },
    {
      title: 'QUẢN LÝ CỬA HÀNG',
      icon: 'bi bi-shop-window',
      items: [
        { path: 'product-manage', label: 'Quản lý sản phẩm', icon: 'bi bi-box-seam-fill' },
        { path: 'order-manage', label: 'Quản lý đơn hàng', icon: 'bi bi-cart-check-fill' }
      ]
    }
  ];

  constructor(private router: Router) {}

  logout() {
    this.authService.logout();
  }
}
