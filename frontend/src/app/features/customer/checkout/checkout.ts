import { Component, OnInit, inject, ChangeDetectorRef, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { CartService, CartItem } from '../../../core/services/cart.service';
import { ContactService, ContactInfo } from '../../../shared/services/contact.service';
import { OrderService, PaymentMethod, OrderCreate } from '../../../shared/services/order.service';
import { UIService } from '../../../core/services/ui.service';
import { environment } from '../../../../environments/environment';
import { Subscription } from 'rxjs';

declare var paypal: any;

@Component({
  selector: 'app-checkout',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './checkout.html',
  styleUrls: ['./checkout.scss']
})
export class CheckoutComponent implements OnInit, OnDestroy {
  private cartService = inject(CartService);
  private contactService = inject(ContactService);
  private orderService = inject(OrderService);
  private uiService = inject(UIService);
  private router = inject(Router);
  private cdr = inject(ChangeDetectorRef);

  // Data
  cartItems: CartItem[] = [];
  addresses: ContactInfo[] = [];
  paymentMethods: PaymentMethod[] = [];
  imageBaseUrl = environment.imageBaseUrl;

  // Form State
  selectedAddressId: number | null = null;
  selectedPaymentMethodId: number | null = null;
  // Ids from the payment_method seed table (database/03_seeds/payment_method/seed.sql).
  readonly PAYMENT = { COD: 1, PAYPAL: 4 } as const;
  customAddress: string = '';
  customPhone: string = '';
  orderNotes: string = '';

  
  // UI State
  isWaitingFraud = false;
  fraudCountdown = 0;
  canBypassFraud = false;
  isLoading = true;
  isSubmitting = false;
  isEditingContact = false;
  shippingFee = 30000;

  // --- THÊM STATE CHO VOUCHER ---
  voucherInput: string = '';
  appliedVoucher: any = null;
  discountAmount: number = 0;
  isCheckingVoucher: boolean = false;
  voucherError: string = '';

  private isPaypalInitialized = false;
  private subscriptions: Subscription = new Subscription();
  private lastCreatedOrderId: number = 0;

  ngOnInit(): void {
    this.loadData();
  }

  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
    this.isPaypalInitialized = false;
  }

  loadData(): void {
    this.isLoading = true;

    // 1. Giỏ hàng
    this.subscriptions.add(
      this.cartService.cartItems$.subscribe(items => {
        this.cartItems = items;
        if (items.length === 0 && !this.isLoading) {
          this.router.navigate(['/cart']);
        }
      })
    );

    // 2. Địa chỉ
    this.subscriptions.add(
      this.contactService.getContactInfos().subscribe({
        next: (data) => {
          this.addresses = data;
          const defaultAddr = data.find(a => a.is_default) || data[0];
          if (defaultAddr) {
            this.selectedAddressId = defaultAddr.contact_id || null;
            this.customAddress = defaultAddr.address;
            this.customPhone = defaultAddr.phone_number;
          }
        },
        error: () => this.uiService.showError('Không thể tải địa chỉ')
      })
    );

    // 3. Phương thức thanh toán (Khớp với ID render cứng)
    this.subscriptions.add(
      this.orderService.getPaymentMethods().subscribe({
        next: (data) => {
          this.paymentMethods = data;
          if (data.length > 0) {
            // Mặc định chọn COD (thường là ID 1)
            const cod = data.find(m => m.method_name.toUpperCase() === 'COD');
            this.selectedPaymentMethodId = cod ? cod.payment_method_id : data[0].payment_method_id;
          }
          this.isLoading = false;
          this.cdr.detectChanges();

          // Nếu mặc định load ra là PayPal (ID 2)
          if (this.selectedPaymentMethodId === this.PAYMENT.PAYPAL) {
            this.initPayPalButton();
          }
        },
        error: () => {
          this.isLoading = false;
          this.uiService.showError('Lỗi tải phương thức thanh toán');
        }
      })
    );
  }

  selectPaymentMethod(id: number): void {
    if (this.selectedPaymentMethodId === id) return;
    
    this.selectedPaymentMethodId = id;
    this.isPaypalInitialized = false; // Reset trạng thái mỗi khi chuyển

    // Clear container PayPal cũ để tránh lỗi render đè của SDK
    const container = document.getElementById('paypal-button-container');
    if (container) container.innerHTML = '';
    
    this.cdr.detectChanges();

    if (id === this.PAYMENT.PAYPAL) {
      // Dùng setTimeout để đảm bảo DOM đã render xong [style.display]
      setTimeout(() => this.initPayPalButton(), 0);
    }
  }

  isBanned = false;

  initPayPalButton(): void {
    if (this.isPaypalInitialized || typeof paypal === 'undefined' || this.selectedPaymentMethodId !== this.PAYMENT.PAYPAL) return;

    const container = document.getElementById('paypal-button-container');
    if (!container) return;

    paypal.Buttons({
      style: { layout: 'vertical', color: 'blue', shape: 'rect', label: 'pay' },
      createOrder: () => {
        // Chặn click nếu đang trong quá trình xử lý hoặc đang chờ fraud timer
        if (this.isSubmitting || this.isWaitingFraud) {
          return Promise.reject('Processing...');
        }
        
        this.isSubmitting = true;
        this.cdr.detectChanges();

        return fetch(`${environment.apiUrl}/orders/create-paypal-order?bypass_fraud=${this.canBypassFraud}`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${sessionStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(this.prepareOrderData())
        })
        .then(async res => {
          const data = await res.json();
          this.isSubmitting = false;

          // TRƯỜNG HỢP 1: BỊ CHẶN HOÀN TOÀN (403)
          if (res.status === 403) {
            this.isBanned = true;
            this.cdr.detectChanges();
            throw new Error('BANNED');
          }

          // TRƯỜNG HỢP 2: BẮT ĐỢI (429)
          if (res.status === 429) {
            this.startFraudTimer(data.detail.retry_after);
            throw new Error('FRAUD_WAIT');
          }

          if (!res.ok) throw new Error(data.detail || 'Network error');

          // Lưu ID đơn hàng nội bộ để tí nữa dùng hàm Capture
          this.lastCreatedOrderId = data.internal_order_id;
          this.cdr.detectChanges();

          return data.paypal.id;
        })
        .catch(err => {
          this.isSubmitting = false;
          this.cdr.detectChanges();
          throw err;
        });
      },
      onApprove: (data: any) => {
        this.isLoading = true;
        this.cdr.detectChanges();

        this.orderService.capturePaypalOrder(this.lastCreatedOrderId, data.orderID).subscribe({
          next: (res) => {
            this.isLoading = false;
            this.uiService.showSuccess("Thanh toán thành công!", "Hoàn tất");
            this.cartService.clearCart(); // Xóa sạch local cart
            this.router.navigate(['/customer/profile/orders']);
          },
          error: (err) => {
            this.isLoading = false;
            this.uiService.showError("Thanh toán thành công bên PayPal nhưng lỗi cập nhật hệ thống. Đừng lo!");
            this.cdr.detectChanges();
          }
        });
      },
      onError: (err: any) => {
        if (err.message === 'BANNED' || err.message === 'FRAUD_WAIT') {
          return;
        }
        this.uiService.showError("Giao dịch không thành công hoặc đã bị hủy.");
        console.error('PayPal Error:', err);
      }
    }).render('#paypal-button-container').then(() => {
      this.isPaypalInitialized = true;
    });
  }

  startFraudTimer(seconds: number) {
    this.isWaitingFraud = true;
    this.fraudCountdown = seconds;
    this.cdr.detectChanges();

    // Hiện thông báo Info cho user biết là đang kiểm tra
    this.uiService.showInfo(
      `Hệ thống cần ${seconds} giây để xác thực giao dịch an toàn. Vui lòng không đóng trang.`,
      "Đang kiểm tra bảo mật"
    );

    const interval = setInterval(() => {
      this.fraudCountdown--;
      this.cdr.detectChanges();

      if (this.fraudCountdown <= 0) {
        clearInterval(interval);
        this.isWaitingFraud = false;
        this.canBypassFraud = true;
        
        // Dùng showSuccess khi xác thực xong
        this.uiService.showSuccess(
          "Xác thực hoàn tất! Bây giờ bạn có thể nhấn Thanh toán lại.",
          "Sẵn sàng"
        );
        this.cdr.detectChanges();
      }
    }, 1000);
  }

  placeOrder(): void {
    if (!this.selectedAddressId || this.isSubmitting) return;
    
    this.isSubmitting = true;
    this.orderService.createOrder(this.prepareOrderData()).subscribe({
      next: () => {
        this.uiService.showSuccess('Thành công!');
        this.cartService.clearCart();
        this.router.navigate(['/customer/profile/orders']);
      },
      error: (err) => {
        this.isSubmitting = false;
        this.uiService.showError('Lỗi đặt hàng');
        this.cdr.detectChanges();
      }
    });
  }

  // --- API GỌI VOUCHER VÀ CẬP NHẬT ---
  applyVoucher() {
    if (!this.voucherInput.trim()) {
      this.voucherError = 'Vui lòng nhập mã giảm giá.';
      return;
    }

    this.isCheckingVoucher = true;
    this.voucherError = '';
    
    // Gọi API Check Voucher
    this.orderService.checkVoucher(this.voucherInput, this.getSubtotal()).subscribe({
      next: (res: any) => {
        this.appliedVoucher = res;
        this.discountAmount = res.calculated_discount;
        this.isCheckingVoucher = false;
        this.uiService.showSuccess(`Áp dụng mã thành công! Bạn được giảm ${this.discountAmount.toLocaleString('vi-VN')}đ`, 'Thành công');
        this.cdr.detectChanges();
      },
      error: (err: any) => {
        this.isCheckingVoucher = false;
        this.appliedVoucher = null;
        this.discountAmount = 0;
        this.voucherError = err.error?.detail || 'Mã giảm giá không hợp lệ.';
        this.cdr.detectChanges();
      }
    });
  }

  removeVoucher() {
    this.appliedVoucher = null;
    this.voucherInput = '';
    this.discountAmount = 0;
    this.voucherError = '';
    this.cdr.detectChanges();
  }

  // Cập nhật lại hàm lấy data gửi lên API
  private prepareOrderData(): any { // Dùng any để bypass lỗi thiếu field voucher_code nếu interface chưa update
    return {
      contact_id: this.selectedAddressId!,
      payment_method_id: this.selectedPaymentMethodId!,
      order_items: this.cartItems.map(item => ({
        product_id: item.product.product_id,
        quantity: item.quantity
      })),
      shipping_fee: this.shippingFee,
      shipping_address: this.customAddress,
      phone_number: this.customPhone,
      notes: this.orderNotes,
      voucher_code: this.appliedVoucher ? this.appliedVoucher.code : null // Bổ sung mã Voucher
    };
  }

  selectAddress(addr: ContactInfo): void {
    this.selectedAddressId = addr.contact_id || null;
    this.customAddress = addr.address;
    this.customPhone = addr.phone_number;
  }

  getSubtotal(): number {
    return this.cartService.getTotalPrice();
  }

  getTotal(): number {
    // Trừ đi discountAmount (số tiền giảm)
    return Math.max(0, this.getSubtotal() + this.shippingFee - this.discountAmount);
  }
  getFullImageUrl(imageUrl: string | undefined | null): string {
    if (!imageUrl || imageUrl === '') {
      return 'assets/images/placeholder.png';
    }
    const base = this.imageBaseUrl ? this.imageBaseUrl.replace(/\/$/, '') : '';
    const path = imageUrl.replace(/^\//, '');
    return `${base}/${path}`;
  }
}