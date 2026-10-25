import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

declare var bootstrap: any;

export interface ModalConfig {
  title: string;
  message: string;
  type: 'success' | 'error' | 'warning' | 'info';
  confirmText?: string;
  cancelText?: string;
}

@Injectable({
  providedIn: 'root'
})
export class UIService {
  // Dùng BehaviorSubject
  private modalSubject = new BehaviorSubject<ModalConfig | null>(null);
  modal$ = this.modalSubject.asObservable();

  showModal(config: ModalConfig) {
    // NHỊP 1: Bơm dữ liệu (Title, Message, Type) vào Modal và nhường cho Angular tự do quét giao diện
    setTimeout(() => {
      this.modalSubject.next(config);

      // NHỊP 2: Đợi thêm 1 chút xíu (10ms - 50ms) để chắc chắn DOM đã cập nhật xong toàn bộ HTML
      // (Tuyệt đối KHÔNG dùng appRef.tick() ở đây nữa)
      setTimeout(() => {
        const modalElement = document.getElementById('globalNotificationModal');
        if (modalElement) {
          try {
            const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
            modal.show();
          } catch (e) {
            console.error("Lỗi khi mở modal:", e);
          }
        } else {
          console.warn("Không tìm thấy globalNotificationModal trong HTML!");
        }
      }, 50); 
    });
  }

  showSuccess(message: string, title: string = 'Thành công') {
    this.showModal({ title, message, type: 'success' });
  }

  showError(message: string, title: string = 'Lỗi') {
    this.showModal({ title, message, type: 'error' });
  }

  showInfo(message: string, title: string = 'Thông báo') {
    this.showModal({ title, message, type: 'info' });
  }
}