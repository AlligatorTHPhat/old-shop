import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AdminService } from '../../../shared/services/admin.service';

@Component({
  selector: 'app-moderator-manage',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './moderator-manage.html',
  styleUrl: './moderator-manage.scss'
})
export class ModeratorManageComponent implements OnInit {
  moderators: any[] = [];       // danh sách hiển thị (sau lọc)
  allModerators: any[] = [];    // raw data từ API
  skip = 0;
  limit = 5;
  isLoading = false;
  
  showModal = false;
  showStatusModal = false;
  showDuplicateModal = false;
  duplicateErrorMsg = '';
  duplicateErrorTitle = 'Dữ liệu bị trùng!';
  
  editingModerator: any = null;
  statusModalModerator: any = null;
  statusReason = '';
  statusAction: 'lock' | 'unlock' = 'lock';
  activeTab: 'active' | 'locked' = 'active';
  searchTerm: string = '';

  moderatorForm = {
    username: '', email: '', password: '', full_name: '', phone_number: '', address: ''
  };

  constructor(
    private adminService: AdminService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadModerators();
  }

  // Apply lọc tab + search vào danh sách hiển thị (giống voucher-manage)
  applyFilterAndTab(): void {
    let filtered = this.allModerators;
    filtered = (this.activeTab === 'locked')
      ? filtered.filter(mod => mod.is_active === false)
      : filtered.filter(mod => mod.is_active === true);

    if (this.searchTerm.trim()) {
      const term = this.searchTerm.toLowerCase();
      filtered = filtered.filter(mod =>
        mod.username?.toLowerCase().includes(term) ||
        mod.email?.toLowerCase().includes(term) ||
        mod.full_name?.toLowerCase().includes(term)
      );
    }
    this.moderators = filtered;
  }

  // Getters phân trang
  get filteredModerators(): any[] { return this.moderators; }
  get pagedModerators(): any[] { return this.moderators.slice(this.skip, this.skip + this.limit); }
  get totalPages(): number { return Math.ceil(this.moderators.length / this.limit); }
  get currentPage(): number { return Math.floor(this.skip / this.limit) + 1; }
  get visiblePages(): number[] {
    const pages: number[] = [];
    const total = this.totalPages;
    const current = this.currentPage;
    let start = Math.max(1, current - 1);
    let end = Math.min(total, current + 1);
    if (current === 1) end = Math.min(total, 3);
    if (current === total) start = Math.max(1, total - 2);
    for (let i = start; i <= end; i++) { pages.push(i); }
    return pages;
  }

  onSearchChange() {
    this.skip = 0;
    this.applyFilterAndTab();
  }

  goToPage(page: number) {
    if (page >= 1 && page <= this.totalPages) {
      this.skip = (page - 1) * this.limit;
    }
  }

  nextPage(): void {
    if (this.currentPage < this.totalPages) { this.skip += this.limit; }
  }

  prevPage(): void {
    if (this.skip >= this.limit) { this.skip -= this.limit; }
  }

  loadModerators(): void {
    this.isLoading = true;
    this.adminService.getModerators(true).subscribe({
      next: (data: any) => {
        this.allModerators = data;
        this.applyFilterAndTab();
        if (this.skip >= this.moderators.length) this.skip = 0;
        this.isLoading = false;
        this.cdr.detectChanges();
      },
      error: (err: any) => {
        console.error('Error loading moderators:', err);
        this.isLoading = false;
        this.cdr.detectChanges();
      }
    });
  }

  switchTab(tab: 'active' | 'locked'): void {
    this.activeTab = tab;
    this.skip = 0;
    this.searchTerm = '';
    this.applyFilterAndTab();
  }

  openModal(moderator: any = null): void {
    this.editingModerator = moderator;
    if (moderator) {
      this.moderatorForm = {
        username: moderator.username, email: moderator.email, password: '',
        full_name: moderator.full_name || '', phone_number: moderator.phone_number || '', address: moderator.address || ''
      };
    } else {
      this.moderatorForm = {
        username: '', email: '', password: '', full_name: '', phone_number: '', address: ''
      };
    }
    this.showModal = true;
  }

  closeModal(): void {
    this.showModal = false;
    this.editingModerator = null;
  }

  saveModerator(): void {
    if (this.editingModerator) {
      this.closeModal();
    } else {
      this.createModerator();
    }
  }

  createModerator(): void {
    if (!this.moderatorForm.username || !this.moderatorForm.email || !this.moderatorForm.password || !this.moderatorForm.full_name) {
      alert('Vui lòng điền đầy đủ thông tin bắt buộc.');
      return;
    }
    this.adminService.createModerator(this.moderatorForm).subscribe({
      next: () => {
        this.loadModerators();
        this.closeModal();
      },
      error: (err: any) => {
        console.error('Error creating moderator:', err);
        const detail = err?.error?.detail || 'Tạo moderator thất bại.';
        const isDuplicate = detail.toLowerCase().includes('already exists') || detail.toLowerCase().includes('đã tồn tại') || detail.toLowerCase().includes('trùng');
        
        this.duplicateErrorMsg = detail;
        this.duplicateErrorTitle = isDuplicate ? 'Dữ liệu bị trùng!' : 'Lỗi khởi tạo!';
        this.showDuplicateModal = true;
        this.showModal = false;
        this.cdr.detectChanges();
      }
    });
  }

  closeDuplicateModal(): void {
    this.showDuplicateModal = false;
    this.duplicateErrorMsg = '';
    this.showModal = true;
  }

  openStatusModal(moderator: any): void {
    this.statusModalModerator = moderator;
    this.statusAction = moderator.is_active ? 'lock' : 'unlock';
    this.statusReason = '';
    this.showStatusModal = true;
  }

  closeStatusModal(): void {
    this.showStatusModal = false;
    this.statusModalModerator = null;
    this.statusReason = '';
  }

  saveStatusChange(): void {
    if (!this.statusModalModerator) return;
    if (!this.statusReason.trim()) {
      alert('Vui lòng nhập lý do.');
      return;
    }
    this.adminService.toggleModeratorStatus(
      this.statusModalModerator.user_id,
      this.statusAction,
      this.statusReason.trim()
    ).subscribe({
      next: () => {
        this.closeStatusModal();
        this.loadModerators();
      },
      error: (err: any) => {
        console.error('Error toggling moderator status:', err);
        alert(err?.error?.detail || 'Không thể cập nhật trạng thái moderator.');
        this.cdr.detectChanges();
      }
    });
  }

  trackByUserId(index: number, item: any): any {
    return item.user_id || index;
  }
}