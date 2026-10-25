import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { UIService } from '../../../core/services/ui.service';

@Component({
  selector: 'app-my-orders',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './my-orders.html',
  styleUrl: './my-orders.scss'
})
export class MyOrdersComponent implements OnInit {
  private http = inject(HttpClient);
  private uiService = inject(UIService);
  private apiUrl = `${environment.apiUrl}/orders`;

  // Sử dụng Signal để quản lý state cho mượt
  orders = signal<any[]>([]);
  selectedOrder = signal<any>(null);
  showDetailModal = signal(false);
  
  // Phân trang
  currentPage = signal(1);
  pageSize = 4; 
  
  // Computed để tự động phân trang ở FE (hoặc gọi API nếu ông muốn chuẩn BE)
  paginatedOrders = computed(() => {
    const start = (this.currentPage() - 1) * this.pageSize;
    return this.orders().slice(start, start + this.pageSize);
  });

  canCancel(status: number): boolean {
    // 0: Chờ xác nhận (Hủy OK)
    // 1: Đã xác nhận (KHÔNG HỦY)
    // 2: Đang giao (Hủy OK - Theo ý ông)
    // 3: Đã giao (Hủy OK - Theo ý ông, dù thực tế thường là Trả hàng)
    // 4: Đã hủy rồi thì không hiện nút nữa
    return status !== 1 && status !== 4;
  }

  totalPages = computed(() => Math.ceil(this.orders().length / this.pageSize));

  ngOnInit() {
    this.loadMyOrders();
  }

  loadMyOrders() {
    // API /orders đã được BE filter theo buyer_id nhờ token
    this.http.get<any[]>(this.apiUrl).subscribe({
      next: (data) => this.orders.set(data),
      error: () => this.uiService.showError('Không thể tải lịch sử đơn hàng', 'Lỗi')
    });
  }

  viewDetail(orderId: number) {
    this.http.get<any>(`${this.apiUrl}/${orderId}`).subscribe({
      next: (data) => {
        this.selectedOrder.set(data);
        this.showDetailModal.set(true);
      },
      error: () => this.uiService.showError('Lỗi lấy chi tiết đơn hàng', 'Lỗi')
    });
  }

  cancelOrder(orderId: number) {
    if (confirm('Ông có chắc chắn muốn hủy đơn hàng này không?')) {
      this.http.put(`${this.apiUrl}/${orderId}`, { order_status: 4 }).subscribe({
        next: () => {
          this.uiService.showSuccess('Đã hủy đơn hàng thành công', 'Thông báo');
          this.loadMyOrders();
        },
        error: (err) => {
          // Nếu BE ông chưa cho phép hủy ở status 2, 3 thì nó sẽ bắn lỗi ở đây
          this.uiService.showError(err.error?.detail || 'Lỗi hệ thống khi hủy đơn', 'Lỗi');
        }
      });
    }
  }
  
  getStatusInfo(status: number) {
    const statusMap: any = {
      0: { label: 'Chờ xác nhận', class: 'bg-warning text-dark' },
      1: { label: 'Đã xác nhận', class: 'bg-info text-dark' },
      2: { label: 'Đang giao hàng', class: 'bg-primary' },
      3: { label: 'Đã giao', class: 'bg-success' },
      4: { label: 'Đã hủy', class: 'bg-danger' }
    };
    return statusMap[status] || { label: 'N/A', class: 'bg-secondary' };
  }

  setPage(page: number) {
    if (page >= 1 && page <= this.totalPages()) {
      this.currentPage.set(page);
    }
  }
}