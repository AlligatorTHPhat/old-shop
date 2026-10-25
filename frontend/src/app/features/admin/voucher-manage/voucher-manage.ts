// voucher-manage.component.ts
import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AdminService } from '../../../shared/services/admin.service';
import { UIService } from '../../../core/services/ui.service';

@Component({
  selector: 'app-voucher-manage',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './voucher-manage.html',
  styleUrl: './voucher-manage.scss'
})
export class VoucherManageComponent implements OnInit {
  vouchers: any[] = [];
  allVouchers: any[] = [];
  isLoading = false;
  showModal = false;
  editingVoucher: any = null;
  activeTab: 'active' | 'trash' = 'active';
  searchTerm: string = '';
  
  // Biến hiển thị cho định dạng tiền tệ
  displayDiscountValue: string = '';
  displayMinOrder: string = '';

  // Confirm Modal Variables
  showConfirmModal = false;
  confirmTitle = '';
  confirmMessage = '';
  confirmActionType: 'softDelete' | 'restore' | 'hardDelete' | 'warning' = 'warning';
  targetVoucherId: number | null = null;

  skip = 0;
  limit = 5;

  voucherForm = {
    code: '',
    description: '',
    discount_type: 0,
    discount_value: 0,
    max_usage: 100,
    min_order_amount: 0,
    valid_from: '',
    valid_to: '',
    is_active: true
  };

  constructor(
    private adminService: AdminService, 
    private cdr: ChangeDetectorRef,
    private uiService: UIService
  ) {}

  ngOnInit(): void { this.loadVouchers(); }

  // --- HÀM ĐỊNH DẠNG TIỀN TỆ REAL-TIME ---
  formatCurrencyInput(event: any, field: 'discount' | 'minOrder') {
    let value = event.target.value.replace(/\./g, '');
    if (isNaN(value) || value === '') value = '0';
    
    const formatted = Number(value).toLocaleString('vi-VN');
    
    if (field === 'discount') {
      this.displayDiscountValue = formatted;
      this.voucherForm.discount_value = Number(value);
    } else {
      this.displayMinOrder = formatted;
      this.voucherForm.min_order_amount = Number(value);
    }
  }

  loadVouchers() {
    this.isLoading = true;
    this.adminService.getVouchers().subscribe({
      next: (data) => {
        this.allVouchers = data;
        this.applyFilterAndTab();
        this.isLoading = false;
        this.cdr.detectChanges();
      },
      error: () => {
        this.isLoading = false;
        this.uiService.showError('Không thể tải danh sách voucher');
      }
    });
  }

  applyFilterAndTab() {
    let filtered = this.allVouchers;
    filtered = (this.activeTab === 'trash') 
      ? filtered.filter(v => v.is_deleted) 
      : filtered.filter(v => !v.is_deleted);

    if (this.searchTerm.trim()) {
      const term = this.searchTerm.toLowerCase();
      filtered = filtered.filter(v => v.code.toLowerCase().includes(term) || v.description?.toLowerCase().includes(term));
    }
    this.vouchers = filtered;
  }

  openModal(voucher: any = null) {
    this.editingVoucher = voucher;
    if (voucher) {
      this.voucherForm = { 
        ...voucher,
        valid_from: voucher.valid_from.substring(0, 16),
        valid_to: voucher.valid_to.substring(0, 16)
      };
      this.displayDiscountValue = voucher.discount_value.toLocaleString('vi-VN');
      this.displayMinOrder = voucher.min_order_amount.toLocaleString('vi-VN');
    } else {
      this.resetForm();
    }
    this.showModal = true;
  }

  resetForm() {
    this.voucherForm = {
      code: '',
      description: '',
      discount_type: 0,
      discount_value: 0,
      max_usage: 100,
      min_order_amount: 0,
      valid_from: new Date().toISOString().substring(0, 16),
      valid_to: '',
      is_active: true
    };
    this.displayDiscountValue = '0';
    this.displayMinOrder = '0';
  }

  saveVoucher() {
    // 1. Clone dữ liệu
    const payload = { ...this.voucherForm };

    // 2. ÉP KIỂU DỮ LIỆU SỐ (Quan trọng: Tránh lỗi 422 do input gửi string)
    payload.discount_value = Number(this.voucherForm.discount_value);
    payload.min_order_amount = Number(this.voucherForm.min_order_amount);
    payload.max_usage = Number(this.voucherForm.max_usage);

    // 3. FORMAT NGÀY THÁNG SANG ISO STRING
    // Backend cần định dạng 2026-05-03T08:21:13.364Z
    if (payload.valid_from) payload.valid_from = new Date(payload.valid_from).toISOString();
    if (payload.valid_to) payload.valid_to = new Date(payload.valid_to).toISOString();

    const request = this.editingVoucher 
        ? this.adminService.updateVoucher(this.editingVoucher.voucher_id, payload)
        : this.adminService.createVoucher({ ...payload, code: payload.code.toUpperCase() });

    request.subscribe({
        next: () => {
        this.showModal = false;
        this.loadVouchers();
        },
        error: (err) => {
        console.error("Chi tiết lỗi API:", err);
        const msg = err.error?.detail;
        this.showErrorModal('Lỗi lưu chiến dịch', typeof msg === 'string' ? msg : 'Dữ liệu nhập vào không hợp lệ (Lỗi 422/400)');
        }
    });
  }

  showErrorModal(title: string, message: string) {
    this.confirmTitle = title;
    this.confirmMessage = message;
    this.confirmActionType = 'warning';
    this.showConfirmModal = true;
    this.cdr.detectChanges();
  }

  confirmSoftDelete(id: number) {
    this.confirmTitle = 'Xóa tạm thời';
    this.confirmMessage = 'Bạn có chắc chắn muốn đưa voucher này vào thùng rác?';
    this.confirmActionType = 'softDelete';
    this.targetVoucherId = id;
    this.showConfirmModal = true;
  }

  softDelete(id: number) {
    this.adminService.deleteVoucher(id).subscribe({
      next: () => {
        this.loadVouchers();
      },
      error: (err) => {
        this.showErrorModal('Lỗi thao tác', err.error?.detail || 'Không thể xóa tạm thời');
      }
    });
  }

  confirmRestore(id: number) {
    this.confirmTitle = 'Khôi phục voucher';
    this.confirmMessage = 'Bạn có muốn khôi phục và kích hoạt lại voucher này?';
    this.confirmActionType = 'restore';
    this.targetVoucherId = id;
    this.showConfirmModal = true;
  }

  confirmHardDelete(id: number) {
    this.confirmTitle = 'Xóa vĩnh viễn voucher';
    this.confirmMessage = 'Hành động này không thể hoàn tác. Bạn có chắc chắn muốn xóa?';
    this.confirmActionType = 'hardDelete';
    this.targetVoucherId = id;
    this.showConfirmModal = true;
  }

  closeConfirmModal() {
    this.showConfirmModal = false;
    this.targetVoucherId = null;
  }

  onConfirm() {
    if (!this.targetVoucherId) return;

    if (this.confirmActionType === 'restore') {
      this.restoreVoucher(this.targetVoucherId);
    } else if (this.confirmActionType === 'hardDelete') {
      this.hardDelete(this.targetVoucherId);
    } else if (this.confirmActionType === 'softDelete') {
      this.softDelete(this.targetVoucherId);
    }
    this.closeConfirmModal();
  }

  hardDelete(id: number) {
    this.adminService.hardDeleteVoucher(id).subscribe({
      next: () => {
        this.loadVouchers();
      },
      error: (err) => {
        this.showErrorModal('Lỗi xóa vĩnh viễn', err.error?.detail || 'Không xác định');
      }
    });
  }

  restoreVoucher(id: number) {
    const restoreData = {
        is_deleted: false,
        is_active: true
    };

    this.adminService.updateVoucher(id, restoreData).subscribe({
        next: () => {
        this.loadVouchers();
        },
        error: (err) => {
        this.showErrorModal('Lỗi khôi phục', err.error?.detail || 'Không xác định');
        }
    });
 }

  get pagedVouchers() { return this.vouchers.slice(this.skip, this.skip + this.limit); }
  switchTab(tab: 'active' | 'trash') { this.activeTab = tab; this.skip = 0; this.applyFilterAndTab(); }
}