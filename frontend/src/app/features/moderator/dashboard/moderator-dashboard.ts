import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { ModeratorService } from '../../../shared/services/moderator.service';

@Component({
  selector: 'app-moderator-dashboard',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './moderator-dashboard.html',
  styleUrl: './moderator-dashboard.scss'
})
export class ModeratorDashboardComponent implements OnInit {
  pendingProducts: any[] = [];
  users: any[] = [];

  loadingProducts = false;
  loadingUsers = false;
  actionLoading = false;
  message: string | null = null;

  constructor(
    private moderatorService: ModeratorService, 
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadDashboard();
  }

  get totalTasks(): number {
    return this.pendingProducts.length + this.users.length;
  }

  loadDashboard(): void {
    this.loadPendingProducts();
    this.loadUsers();
  }

  loadPendingProducts(): void {
    this.loadingProducts = true;
    this.moderatorService.getPendingProducts().subscribe({
      next: (data) => {
        this.pendingProducts = data;
        this.loadingProducts = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Error loading pending products:', err);
        this.loadingProducts = false;
        this.cdr.detectChanges();
      }
    });
  }

  loadUsers(): void {
    this.loadingUsers = true;
    this.moderatorService.getUsers().subscribe({
      next: (data) => {
        // Lọc qua mảng roles
        this.users = data.filter((user: any) => 
          user.roles && user.roles.some((r: any) => r.role_id === 3)
        );
        this.loadingUsers = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Error loading users:', err);
        this.loadingUsers = false;
      }
    });
  }

  approveProduct(productId: number): void {
    this.performAction(() => this.moderatorService.approveProduct(productId, 1), 'Sản phẩm đã được duyệt.');
  }

  rejectProduct(productId: number): void {
    const reason = prompt('Lý do từ chối / yêu cầu sửa đổi:');
    if (!reason) {
      return;
    }
    this.performAction(() => this.moderatorService.approveProduct(productId, 2, reason), 'Sản phẩm đã bị từ chối.');
  }

  lockUser(user: any): void {
    const reason = prompt('Lý do khóa tài khoản tạm thời:');
    if (!reason) {
      return;
    }
    this.performAction(() => this.moderatorService.lockUnlockUser(user.user_id, 'lock', reason), 'Người dùng đã bị khóa.');
  }

  unlockUser(user: any): void {
    const reason = prompt('Lý do mở khóa tài khoản:');
    if (!reason) {
      return;
    }
    this.performAction(() => this.moderatorService.lockUnlockUser(user.user_id, 'unlock', reason), 'Người dùng đã được mở khóa.');
  }

  private performAction(action: () => import('rxjs').Observable<any>, successMessage: string): void {
    this.actionLoading = true;
    this.message = null;
    action().subscribe({
      next: () => {
        this.message = successMessage;
        this.actionLoading = false;
        this.loadDashboard();
      },
      error: (err: any) => {
        console.error('Action failed:', err);
        this.message = err?.error?.detail || 'Thực hiện hành động thất bại.';
        this.actionLoading = false;
      }
    });
  }
}
