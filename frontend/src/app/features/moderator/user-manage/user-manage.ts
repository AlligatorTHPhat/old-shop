import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ModeratorService } from '../../../shared/services/moderator.service';

@Component({
  selector: 'app-moderator-user-manage',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './user-manage.html',
  styleUrl: './user-manage.scss'
})
export class ModeratorUserManageComponent implements OnInit {
  users: any[] = [];
  filteredUsers: any[] = [];
  isLoading = false;
  actionLoading = false;
  searchTerm = '';
  message: string | null = null;
  currentTab: 'active' | 'locked' = 'active';

  // Modal control
  showStatusModal = false;
  selectedUser: any = null;
  statusReason = '';
  isBanAction = true;

  currentPage: number = 1;
  pageSize: number = 5;

  constructor(
    private moderatorService: ModeratorService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadUsers();
  }

  get paginatedUsers() {
    const start = (this.currentPage - 1) * this.pageSize;
    const end = start + this.pageSize;
    return this.filteredUsers.slice(start, end);
  }

  get totalPages(): number {
    return Math.ceil(this.filteredUsers.length / this.pageSize);
  }

  loadUsers(): void {
    this.isLoading = true;
    this.message = null;
    this.moderatorService.getUsers().subscribe({
      next: (data) => {
        console.log('Data user nhận được:', data);

        // LOG ĐỂ KIỂM TRA CHÍNH XÁC TÊN TRƯỜNG
        if (data && data.length > 0) {
          console.log('User đầu tiên có cấu trúc:', data[0]);
        }

        this.users = data.filter((user: any) => {
          // Kiểm tra xem mảng roles có tồn tại và có role nào mang id = 3 không
          return user.roles && user.roles.some((r: any) => Number(r.role_id) === 3);
        });

        this.filterUsers();
        this.isLoading = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.message = 'Không tải được danh sách.';
        this.isLoading = false;
        this.cdr.detectChanges();
      }
    });
  }

  selectTab(tab: 'active' | 'locked'): void {
    this.currentTab = tab;
    this.currentPage = 1;
    this.filterUsers();
  }

  filterUsers(): void {
    let list = [...this.users];
    if (this.currentTab === 'active') {
      list = list.filter(u => u.is_active);
    } else {
      list = list.filter(u => !u.is_active);
    }
    const term = this.searchTerm.trim().toLowerCase();
    if (term) {
      list = list.filter((user) =>
        user.username?.toLowerCase().includes(term) ||
        user.email?.toLowerCase().includes(term) ||
        user.full_name?.toLowerCase().includes(term) ||
        user.user_id?.toString().includes(term)
      );
    }
    this.filteredUsers = list;
    this.currentPage = 1;
  }

  openStatusModal(user: any): void {
    this.selectedUser = user;
    this.isBanAction = user.is_active;
    this.statusReason = '';
    this.showStatusModal = true;
    this.cdr.detectChanges();
  }

  closeStatusModal(): void {
    this.showStatusModal = false;
    this.selectedUser = null;
    this.statusReason = '';
    this.cdr.detectChanges();
  }

  confirmStatusChange(): void {
    if (!this.statusReason.trim() || !this.selectedUser) return;

    this.actionLoading = true;
    this.message = null;

    const obs = this.isBanAction
      ? this.moderatorService.banUser(this.selectedUser.user_id, this.statusReason)
      : this.moderatorService.unbanUser(this.selectedUser.user_id, this.statusReason);

    obs.subscribe({
      next: () => {
        const label = this.isBanAction ? 'khóa' : 'mở khóa';
        this.message = `Người dùng đã được ${label} thành công.`;
        this.actionLoading = false;
        this.closeStatusModal();
        this.loadUsers();
      },
      error: (err) => {
        console.error('Error updating account status:', err);
        this.message = err?.error?.detail || 'Không thể cập nhật trạng thái người dùng.';
        this.actionLoading = false;
        this.cdr.detectChanges();
      }
    });
  }
}
