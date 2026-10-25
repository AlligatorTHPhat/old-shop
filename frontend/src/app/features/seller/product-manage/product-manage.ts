import { Component, OnInit, inject, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { FormsModule, ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { environment } from '../../../../environments/environment';
import { UIService } from '../../../core/services/ui.service';
import { mediaUrl } from '../../../core/utils/media-url';

declare var bootstrap: any;

@Component({
  selector: 'app-product-manage',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule],
  templateUrl: './product-manage.html',
  styleUrl: './product-manage.scss'
})
export class ProductManageComponent implements OnInit {
  private http = inject(HttpClient);
  private fb = inject(FormBuilder);
  private uiService = inject(UIService);
  private cdr = inject(ChangeDetectorRef);
  private apiUrl = environment.apiUrl;

  Math = Math;

  products: any[] = [];
  categories: any[] = [];
  productForm!: FormGroup;
  selectedFiles: File[] = [];
  
  currentStatus = 0;
  currentPage = 1;
  pageSize = 5;
  totalItems: number = 0;

  showModal = false;
  isEditMode = false;
  editingProductId: number | null = null;
  isSubmitting = false;
  isUpdatingStatus = false;

  showConfirmModal = false;
  confirmProduct: any = null;
  confirmTargetStatus: number = 0;

  showRejectModal = false;
  currentRejectReason = '';

  ngOnInit() {
    this.initForm();
    this.loadProducts();
    this.loadCategories();
  }

  initForm() {
    this.productForm = this.fb.group({
      title: ['', [Validators.required, Validators.maxLength(255)]],
      description: [''],
      category_id: ['', Validators.required],
      price: ['', [Validators.required, Validators.min(1)]],
      quantity: ['', [Validators.required, Validators.min(1)]],
      video_url: [''],
      weight_grams: [''],
      d: [''], r: [''], c: [''],
      condition_rating: ['8', [Validators.required, Validators.min(1), Validators.max(10)]],
      warranty_months: ['0', Validators.min(0)],
      transfer_method: ['1', Validators.required]
    });
  }

  onNumericInput(event: any, controlName: string) {
    let rawValue = event.target.value.replace(/[^0-9]/g, '');
    this.productForm.patchValue({ [controlName]: rawValue }, { emitEvent: false });
    event.target.value = rawValue;
  }

  allowOnlyNumbers(event: KeyboardEvent): boolean {
    const charCode = (event.which) ? event.which : event.keyCode;
    if (charCode > 31 && (charCode < 48 || charCode > 57)) {
      event.preventDefault();
      return false;
    }
    return true;
  }

  onPriceInput(event: any) {
    const rawValue = event.target.value.replace(/\D/g, '');
    this.productForm.patchValue({ price: rawValue }, { emitEvent: false });
    event.target.value = rawValue ? parseInt(rawValue, 10).toLocaleString('vi-VN') : '';
  }

  get displayPrice(): string {
    const price = this.productForm.get('price')?.value;
    return price ? parseInt(price, 10).toLocaleString('vi-VN') : '';
  }

  loadProducts() {
    this.http.get<any[]>(`${this.apiUrl}/products/seller/my-products`).subscribe({
      next: (data) => {
        this.products = data;
        this.updateTotal();
        this.cdr.detectChanges();
      }
    });
  }

  loadCategories() {
    this.http.get<any[]>(`${this.apiUrl}/categories`).subscribe({
      next: (data) => {
        this.categories = data;
        this.cdr.detectChanges();
      }
    });
  }

  getPrimaryImage(product: any): string {
    const primaryImage = product.product_images?.find((img: any) => img.is_primary);
    const raw = primaryImage ? primaryImage.image_url : (product.product_images?.[0]?.image_url || '');
    return mediaUrl(raw, 'assets/placeholder.jpg');
  }

  get filteredProducts() {
    return this.products.filter(p => p.status === this.currentStatus);
  }

  get pagedProducts() {
    const start = (this.currentPage - 1) * this.pageSize;
    return this.filteredProducts.slice(start, start + this.pageSize);
  }

  get totalPages(): number {
    return Math.ceil(this.filteredProducts.length / this.pageSize) || 1;
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

  updateTotal() {
    this.totalItems = this.filteredProducts.length;
  }

  switchTab(s: number) {
    this.currentStatus = s;
    this.currentPage = 1;
    this.updateTotal();
    this.cdr.detectChanges();
  }

  getStatusBadge(status: number): { class: string, label: string } {
    switch (status) {
      case 0: return { class: 'custom-badge badge-warning', label: 'CHỜ DUYỆT' };
      case 1: return { class: 'custom-badge badge-success', label: 'ĐÃ DUYỆT' };
      case 2: return { class: 'custom-badge badge-danger', label: 'TỪ CHỐI' };
      case 3: return { class: 'custom-badge badge-secondary', label: 'ĐÃ THU HỒI' };
      default: return { class: 'custom-badge badge-secondary', label: 'KHÔNG RÕ' };
    }
  }

  viewRejectReason(product: any) {
    this.currentRejectReason = product.reject_reason || 'Quản trị viên không cung cấp lý do cụ thể.';
    this.showRejectModal = true;
  }

  closeRejectModal() {
    this.showRejectModal = false;
    this.currentRejectReason = '';
  }

  openModal(p?: any) {
    this.isEditMode = !!p;
    this.editingProductId = p ? p.product_id : null;
    this.isSubmitting = false;

    const fileInput = document.getElementById('fileUpload') as HTMLInputElement;
    if (fileInput) fileInput.value = ''; 

    if (p) {
      const patchData = { ...p };
      if (p.dimensions && typeof p.dimensions === 'string' && p.dimensions.includes('x')) {
        const parts = p.dimensions.split('x');
        patchData.d = parts[0];
        patchData.r = parts[1];
        patchData.c = parts[2];
      }
      this.productForm.patchValue(patchData);
    } else {
      this.productForm.reset({ condition_rating: '8', warranty_months: '0', transfer_method: '1' });
      this.selectedFiles = [];
    }
    this.showModal = true;
  }

  onFileSelected(event: any) {
    if (event.target.files.length > 0) this.selectedFiles = Array.from(event.target.files);
  }

  onSubmit() {
    if (this.productForm.invalid) {
      this.productForm.markAllAsTouched();
      this.uiService.showError('Vui lòng điền đầy đủ các thông tin bắt buộc.', 'Thiếu thông tin');
      return;
    }
    if (!this.isEditMode && this.selectedFiles.length === 0) {
      this.uiService.showError('Vui lòng chọn ít nhất 1 hình ảnh.', 'Thiếu hình ảnh');
      return;
    }

    this.isSubmitting = true;
    const formData = new FormData();
    const formValue = this.productForm.value;
    const dimensions = `${formValue.d || 0}x${formValue.r || 0}x${formValue.c || 0}`;
    
    Object.keys(formValue).forEach(key => {
      if (!['d', 'r', 'c'].includes(key)) formData.append(key, formValue[key]);
    });
    formData.append('dimensions', dimensions);
    this.selectedFiles.forEach(file => formData.append('files', file));

    const obs = this.isEditMode 
      ? this.http.put(`${this.apiUrl}/products/${this.editingProductId}`, { ...formValue, dimensions })
      : this.http.post(`${this.apiUrl}/products`, formData, { responseType: 'text' }); 

    obs.subscribe({
      next: () => {
        // Lược bỏ Modal Success, chỉ Đóng form và Cập nhật bảng
        this.isSubmitting = false;
        this.closeModal();
        this.loadProducts();
      },
      error: (err) => {
        this.isSubmitting = false;
        // Bắt lỗi Parse Json từ Backend
        if (err.status === 200 || err.status === 201) {
          this.closeModal();
          this.loadProducts();
        } else {
          // Chỉ mở Error Alert nếu thực sự bị lỗi 400, 500
          this.uiService.showError(err.error?.message || err.message || 'Có lỗi xảy ra từ máy chủ', 'Lỗi Server');
          this.cdr.detectChanges();
        }
      }
    });
  }

  openConfirmModal(product: any, newStatus: number) {
    this.confirmProduct = product;
    this.confirmTargetStatus = newStatus;
    this.showConfirmModal = true;
  }

  closeConfirmModal() {
    this.showConfirmModal = false;
    this.confirmProduct = null;
  }

  confirmUpdateStatus() {
    if (!this.confirmProduct || this.isUpdatingStatus) return;
    this.isUpdatingStatus = true;
    
    this.http.patch(`${this.apiUrl}/products/${this.confirmProduct.product_id}/status`, { new_status: this.confirmTargetStatus }).subscribe({
      next: () => {
        this.isUpdatingStatus = false;
        this.closeConfirmModal();
        this.loadProducts();
      },
      error: () => {
        this.isUpdatingStatus = false;
        this.closeConfirmModal();
        this.uiService.showError('Không thể cập nhật lúc này', 'Lỗi');
        this.cdr.detectChanges();
      }
    });
  }

  closeModal() {
    this.showModal = false;
    this.isSubmitting = false;
  }
}