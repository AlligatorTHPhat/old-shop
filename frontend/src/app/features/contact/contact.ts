import { Component, ChangeDetectorRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { finalize } from 'rxjs';
import { UIService } from '../../core/services/ui.service';
import { environment } from '../../../environments/environment';

/**
 * Contact form. Messages go to the backend (`POST /system/contact`), which stores them and relays
 * them to the Google Apps Script helpdesk sheet. The Apps Script URL never reaches the browser.
 */
@Component({
  selector: 'app-contact',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './contact.html',
  styleUrls: ['./contact.scss']
})
export class ContactComponent {
  private http = inject(HttpClient);
  private uiService = inject(UIService);
  private cdr = inject(ChangeDetectorRef);

  isLoading = false;

  contactInfo = {
    office: 'Số 123, Đường ABC, Quận Ninh Kiều, Cần Thơ',
    email: 'contact@oldshop.com',
    phone: '0987.654.321',
    messenger: 'm.me/oldshop.secondhand'
  };

  formData = this.emptyForm();

  sendMessage() {
    const { fullName, email, phone, subject, message } = this.formData;
    if (!fullName || !email || !message) {
      this.uiService.showError('Vui lòng điền đầy đủ các thông tin bắt buộc!', 'Thông báo');
      return;
    }

    this.isLoading = true;
    this.http
      .post(`${environment.apiUrl}/system/contact`, {
        full_name: fullName,
        email,
        phone: phone || null,
        subject: subject || null,
        message
      })
      .pipe(
        finalize(() => {
          this.isLoading = false;
          this.cdr.detectChanges();
        })
      )
      .subscribe({
        next: () => {
          this.uiService.showModal({
            title: 'Đã gửi yêu cầu!',
            message: 'Cảm ơn bạn đã liên hệ. Đội ngũ OldShop sẽ phản hồi bạn sớm nhất.',
            type: 'success'
          });
          this.formData = this.emptyForm();
        },
        error: () => this.uiService.showError('Đã có lỗi xảy ra, vui lòng thử lại sau!', 'Lỗi')
      });
  }

  private emptyForm() {
    return { fullName: '', email: '', phone: '', subject: '', message: '' };
  }
}
