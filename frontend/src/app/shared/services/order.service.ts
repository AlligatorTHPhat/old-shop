import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface OrderItem {
  product_id: number;
  quantity: number;
}

export interface OrderCreate {
  contact_id: number;
  payment_method_id: number;
  order_items: OrderItem[];
  voucher_code?: string | null; // Thay đổi từ voucher_id sang voucher_code
  shipping_fee: number;
  shipping_address?: string;
  phone_number?: string;
  notes?: string;
}

export interface PaymentMethod {
  payment_method_id: number;
  method_name: string;
  is_online: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class OrderService {
  private http = inject(HttpClient);
  private apiUrl = `${environment.apiUrl}/orders`;

  constructor() {}

  getPaymentMethods(): Observable<PaymentMethod[]> {
    return this.http.get<PaymentMethod[]>(`${this.apiUrl}/payment-methods`);
  }

  createOrder(order: OrderCreate): Observable<any> {
    return this.http.post<any>(this.apiUrl, order);
  }

  getOrders(): Observable<any[]> {
    return this.http.get<any[]>(this.apiUrl);
  }

  getOrderDetails(orderId: number): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/${orderId}`);
  }

  capturePaypalOrder(orderId: number, paypalOrderId: string): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/${orderId}/capture-paypal`, {}, {
      params: { paypal_order_id: paypalOrderId }
    });
  }

  /**
   * Gọi API kiểm tra mã giảm giá (Voucher)
   */
  checkVoucher(code: string, orderAmount: number): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/check-voucher/${code}?order_amount=${orderAmount}`);
  }
}