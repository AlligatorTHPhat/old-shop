import { Component, OnInit, OnDestroy, ChangeDetectorRef, isDevMode } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { ModerationProduct, ProductService } from '../../../shared/services/product.service';
import { ProductVideoComponent } from '../../../shared/components/product-video/product-video';
import { environment } from '../../../../environments/environment';

declare var bootstrap: any

@Component({
  selector: 'app-moderator-product-manage',
  standalone: true,
  imports: [CommonModule, FormsModule, ProductVideoComponent],
  templateUrl: './product-manage.html',
  styleUrl: './product-manage.scss'
})
export class ModeratorProductManageComponent implements OnInit, OnDestroy {
  products: ModerationProduct[] = [];
  totalProducts = 0;
  loadError: string | null = null;
  searchTerm: string = '';
  isLoading = false;
  actionLoading = false;
  message: string | null = null;
  activeTab: 'pending' | 'approved' | 'rejected' = 'pending';
  selectedProduct: any = null;
  targetStatus: number | null = null;
  rejectionReason: string = '';
  isViewMode: boolean = false;
  
  currentPage: number = 1;
  pageSize: number = 5;
  readonly Math = Math;
  private listRequest?: Subscription;
  private actionRequest?: Subscription;
  private searchTimer?: ReturnType<typeof setTimeout>;
  private messageTimer?: ReturnType<typeof setTimeout>;

  constructor(
    private cdr: ChangeDetectorRef,
    private productService: ProductService
  ) {}

  ngOnInit(): void {
    this.loadProducts();
  }

  ngOnDestroy(): void {
    this.listRequest?.unsubscribe();
    this.actionRequest?.unsubscribe();
    clearTimeout(this.searchTimer);
    clearTimeout(this.messageTimer);
  }

  get totalPages(): number {
    return Math.ceil(this.totalProducts / this.pageSize) || 1;
  }

  // Phân trang thông minh: Hiển thị các trang lân cận
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
    if (page >= 1 && page <= this.totalPages && page !== this.currentPage) {
      this.currentPage = page;
      this.loadProducts();
    }
  }

  getVideoUrl(product: any): string | null {
    return product.video_url ? this.getFullUrl(product.video_url) : null;
  }

  loadProducts(): void {
    clearTimeout(this.searchTimer);
    this.listRequest?.unsubscribe();
    this.isLoading = true;
    this.loadError = null;
    const statusMap = { 'pending': 0, 'approved': 1, 'rejected': 2 };
    const status = statusMap[this.activeTab];
    
    this.listRequest = this.productService.getModerationPage(
      status, (this.currentPage - 1) * this.pageSize, this.pageSize, this.searchTerm
    ).subscribe({
      next: (data) => {
        this.totalProducts = data.total;
        // Moderating the last item may remove the entire current page.
        if (this.currentPage > this.totalPages) {
          this.currentPage = this.totalPages;
          this.loadProducts();
          return;
        }
        this.products = data.items.map(p => ({
          ...p,
          product_name: p.title || 'Sản phẩm không tên'
        }));
        this.isLoading = false;
        this.cdr.detectChanges();
      },
      error: () => {
        this.isLoading = false;
        this.products = [];
        this.totalProducts = 0;
        this.loadError = 'Không tải được danh sách sản phẩm. Vui lòng thử lại.';
        this.cdr.detectChanges();
      }
    });
  }

  filterProducts() {
    this.currentPage = 1;
    clearTimeout(this.searchTimer);
    this.listRequest?.unsubscribe();
    this.loadError = null;
    this.isLoading = true;
    this.searchTimer = setTimeout(() => this.loadProducts(), 300);
  }

  onSearchChange(term: string) {
    this.searchTerm = term;
    this.filterProducts();
  }

  refreshProducts() {
    this.currentPage = 1;
    this.loadProducts();
  }

  selectTab(tab: 'pending' | 'approved' | 'rejected'): void {
    this.activeTab = tab;
    this.currentPage = 1;
    this.searchTerm = '';
    this.loadProducts();
  }

  openModal(product: any, status: 'approved' | 'rejected', viewMode: boolean = false) {
    this.selectedProduct = product;
    this.isViewMode = viewMode;
    this.targetStatus = status === 'approved' ? 1 : 2;
    if (viewMode) {
      this.rejectionReason = product.reject_reason || 'Không có lý do.';
    } else {
      this.rejectionReason = '';
    }
    new bootstrap.Modal(document.getElementById('reasonModal')).show();
  }

  showFullReason(product: any) {
    this.openModal(product, 'rejected', true);
  }

  confirmAction() {
    if (this.actionLoading) return;
    if (this.targetStatus === 2 && !this.rejectionReason.trim()) {
      alert('Vui lòng nhập lý do!');
      return;
    }
    
    this.actionLoading = true;
    this.actionRequest = this.productService.updateProductStatus(
      this.selectedProduct.product_id, 
      this.targetStatus!, 
      this.rejectionReason
    ).subscribe({
      next: () => {
        this.actionLoading = false;
        this.closeModal();
        this.loadProducts();
        this.message = "Thao tác thành công!";
        clearTimeout(this.messageTimer);
        this.messageTimer = setTimeout(() => {
          this.message = null;
          this.cdr.detectChanges();
        }, 3000);
      },
      error: (err) => {
        this.actionLoading = false;
        alert("Lỗi: " + (err.error?.detail || "Không thể cập nhật"));
        this.cdr.detectChanges();
      }
    });
  }

  viewProductDetail(product: any) {
    this.selectedProduct = product;
    const modalEl = document.getElementById('productDetailModal');
    if (modalEl) {
      const modal = new bootstrap.Modal(modalEl);
      modal.show();
    }
  }

  closeDetailModal() {
    const modalEl = document.getElementById('productDetailModal');
    const modal = bootstrap.Modal.getInstance(modalEl);
    if (modal) modal.hide();
  }

  getFullUrl(url: string): string {
    if (!url) return 'assets/placeholder.jpg';
    let baseUrl = environment.imageBaseUrl;
    if (baseUrl.startsWith('https') && isDevMode()) {
      console.warn('Using HTTPS in local, may cause ERR_SSL error');
    }
    if (url.startsWith('/')) return `${baseUrl}${url}`;
    return url;
  }

  getPrimaryImage(product: any): string {
    const primary = product.product_images?.find((img: any) => img.is_primary);
    return this.getFullUrl(primary ? primary.image_url : (product.product_images?.[0]?.image_url || ''));
  }

  quickAction(status: 'approved' | 'rejected') {
    const modalDetail = bootstrap.Modal.getInstance(document.getElementById('productDetailModal'));
    modalDetail.hide();
    setTimeout(() => {
      this.openModal(this.selectedProduct, status);
    }, 400);
  }

  getRawVideoUrl(product: any): string {
    if (!product || !product.video_url) return '';
    if (product.video_url.includes('yout')) {
      return product.video_url;
    }
    return this.getFullUrl(product.video_url);
  }

  closeModal() {
    const modalEl = document.getElementById('reasonModal');
    const modal = bootstrap.Modal.getInstance(modalEl);
    if (modal) modal.hide();
  }
}
