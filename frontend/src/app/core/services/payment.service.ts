import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class PaymentService {
  private http = inject(HttpClient);
  private apiUrl = `${environment.apiUrl}/orders`;

  // Gọi Backend để xác nhận tiền đã thanh toán thành công
  capturePaypalOrder(orderId: number, paypalOrderId: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/${orderId}/capture-paypal?paypal_order_id=${paypalOrderId}`, {});
  }
}