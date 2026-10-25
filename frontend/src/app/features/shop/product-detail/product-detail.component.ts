import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule, ActivatedRoute, Router } from '@angular/router';
import { Category, Product, ProductImage } from '../../../core/models';
import { environment } from '../../../../environments/environment';
import { ProductService } from '../../../shared/services/product.service';
import { CartService } from '../../../core/services/cart.service';
import { UIService } from '../../../core/services/ui.service';
import { AuthService } from '../../../core/services/auth.service';
import { CategoryService } from '../../../shared/services/category.service';
declare var bootstrap: any;

@Component({
  selector: 'app-product-detail',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './product-detail.component.html',
  styleUrls: ['./product-detail.component.scss']
})
export class ProductDetailComponent implements OnInit {
  product: any | null = null;
  primaryImage: ProductImage | null = null;
  secondaryImages: ProductImage[] = [];
  imageBaseUrl = environment.imageBaseUrl;
  categories: Category[] = [];
  
  constructor(
    private route: ActivatedRoute,
    private productService: ProductService,
    public cartService: CartService,
    private uiService: UIService,
    private cdr: ChangeDetectorRef,
    private authService: AuthService,
    private categoryService: CategoryService,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.categoryService.getCategories().subscribe(cats => this.categories = cats);
    this.route.params.subscribe(params => {
      const id = +params['id'];
      if (id) {
        this.loadProduct(id);
      }
    });
  }

  getCategoryName(id: number): string {
    const cat = this.categories.find(c => c.category_id === id);
    return cat ? cat.name : 'Đang tải...';
  }

  private loadProduct(id: number): void {
    this.productService.getProduct(id).subscribe({
      next: (product) => {
        this.product = product;
        this.setImages();
        this.cdr.detectChanges();
      },
      error: (error) => {
        console.error('Error loading product details:', error);
        this.uiService.showError('Không thể tải thông tin sản phẩm.');
        this.cdr.detectChanges();
      }

    });
  }
  
  private setImages(): void {
    if (this.product?.product_images) {
      this.primaryImage = this.product.product_images.find((img: any) => img.is_primary) || null;
      this.secondaryImages = this.product.product_images.filter((img: any) => !img.is_primary);
    }
  }

  getFullImageUrl(imageUrl: string): string {
    if (!imageUrl) return 'data:image/svg+xml;charset=UTF-8,%3Csvg xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22 width%3D%22600%22 height%3D%22600%22 viewBox%3D%220 0 600 600%22%3E%3Crect width%3D%22600%22 height%3D%22600%22 fill%3D%22%23e9ecef%22%2F%3E%3Ctext x%3D%22300%22 y%3D%22285%22 font-family%3D%22Arial%2Csans-serif%22 font-size%3D%2248%22 fill%3D%22%236c757d%22 text-anchor%3D%22middle%22%3E%F0%9F%96%BC%3C%2Ftext%3E%3Ctext x%3D%22300%22 y%3D%22335%22 font-family%3D%22Arial%2Csans-serif%22 font-size%3D%2220%22 fill%3D%22%236c757d%22 text-anchor%3D%22middle%22%3EKh%C3%B4ng c%C3%B3 h%C3%ACnh%3C%2Ftext%3E%3C%2Fsvg%3E';
    const baseUrl = this.imageBaseUrl.replace(/\/$/, '');
    const path = imageUrl.startsWith('/') ? imageUrl : `/${imageUrl}`;
    return `${baseUrl}${path}`;
  }

  setPrimaryImage(image: ProductImage): void {
    this.primaryImage = image;
  }

  reportingType: 'product' | 'review' | null = null;
  reportingId: number | null = null;
  reportCategory: string = '';
  reportReason: string = '';
  couponCode: string = '';

  applyCoupon(): void {
    if (!this.couponCode.trim()) {
      this.uiService.showError('Vui lòng nhập mã giảm giá!');
      return;
    }
    this.uiService.showModal({
      title: 'Mã giảm giá',
      message: `Đang kiểm tra mã: ${this.couponCode}. Tính năng này sẽ sớm ra mắt!`,
      type: 'info'
    });
  }
  selectedVoucher: string = '';
  userRating: number = 5;
  commentText: string = '';
  visibleReviewCount: number = 5;
  
  onVoucherSelect() {
    this.couponCode = this.selectedVoucher;
  }

  loadMoreReviews() {
    this.visibleReviewCount += 5;
  }

  submitReview() {
    if (!this.authService.isLoggedIn()) {
        const modalElement = document.getElementById('loginModal');
        if (modalElement) {
            const modal = (window as any).bootstrap.Modal.getOrCreateInstance(modalElement);
            modal.show();
        }
        return;
    }
    if (!this.commentText.trim()) {
      this.uiService.showError('Vui lòng nhập nội dung đánh giá!');
      return;
    }

    if (!this.product) return;

    this.productService.submitReview(this.product.product_id, {
        rating: this.userRating,
        content: this.commentText
    }).subscribe({
        next: () => {
            this.uiService.showSuccess('Cảm ơn bạn đã đánh giá!');
            this.commentText = '';
            this.loadProduct(this.product.product_id);
        },
        error: (err) => {
            this.uiService.showError('Lỗi khi gửi đánh giá: ' + (err.error?.detail || ''));
        }
    });
  }

  confirmReport() {
    this.submitReport();
  }

  reportProduct(): void {
    if (!this.authService.isLoggedIn()) {
        const modalElement = document.getElementById('loginModal');
        if (modalElement) {
            const modal = (window as any).bootstrap.Modal.getOrCreateInstance(modalElement);
            modal.show();
        }
        return;
    }
    this.reportingType = 'product';
    this.reportingId = this.product?.product_id || null;
    this.reportCategory = '';
    this.reportReason = '';
    const modalElement = document.getElementById('reportModal');
    if (modalElement) {
      const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
      modal.show();
    }
  }

  reportReview(reviewId: number): void {
    if (!this.authService.isLoggedIn()) {
        const modalElement = document.getElementById('loginModal');
        if (modalElement) {
            const modal = (window as any).bootstrap.Modal.getOrCreateInstance(modalElement);
            modal.show();
        }
        return;
    }
    this.reportingType = 'review';
    this.reportingId = reviewId;
    this.reportCategory = '';
    this.reportReason = '';
    const modalElement = document.getElementById('reportModal');
    if (modalElement) {
      const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
      modal.show();
    }
  }

  submitReport(): void {
    if (!this.reportCategory) {
      this.uiService.showError('Vui lòng chọn lý do báo cáo!');
      return;
    }

    if (!this.product) return;

    let reportContent = `[Báo cáo ${this.reportingType === 'product' ? 'Sản phẩm' : 'Đánh giá #' + this.reportingId}] Lý do: ${this.reportCategory} - ${this.reportReason}`;

    this.productService.submitReview(this.product.product_id, {
        rating: 0,
        content: reportContent
    }).subscribe({
        next: () => {
            this.uiService.showSuccess('Báo cáo của bạn đã được gửi tới đội ngũ quản trị.');
            this.reportCategory = '';
            this.reportReason = '';
            const reportModalEl = document.getElementById('reportModal');
            if (reportModalEl) {
                const m = bootstrap.Modal.getOrCreateInstance(reportModalEl);
                m.hide();
            }
        },
        error: (err) => {
            this.uiService.showError('Lỗi khi gửi báo cáo: ' + (err.error?.detail || ''));
        }
    });
  }

  getValidReviews(): any[] {
    if (!this.product || !this.product.reviews) return [];
    return this.product.reviews.filter((r: any) => r.rating > 0);
  }

  addToCart(): void {
    if (!this.product) return;

    // 1. Kiểm tra đăng nhập (Giữ nguyên logic của bạn)
    if (!this.authService.isLoggedIn()) {
        const modalElement = document.getElementById('loginModal');
        if (modalElement) {
            const modal = (window as any).bootstrap.Modal.getOrCreateInstance(modalElement);
            modal.show();
        }
        return;
    }
    this.cartService.addToCart(this.product);
    this.router.navigate(['/customer/cart']); 
  }

  canAddToCart(): boolean {
    if (!this.product) return false;
    const inCart = this.cartService.getProductQuantityInCart(this.product.product_id);
    return this.product.quantity > 0 && inCart < this.product.quantity;
  }
}
