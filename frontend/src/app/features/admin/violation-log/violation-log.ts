import { Component, OnInit, inject, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AdminService } from '../../../shared/services/admin.service';
import { catchError, finalize } from 'rxjs/operators';
import { of } from 'rxjs';

@Component({
  selector: 'app-violation-log',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './violation-log.html',
  styleUrl: './violation-log.scss'
})
export class ViolationLogComponent implements OnInit {
  private adminService = inject(AdminService);
  private cdr = inject(ChangeDetectorRef);

  logs: any[] = [];
  userMap = new Map<number, string>();
  isLoading = false;

  // Cấu hình phân trang
  skip: number = 0;
  limit: number = 5; 
  rawLogsCount: number = 0;

  ngOnInit(): void {
    void this.loadInitialData();
  }

  /**
   * Getter tính toán số trang hiện tại dựa trên skip và limit
   */
  get currentPage(): number {
    return Math.floor(this.skip / this.limit) + 1;
  }

  /**
   * Khởi tạo dữ liệu ban đầu (Map User -> Load Logs)
   */
  async loadInitialData() {
    this.isLoading = true;
    this.cdr.markForCheck();

    this.adminService.getUsers(0, 100).pipe(
      catchError(() => of([])),
      finalize(() => {
        this.loadLogs();
      })
    ).subscribe(users => {
      if (users) {
        users.forEach((u: any) => this.userMap.set(u.user_id, u.username));
      }
    });
  }

  /**
   * Tải danh sách log
   */
  loadLogs() {
    this.isLoading = true;
    this.adminService.getViolationLogs(this.skip, this.limit).subscribe({
      next: (data: any[]) => {
        this.rawLogsCount = data.length;
        // Map dữ liệu và bổ sung username nếu backend chưa JOIN
        this.logs = data.map(log => ({
          ...log,
          username: log.username || this.userMap.get(log.user_id) || `User #${log.user_id}`
        }));
        this.isLoading = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error("Lỗi tải logs:", err);
        this.isLoading = false;
        this.cdr.detectChanges();
      }
    });
  }

  /**
   * Chuyển đến trang cụ thể khi nhập số vào Input
   */
  goToPage(event: any) {
    const inputElement = event.target as HTMLInputElement;
    const page = parseInt(inputElement.value);

    if (page && page > 0) {
      this.skip = (page - 1) * this.limit;
      this.loadLogs();
      this.scrollToTop();
    } else {
      // Reset về trang hiện tại nếu nhập lỗi
      inputElement.value = this.currentPage.toString();
    }
  }

  /**
   * Sang trang tiếp theo
   */
  nextPage() {
    if (!this.isLoading && this.rawLogsCount >= this.limit) {
      this.skip += this.limit;
      this.loadLogs();
      this.scrollToTop();
    }
  }

  /**
   * Quay lại trang trước
   */
  prevPage() {
    if (!this.isLoading && this.skip > 0) {
      this.skip = Math.max(0, this.skip - this.limit);
      this.loadLogs();
      this.scrollToTop();
    }
  }

  /**
   * Mapping màu sắc Badge
   */
  getActionClass(action: string): string {
    const act = action?.toUpperCase() || '';
    if (act.includes('DEACTIVATE_MODERATOR')) return 'badge-danger';
    if (act.includes('ACTIVATE_MODERATOR')) return 'badge-success';
    if (act.includes('DEACTIVATE')) return 'badge-orange';
    if (act.includes('ACTIVATE')) return 'badge-warning';
    return 'badge-info';
  }

  /**
   * Mapping Text Tiếng Việt
   */
  getFriendlyAction(action: string): string {
    if (!action) return 'Hành động';
    const labels: Record<string, string> = {
      'DEACTIVATE_MODERATOR': 'Khóa Kiểm duyệt',
      'ACTIVATE_MODERATOR': 'Mở khóa Kiểm duyệt',
      'DEACTIVATE': 'Khóa người dùng',
      'ACTIVATE': 'Mở khóa người dùng'
    };
    return labels[action.toUpperCase()] || action;
  }

  /**
   * Hiển thị người thực thi dựa trên hành động
   */
  getExecutioner(action: string): string {
    return action?.toUpperCase().includes('MODERATOR') ? 'Admin' : 'mod1';
  }

  private scrollToTop() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}