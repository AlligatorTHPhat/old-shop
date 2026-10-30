import { Component, OnInit, OnDestroy, ChangeDetectorRef, ViewChild, ElementRef, AfterViewInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AdminService } from '../../../shared/services/admin.service';
import { AdminDashboardStats } from '../../../core/models';
import { RouterModule } from '@angular/router';
import Chart from 'chart.js/auto';
import { salesChart } from './sales-chart';

@Component({
  selector: 'app-admin-dashboard', standalone: true,
  imports: [CommonModule, RouterModule, FormsModule],
  templateUrl: './dashboard.html', styleUrl: './dashboard.scss'
})
export class AdminDashboardComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('adminChart') adminChart!: ElementRef<HTMLCanvasElement>;
  stats: AdminDashboardStats = { total_users: 0, total_orders: 0, pending_products: 0, total_revenue: 0 };
  isLoading = true;
  error = '';
  chartView: 'year' | 'month' = 'year';
  salesYear = Number(new Intl.DateTimeFormat('en', { year: 'numeric', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date()));
  salesMonth = Number(new Intl.DateTimeFormat('en', { month: 'numeric', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date()));
  months = Array.from({ length: 12 }, (_, i) => i + 1);
  chartInstance?: Chart;

  constructor(private adminService: AdminService, private cdr: ChangeDetectorRef) {}

  ngOnInit() { this.loadStats(); }
  ngAfterViewInit() { this.initChart(); }
  ngOnDestroy() { this.chartInstance?.destroy(); }

  loadStats() {
    this.isLoading = true;
    this.error = '';
    this.adminService.getStats(this.salesYear).subscribe({
      next: data => {
        this.stats = data;
        this.isLoading = false;
        this.updateChartData();
        this.cdr.detectChanges();
      },
      error: () => {
        this.error = 'Không thể cập nhật số liệu. Dữ liệu đang hiển thị có thể đã cũ.';
        this.isLoading = false;
        this.cdr.detectChanges();
      }
    });
  }

  switchChartView(view: 'year' | 'month') { this.chartView = view; this.updateChartData(); }

  initChart() {
    this.chartInstance = new Chart(this.adminChart.nativeElement, {
      type: 'line', data: { labels: [], datasets: [{
        label: 'Giá trị hàng đã giao (VND)', data: [], borderColor: '#0d6efd', tension: 0.2
      }] },
      options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } }
    });
    this.updateChartData();
  }

  updateChartData() {
    if (!this.chartInstance) return;
    const series = salesChart(this.stats.sales_report, this.chartView, this.salesMonth);
    this.chartInstance.data.labels = series.labels;
    this.chartInstance.data.datasets[0].data = series.values;
    this.chartInstance.update();
  }
}
