import { Component, OnInit, ChangeDetectorRef, isDevMode } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ModeratorService } from '../../../shared/services/moderator.service';
import { ProductService } from '../../../shared/services/product.service';
import { CategoryService } from '../../../shared/services/category.service';
import { environment } from '../../../../environments/environment';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';

declare var bootstrap: any

@Component({
  selector: 'app-moderator-product-manage',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './product-manage.html',
  styleUrl: './product-manage.scss'
})
export class ModeratorProductManageComponent implements OnInit {
  products: any[] = [];
  allProducts: any[] = [];
  searchTerm: string = '';
  isLoading = false;
  actionLoading = false;
  message: string | null = null;
  activeTab: 'pending' | 'approved' | 'rejected' = 'pending';
  selectedProduct: any = null;
  targetStatus: number | null = null;
  rejectionReason: string = '';
  category: any[] = [];
  categoryMap: Map<number, string> = new Map();
  userMap: Map<number, string> = new Map();
  isViewMode: boolean = false;
  
  currentPage: number = 1;
  pageSize: number = 5;
Math: any;

  constructor(
    private moderatorService: ModeratorService,
    private cdr: ChangeDetectorRef,
    private productService: ProductService,
    private categoryService: CategoryService,
    private sanitizer: DomSanitizer
  ) {}

  ngOnInit(): void {
    void import('rxjs').then(rxjs => {
      rxjs.forkJoin({
        categories: this.categoryService.getCategories(),
        users: this.moderatorService.getUsers()
      }).subscribe(({ categories, users }) => {
        this.category = categories;
        users.forEach(u => this.userMap.set(u.user_id, u.username));
        this.loadProducts();
      });
    });
  }

  get paginatedProducts() {
    const start = (this.currentPage - 1) * this.pageSize;
    const end = start + this.pageSize;
    return this.products.slice(start, end);
  }

  get totalPages(): number {
    return Math.ceil(this.products.length / this.pageSize) || 1;
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
    if (page >= 1 && page <= this.totalPages) {
      this.currentPage = page;
    }
  }

  getVideoUrl(product: any): string | null {
    return product.video_url ? this.getFullUrl(product.video_url) : null;
  }

  loadProducts(): void {
    this.isLoading = true;
    const statusMap = { 'pending': 0, 'approved': 1, 'rejected': 2 };
    const status = statusMap[this.activeTab];
    
    this.productService.getProductsByStatus(status).subscribe({
      next: (data) => {
        this.category.forEach(c => this.categoryMap.set(c.category_id, c.name));
        this.allProducts = (data || []).map(p => ({
          ...p,
          category_name: this.categoryMap.get(p.category_id) || 'Chưa phân loại',
          seller_name: this.userMap.get(p.seller_id) || 'User #' + p.seller_id,
          product_name: p.title || 'Sản phẩm không tên'
        }));
        this.filterProducts();
        this.isLoading = false;
        this.cdr.detectChanges();
      },
      error: () => {
        this.isLoading = false;
      }
    });
  }

  filterProducts() {
    if (!this.searchTerm.trim()) {
      this.products = [...this.allProducts];
    } else {
      const term = this.searchTerm.toLowerCase().trim();
      this.products = this.allProducts.filter(p => 
        p.product_name.toLowerCase().includes(term) || 
        p.seller_name.toLowerCase().includes(term) ||
        p.category_name.toLowerCase().includes(term)
      );
    }
    this.currentPage = 1;
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
    if (this.targetStatus === 2 && !this.rejectionReason.trim()) {
      alert('Vui lòng nhập lý do!');
      return;
    }
    
    this.productService.updateProductStatus(
      this.selectedProduct.product_id, 
      this.targetStatus!, 
      this.rejectionReason
    ).subscribe({
      next: () => {
        this.closeModal();
        this.loadProducts();
        this.message = "Thao tác thành công!";
        setTimeout(() => this.message = null, 3000);
      },
      error: (err) => {
        alert("Lỗi: " + (err.error?.detail || "Không thể cập nhật"));
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