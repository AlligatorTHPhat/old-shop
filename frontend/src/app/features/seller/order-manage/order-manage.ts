import { Component, OnInit, inject, ChangeDetectorRef, NgZone } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms'; // <-- BẮT BUỘC CÓ ĐỂ CHẠY SEARCH
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { UIService } from '../../../core/services/ui.service';

@Component({
  selector: 'app-order-manage',
  standalone: true,
  imports: [CommonModule, FormsModule], // <-- Khai báo FormsModule ở đây
  templateUrl: './order-manage.html',
  styleUrl: './order-manage.scss'
})
export class OrderManageComponent implements OnInit {
  private http = inject(HttpClient);
  private uiService = inject(UIService);
  private apiUrl = environment.apiUrl;
  private cdr = inject(ChangeDetectorRef);
  private zone = inject(NgZone);

  Math = Math;

  orders: any[] = [];
  selectedOrder: any = null;
  showDetailModal = false;
  
  filterStatus: number | null = 0;
  searchTerm: string = ''; // Biến lưu từ khóa tìm kiếm
  
  // Biến Phân trang
  currentPage = 1;
  pageSize = 5;

  // Biến cho Modal Xác Nhận
  showConfirmModal = false;
  confirmOrder: any = null;
  confirmTargetStatus: number = 0;
  isUpdatingStatus = false;

  // Lọc Đơn hàng: KẾT HỢP TRẠNG THÁI + TÌM KIẾM
  get filteredOrders() {
    let list = this.orders.filter(o => o.order_status === this.filterStatus);
    
    if (this.searchTerm.trim()) {
      const term = this.searchTerm.trim().toLowerCase();
      list = list.filter(o => 
        o.order_id?.toString().includes(term) ||
        o.buyer?.full_name?.toLowerCase().includes(term) ||
        o.tracking_number?.toLowerCase().includes(term)
      );
    }
    return list;
  }

  get pagedOrders() {
    const start = (this.currentPage - 1) * this.pageSize;
    return this.filteredOrders.slice(start, start + this.pageSize);
  }

  get totalPages(): number {
    return Math.ceil(this.filteredOrders.length / this.pageSize) || 1;
  }

  get visiblePages(): number[] {
    const pages: number[] = [];
    const total = this.totalPages;
    const current = this.currentPage;

    let start = Math.max(1, current - 1);
    let end = Math.min(total, current + 1);

    if (current === 1) end = Math.min(total, 3);
    if (current === total) start = Math.max(1, total - 2);

    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    return pages;
  }

  goToPage(page: number) {
    if (page >= 1 && page <= this.totalPages) {
      this.currentPage = page;
    }
  }

  // Khi người dùng gõ tìm kiếm -> Trả về trang 1
  onSearchChange() {
    this.currentPage = 1;
  }

  switchTab(s: number) {
    this.filterStatus = s;
    this.currentPage = 1;
    this.searchTerm = ''; // Chuyển tab thì xóa trắng ô search cho gọn
    this.cdr.detectChanges();
  }

  ngOnInit() {
    this.loadOrders();
  }

  loadOrders() {
    this.http.get<any[]>(`${this.apiUrl}/orders/seller`).subscribe({
      next: (data) => {
        this.orders = data;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.uiService.showError('Không thể tải danh sách đơn hàng', 'Lỗi Server');
      }
    });
  }

  viewOrderDetails(orderId: number) {
    this.http.get<any>(`${this.apiUrl}/orders/${orderId}`).subscribe({
      next: (data) => {
        this.selectedOrder = data;
        this.showDetailModal = true;
        this.cdr.detectChanges();
      },
      error: () => {
        this.uiService.showError('Không thể tải chi tiết đơn hàng', 'Lỗi');
      }
    });
  }

  closeDetailModal() {
    this.showDetailModal = false;
    this.selectedOrder = null;
  }

  getNextStatusLabel(currentStatus: number): string {
    const statusLabels: Record<number, string> = {
      0: 'Xác nhận Đơn',
      1: 'Giao hàng',
      2: 'Hoàn thành'
    };
    return statusLabels[currentStatus] || 'Cập nhật';
  }

  getOrderStatus(status: number): { class: string, label: string } {
    const statusMap: Record<number, { class: string, label: string }> = {
      0: { class: 'custom-badge badge-warning', label: 'Chờ xác nhận' },
      1: { class: 'custom-badge badge-info', label: 'Đã xác nhận' },
      2: { class: 'custom-badge badge-primary', label: 'Đang giao hàng' },
      3: { class: 'custom-badge badge-success', label: 'Đã giao' },
      4: { class: 'custom-badge badge-danger', label: 'Đã hủy' }
    };
    return statusMap[status] || { class: 'custom-badge badge-secondary', label: 'Không xác định' };
  }

  openConfirmModal(order: any, newStatus: number) {
    this.confirmOrder = order;
    this.confirmTargetStatus = newStatus;
    this.showConfirmModal = true;
  }

  closeConfirmModal() {
    this.showConfirmModal = false;
    this.confirmOrder = null;
  }

  confirmUpdateStatus() {
    if (!this.confirmOrder || this.isUpdatingStatus) return;
    this.isUpdatingStatus = true;

    if (this.showDetailModal) {
      this.closeDetailModal();
    }

    this.http.put(`${this.apiUrl}/orders/${this.confirmOrder.order_id}`, { order_status: this.confirmTargetStatus }).subscribe({
      next: () => {
        this.isUpdatingStatus = false;
        this.closeConfirmModal();
        this.loadOrders();
      },
      error: (err) => {
        this.isUpdatingStatus = false;
        this.closeConfirmModal();
        this.uiService.showError(err.error?.message || 'Cập nhật thất bại', 'Lỗi Hệ Thống');
        this.cdr.detectChanges();
      }
    });
  }
}