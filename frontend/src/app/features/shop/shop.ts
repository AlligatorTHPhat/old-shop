import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule, Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { ProductService } from '../../shared/services/product.service';
import { CategoryService } from '../../shared/services/category.service';
import { Product, Category } from '../../core/models';
import { environment } from '../../../environments/environment';
import { CartService } from '../../core/services/cart.service';
import { UIService } from '../../core/services/ui.service';
import { forkJoin } from 'rxjs';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-shop',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './shop.html',
  styleUrls: ['./shop.scss']
})
export class ShopComponent implements OnInit {
  allProducts: Product[] = [];
  products: Product[] = [];
  filteredProducts: Product[] = [];
  categories: Category[] = [];
  categoryCounts: Record<number, number> = {};

  currentPage = 1;
  totalPages = 1;
  itemsPerPage = 9;
  loading = false;
  searchQuery = '';
  selectedCategoryId: number | null = null;
  priceMin: number | null = null;
  priceMax: number | null = null;

  constructor(
    private productService: ProductService,
    private categoryService: CategoryService,
    private cartService: CartService,
    private authService: AuthService,
    private cdr: ChangeDetectorRef,
    private router: Router,
    private uiService: UIService
  ) {
    // Reload data if navigating back to /shop (handles clicking header link again)
    this.router.events.pipe(
      filter(event => event instanceof NavigationEnd),
      filter(event => (event as NavigationEnd).urlAfterRedirects === '/shop')
    ).subscribe(() => {
      this.initialLoad();
    });
  }

  ngOnInit() {
    this.initialLoad();
  }

  private initialLoad() {
    this.loading = true;
    forkJoin({
      categories: this.categoryService.getCategories(),
      products: this.productService.getProducts({ skip: 0, limit: 1000, sort_by: 'created_at' })
    }).subscribe({
      next: (result) => {
        this.categories = result.categories;
        this.allProducts = result.products.filter(p => {
          const cat = this.categories.find(c => c.category_id === p.category_id);
          return cat && !cat.is_deleted;
        });
        this.computeCategoryCounts();
        this.applyFilters();
        this.loading = false;
        this.cdr.detectChanges();
      },
      error: (error) => {
        console.error('Lỗi tải dữ liệu:', error);
        this.loading = false;
        this.uiService.showError('Không thể tải dữ liệu cửa hàng.');
      }
    });
  }

  loadCategories() {
    this.categoryService.getCategories().subscribe({
      next: (categories) => {
        this.categories = categories;
        this.cdr.detectChanges();
      },
      error: (error) => {
        console.error('Error loading categories:', error);
        this.uiService.showError('Không thể tải danh sách danh mục.');
      }
    });
  }

  loadProducts() {
    this.loading = true;
    // Load all approved products to support filtering and counts
    this.productService.getProducts({ skip: 0, limit: 1000, sort_by: 'created_at' }).subscribe({
      next: (products) => {
        this.allProducts = products;
        this.computeCategoryCounts();
        this.applyFilters();
        this.loading = false;
        setTimeout(() => {
          this.cdr.detectChanges();
        });
        this.allProducts = products.filter(p => {
          const cat = this.categories.find(c => c.category_id === p.category_id);
          return cat && !(cat as any).is_deleted;
        });
      },
      error: (error) => {
        console.error('Error loading products:', error);
        this.loading = false;
        this.uiService.showError('Không thể tải danh sách sản phẩm.');
        this.cdr.detectChanges();
      }
    });
  }

  computeCategoryCounts() {
    this.categoryCounts = {};
    for (const product of this.allProducts) {
      if (!this.categoryCounts[product.category_id]) {
        this.categoryCounts[product.category_id] = 0;
      }
      this.categoryCounts[product.category_id] += 1;
    }
  }

  applyFilters() {
    const min = this.priceMin ?? 0;
    const max = this.priceMax ?? Number.MAX_SAFE_INTEGER;

    this.filteredProducts = this.allProducts.filter((product) => {
      const matchesSearch = this.searchQuery
        ? product.title.toLowerCase().includes(this.searchQuery.toLowerCase()) ||
        (product.description || '').toLowerCase().includes(this.searchQuery.toLowerCase())
        : true;

      const matchesCategory = this.selectedCategoryId
        ? product.category_id === this.selectedCategoryId
        : true;

      const price = Number(product.price);
      const matchesPrice = price >= min && price <= max;

      return matchesSearch && matchesCategory && matchesPrice;
    });

    this.totalPages = Math.max(1, Math.ceil(this.filteredProducts.length / this.itemsPerPage));
    this.currentPage = 1;
    this.updatePageProducts();
  }

  updatePageProducts() {
    const start = (this.currentPage - 1) * this.itemsPerPage;
    const end = start + this.itemsPerPage;
    this.products = this.filteredProducts.slice(start, end);
  }

  onSearch() {
    this.applyFilters();
  }

  onCategoryChange(categoryId: number | null = null) {
    this.selectedCategoryId = categoryId;
    this.applyFilters();
  }

  onPriceFilter() {
    this.applyFilters();
  }

  onPageChange(page: number) {
    if (page >= 1 && page <= this.totalPages) {
      this.currentPage = page;
      this.updatePageProducts();
    }
  }

  getPages(): number[] {
    const pages: number[] = [];
    const start = Math.max(1, this.currentPage - 2);
    const end = Math.min(this.totalPages, this.currentPage + 2);
    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    return pages;
  }

  getPrimaryImage(product: any): string {
    let path = '';
    // API trả về field "product_images" (không phải "images")
    const images = product.product_images || product.images || [];
    if (images.length > 0) {
      // Ưu tiên ảnh is_primary=true, fallback về ảnh đầu tiên
      const primary = images.find((img: any) => img.is_primary) || images[0];
      path = primary.image_url || '';
    } else {
      path = product.image || '';
    }

    // Nếu path không phải URL đầy đủ thì nối với imageBaseUrl từ environment
    if (path && !path.startsWith('http')) {
      const base = environment.imageBaseUrl.replace(/\/$/, '');
      return `${base}${path.startsWith('/') ? '' : '/'}${path}`;
    }
    return path;
  }


  formatPrice(value: number | string): string {
    const price = typeof value === 'string' ? Number(value) : value;
    if (!Number.isFinite(price)) {
      return '0 ₫';
    }
    return price.toLocaleString('vi-VN', { style: 'currency', currency: 'VND' });
  }

  addToCart(product: Product) {
    if (!this.authService.isLoggedIn()) {
      const modalElement = document.getElementById('loginModal');
      if (modalElement) {
        const modal = (window as any).bootstrap.Modal.getOrCreateInstance(modalElement);
        modal.show();
      }
      return;
    }
    setTimeout(() => {
      this.cartService.addToCart(product);
    });
  }
}