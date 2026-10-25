import { Component, OnInit, ChangeDetectorRef, ViewChild, ElementRef, AfterViewInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AdminService } from '../../../shared/services/admin.service';
import { RouterModule } from '@angular/router';
import Chart from 'chart.js/auto';

@Component({
  selector: 'app-admin-dashboard',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss'
})
export class AdminDashboardComponent implements OnInit, AfterViewInit {
  @ViewChild('adminChart') adminChart!: ElementRef;
  
  stats: any = {
    total_users: 0,
    total_orders: 0,
    pending_products: 0,
    total_revenue: 0
  };
  isLoading = true;

  // Biến điều khiển Chart
  chartView: 'year' | 'month' = 'year';
  chartInstance: any;

  constructor(
    private adminService: AdminService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadStats();
  }

  ngAfterViewInit(): void {
    this.initChart();
  }

  loadStats() {
    this.isLoading = true;
    this.adminService.getStats().subscribe({
      next: (data) => {
        this.stats = data;
        this.isLoading = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Error loading stats:', err);
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
    const ctx = this.adminChart.nativeElement.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(13, 110, 253, 0.2)');
    gradient.addColorStop(1, 'rgba(13, 110, 253, 0)');

    if (this.chartInstance) {
      this.chartInstance.destroy();
    }

    this.chartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T12'],
        datasets: [{
          label: 'Doanh thu (VND)',
          data: [45000000, 52000000, 48000000, 70000000, 65000000, 80000000, 85000000, 0, 0, 0, 0, 0],
          borderColor: '#0d6efd',
          borderWidth: 3,
          pointBackgroundColor: '#ffffff',
          pointBorderColor: '#0d6efd',
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
        plugins: {
          legend: { display: false }
        },
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
      this.chartInstance.data.datasets[0].data = [45000000, 52000000, 48000000, 70000000, 65000000, 80000000, 85000000, 0, 0, 0, 0, 0];
    } else {
      // Fake data 30 ngày cho tháng
      this.chartInstance.data.labels = Array.from({length: 30}, (_, i) => `Ngày ${i + 1}`);
      this.chartInstance.data.datasets[0].data = Array.from({length: 30}, () => Math.floor(Math.random() * 5000000) + 1000000);
    }

    // Cập nhật lại biểu đồ với animation
    this.chartInstance.update();
  }
}