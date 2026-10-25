import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AdminService } from '../../../shared/services/admin.service';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-category-manage',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './category-manage.html',
  styleUrl: './category-manage.scss'
})
export class CategoryManageComponent implements OnInit {
  categories: any[] = [];
  skip = 0;
  limit = 5;
  isLoading = false;
  showModal = false;
  editingCategory: any = null;
  activeTab: 'active' | 'trash' = 'active';
  allCategories: any[] = [];

  searchTerm: string = '';

  showConfirmModal = false;
  confirmTitle = '';
  confirmMessage = '';
  confirmActionType: 'delete' | 'restore' | 'hardDelete' | 'warning' | null = null;
  pendingCategoryId: number | null = null;

  categoryForm = { name: '', description: '', parent_id: null as number | null, is_active: true };

  constructor(private adminService: AdminService, private cdr: ChangeDetectorRef) {}

  ngOnInit(): void {
    this.loadCategories();
  }

  get filteredCategories(): any[] {
    if (!this.searchTerm.trim()) {
      return this.categories;
    }
    const lowerTerm = this.searchTerm.toLowerCase();
    return this.categories.filter(cat => 
      cat.name.toLowerCase().includes(lowerTerm) || 
      (cat.description && cat.description.toLowerCase().includes(lowerTerm))
    );
  }

  loadCategories() {
    this.isLoading = true;
    this.categories = [];
    this.adminService.getCategories(false, true).subscribe({
      next: (data) => {
        this.allCategories = data;
        if (this.activeTab === 'trash') {
          this.categories = data.filter(cat => cat.is_deleted === true);
        } else {
          this.categories = data.filter(cat => !cat.is_deleted)
            .sort((a, b) => (a.is_active === b.is_active ? 0 : a.is_active ? -1 : 1));
        }
        if (this.skip >= this.categories.length) this.skip = 0;
        this.isLoading = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Lỗi khi tải danh mục:', err);
        this.isLoading = false;
        this.cdr.detectChanges();
      }
    });
  }

  getParentName(parentId: number | null): string {
    if (!parentId) return 'N/A';
    const parent = this.allCategories.find(c => c.category_id === parentId);
    return parent ? parent.name : `#${parentId}`;
  }

  switchTab(tab: 'active' | 'trash') {
    this.activeTab = tab;
    this.skip = 0;
    this.loadCategories();
  }
  get pagedCategories(): any[] {
    return this.filteredCategories.slice(this.skip, this.skip + this.limit);
  }

  get currentPage(): number {
    return Math.floor(this.skip / this.limit) + 1;
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

  onSearchChange() {
    this.skip = 0; 
  }

  goToPage(page: number) {
    if (page >= 1 && page <= this.totalPages) {
      this.skip = (page - 1) * this.limit;
    }
  }

  get totalPages(): number {
    return Math.ceil(this.filteredCategories.length / this.limit);
  }

  nextPage(): void { if (this.skip + this.limit < this.categories.length) this.skip += this.limit; }
  prevPage(): void { if (this.skip >= this.limit) this.skip -= this.limit; }

  openModal(category: any = null) {
    this.editingCategory = category;
    this.categoryForm = category ? 
      { name: category.name, description: category.description, parent_id: category.parent_id, is_active: category.is_active } : 
      { name: '', description: '', parent_id: null, is_active: true };
    this.showModal = true;
  }

  closeModal() { this.showModal = false; this.editingCategory = null; }

  saveCategory() {
    const request = this.editingCategory ? 
      this.adminService.updateCategory(this.editingCategory.category_id, this.categoryForm) : 
      this.adminService.createCategory(this.categoryForm);
    
    request.subscribe({
      next: () => { this.loadCategories(); this.closeModal(); },
      error: (err) => console.error('Error saving category:', err)
    });
  }

  deleteCategory(cat: any) {
    if (cat.is_active) {
      this.confirmTitle = 'Không thể xóa';
      this.confirmMessage = 'Danh mục đang hiển thị. Hãy chuyển sang trạng thái ẨN trước.';
      this.confirmActionType = 'warning';
      this.showConfirmModal = true;
      return;
    }
    this.pendingCategoryId = cat.category_id;
    this.confirmTitle = 'Xác nhận Xóa';
    this.confirmMessage = 'Bạn có chắc chắn muốn xóa danh mục này?';
    this.confirmActionType = 'delete';
    this.showConfirmModal = true;
  }

  restoreCategory(id: number) {
    this.pendingCategoryId = id;
    this.confirmTitle = 'Xác nhận Khôi phục';
    this.confirmMessage = 'Khôi phục danh mục này?';
    this.confirmActionType = 'restore';
    this.showConfirmModal = true;
  }

  hardDeleteCategory(id: number) {
    this.pendingCategoryId = id;
    this.confirmTitle = 'CẢNH BÁO NGUY HIỂM';
    this.confirmMessage = 'Xóa vĩnh viễn không thể hoàn tác!';
    this.confirmActionType = 'hardDelete';
    this.showConfirmModal = true;
  }

  onConfirm() {
    if (!this.pendingCategoryId || !this.confirmActionType) return;
    this.isLoading = true;

    const handleApiError = (err: any) => {
      this.isLoading = false;
      if (err.status === 400) {
        this.confirmTitle = 'Lỗi không thể thực hiện';
        this.confirmMessage = err.error?.detail || 'Dữ liệu đang được sử dụng, không thể thay đổi.';
        this.confirmActionType = 'warning';
        this.cdr.detectChanges(); 
      } else {
        this.closeConfirmModal();
        alert('Có lỗi hệ thống: ' + (err.message || 'Unknown error'));
      }
    };

    let apiCall;
    if (this.confirmActionType === 'delete') apiCall = this.adminService.deleteCategory(this.pendingCategoryId);
    else if (this.confirmActionType === 'restore') apiCall = this.adminService.restoreCategory(this.pendingCategoryId);
    else apiCall = this.adminService.hardDeleteCategory(this.pendingCategoryId);

    apiCall.subscribe({
      next: () => { this.loadCategories(); this.closeConfirmModal(); },
      error: handleApiError
    });
  }

  closeConfirmModal() {
    this.showConfirmModal = false;
    this.confirmActionType = null;
    this.pendingCategoryId = null;
  }
}