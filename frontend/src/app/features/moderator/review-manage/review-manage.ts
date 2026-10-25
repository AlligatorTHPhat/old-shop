import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ProductService } from '../../../shared/services/product.service';
import { ModeratorService } from '../../../shared/services/moderator.service';
import { UIService } from '../../../core/services/ui.service';

declare var bootstrap: any;

@Component({
  selector: 'app-review-manage',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule],
  templateUrl: './review-manage.html',
  styleUrl: './review-manage.scss'
})
export class ReviewManageComponent implements OnInit {
  reportedReviews: any[] = [];
  isLoading = false;

  // Modal State
  selectedReview: any = null;
  actionType: 'reject_product' | 'ban_user' | null = null;
  actionReason: string = '';
  isActionLoading = false;

  constructor(
    private productService: ProductService,
    private moderatorService: ModeratorService,
    private uiService: UIService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadReportedReviews();
  }

  loadReportedReviews() {
    this.isLoading = true;
    this.productService.getReportedReviews().subscribe({
      next: (data: any) => {
        this.reportedReviews = data;
        this.isLoading = false;
        this.cdr.detectChanges();
      },
      error: (err: any) => {
        this.uiService.showError('Không thể tải danh sách báo cáo');
        this.isLoading = false;
        this.cdr.detectChanges();
      }
    });
  }

  openActionModal(review: any, type: 'reject_product' | 'ban_user') {
    this.selectedReview = review;
    this.actionType = type;
    this.actionReason = '';
    const modalEl = document.getElementById('actionModal');
    if (modalEl) {
      new bootstrap.Modal(modalEl).show();
    }
  }

  closeActionModal() {
    const modalEl = document.getElementById('actionModal');
    const modal = bootstrap.Modal.getInstance(modalEl);
    if (modal) modal.hide();
  }

  confirmAction() {
    if (!this.actionReason.trim()) {
      this.uiService.showError('Vui lòng nhập lý do!');
      return;
    }

    this.isActionLoading = true;
    if (this.actionType === 'reject_product') {
      this.productService.updateProductStatus(this.selectedReview.product_id, 2, this.actionReason).subscribe({
        next: () => {
          this.uiService.showSuccess('Đã từ chối sản phẩm');
          this.closeActionModal();
          this.loadReportedReviews();
          this.isActionLoading = false;
        },
        error: (err: any) => {
          this.uiService.showError('Lỗi khi từ chối sản phẩm: ' + (err.error?.detail || ''));
          this.isActionLoading = false;
        }
      });
    } else if (this.actionType === 'ban_user') {
      const sellerId = this.selectedReview.product?.seller_id;
      if (!sellerId) {
        this.uiService.showError('Không tìm thấy thông tin người bán. Vui lòng xem chi tiết sản phẩm.');
        this.isActionLoading = false;
        return;
      }
      this.moderatorService.banUser(sellerId, this.actionReason).subscribe({
        next: () => {
          this.uiService.showSuccess('Đã khóa tài khoản người bán');
          this.closeActionModal();
          this.isActionLoading = false;
        },
        error: (err: any) => {
          this.uiService.showError('Lỗi khi khóa tài khoản: ' + (err.error?.detail || ''));
          this.isActionLoading = false;
        }
      });
    }
  }
}
