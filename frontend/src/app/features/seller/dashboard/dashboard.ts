import { Component, OnInit, inject, ViewChild, ElementRef, AfterViewInit, ChangeDetectorRef } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import Chart from 'chart.js/auto';

@Component({
  selector: 'app-seller-dashboard',
  standalone: true,
  templateUrl: './dashboard.html',
  styleUrls: ['./dashboard.scss'],
  imports: [CommonModule, RouterModule]
})
export class SellerDashboardComponent implements OnInit, AfterViewInit {
  private http = inject(HttpClient);
  private apiUrl = environment.apiUrl;
  private cdr = inject(ChangeDetectorRef);

  @ViewChild('revenueChart') revenueChart!: ElementRef;

  stats = { totalProducts: 0, newOrders: 0, revenue: 0, rating: 4.8 };
  isLoading = true;

  quickActions = [
    { path: '/seller/product-manage', label: 'Quản lý Sản phẩm', desc: 'Thêm, sửa, xóa sản phẩm', icon: 'bi-box-seam-fill', color: 'text-primary', bg: 'bg-primary-light' },
    { path: '/seller/order-manage', label: 'Quản lý Đơn hàng', desc: 'Xử lý và giao hàng', icon: 'bi-cart-check-fill', color: 'text-success', bg: 'bg-success-light' }
  ];

  // Biến điều khiển Chart
  chartView: 'year' | 'month' = 'year';
  chartInstance: any;

  ngOnInit() {
    this.loadDashboardData();
  }

  ngAfterViewInit() {
    this.initChart();
  }

  loadDashboardData() {
    this.isLoading = true;
    forkJoin({
      products: this.http.get<any[]>(`${this.apiUrl}/products/seller/my-products`).pipe(catchError(() => of([]))),
      orders: this.http.get<any[]>(`${this.apiUrl}/orders/seller`).pipe(catchError(() => of([])))
    }).subscribe({
      next: (res) => {
        const totalProducts = res.products.length;
        const newOrders = res.orders.filter(o => o.order_status === 0).length;
        const totalRevenue = res.orders
          .filter(o => o.order_status === 3)
          .reduce((sum, order) => sum + Number(order.final_amount), 0);

        this.stats = {
          totalProducts: totalProducts,
          newOrders: newOrders,
          revenue: totalRevenue,
          rating: 4.8 // Tạm fix cứng
        };
        this.isLoading = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Lỗi load dữ liệu dashboard:', err);
        this.isLoading = false;
        this.cdr.detectChanges();
      }
    });
  }

  switchChartView(view: 'year' | 'month') {
    if (this.chartView === view) return;
    this.chartView = view;
    this.cdr.detectChanges();
    this.updateChartData();
  }

  initChart() {
    const ctx = this.revenueChart.nativeElement.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(66, 133, 244, 0.2)');
    gradient.addColorStop(1, 'rgba(66, 133, 244, 0)');

    if (this.chartInstance) {
      this.chartInstance.destroy();
    }

    this.chartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T12'],
        datasets: [{
          label: 'Doanh thu (VND)',
          data: [1500000, 2200000, 1800000, 4500000, 3100000, 5000000, 4200000, 0, 0, 0, 0, 0],
          borderColor: '#4285F4',
          borderWidth: 3,
          pointBackgroundColor: '#ffffff',
          pointBorderColor: '#4285F4',
          pointBorderWidth: 2,
          pointRadius: 4,
          fill: true,
          backgroundColor: gradient,
          tension: 0.4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: {
            beginAtZero: true,
            grid: { color: '#f1f1f1' },
            ticks: { color: '#6c757d', font: { weight: 'bold' } }
          },
          x: {
            grid: { display: false },
            ticks: { color: '#6c757d', font: { weight: 'bold' } }
          }
        }
      }
    });
  }

  updateChartData() {
    if (!this.chartInstance) return;

    if (this.chartView === 'year') {
      this.chartInstance.data.labels = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T12'];
      this.chartInstance.data.datasets[0].data = [1500000, 2200000, 1800000, 4500000, 3100000, 5000000, 4200000, 0, 0, 0, 0, 0];
    } else {
      this.chartInstance.data.labels = Array.from({length: 30}, (_, i) => `Ngày ${i + 1}`);
      this.chartInstance.data.datasets[0].data = Array.from({length: 30}, () => Math.floor(Math.random() * 500000) + 100000);
    }
    this.chartInstance.update();
  }
}