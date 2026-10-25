import { ChangeDetectorRef, Component, ElementRef, ViewChild } from '@angular/core';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule, FormsModule } from '@angular/forms'; // Thêm FormsModule
import { CommonModule } from '@angular/common';
import { AuthService } from '../../../core/services/auth.service';
import { Router } from '@angular/router';

declare var bootstrap: any;

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [ReactiveFormsModule, FormsModule, CommonModule], // Cần FormsModule cho [(ngModel)]
  templateUrl: './login.html'
})
export class LoginComponent {
  @ViewChild('loginModalElement') loginModalElement!: ElementRef;
  
  loginForm: FormGroup;
  isLoading = false;

  // --- CÁC BIẾN CẦN THÊM ĐỂ FIX LỖI ---
  authStep: 'login' | 'forgot' | 'reset' | string = 'login';
  forgotEmail = '';
  resetData = {
    otp: '',
    new_password: ''
  };

  constructor(
    private fb: FormBuilder,
    private authService: AuthService,
    private router: Router,
    private cdr: ChangeDetectorRef
  ) {
    this.loginForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]],
      password: ['', Validators.required]
    });
  }

  onSubmit() {
    if (this.loginForm.invalid) {
      alert('Vui lòng nhập đúng Email và Mật khẩu!');
      return;
    }

    this.isLoading = true;
    const { email, password } = this.loginForm.value;
    const returnUrl = this.router.url || '/home';

    this.authService.login(email, password).subscribe({
      next: (res) => {
        this.isLoading = false;
        this.hideModal();
        this.loginForm.reset();
        this.router.navigateByUrl(returnUrl);
      },
      error: (err) => {
        this.isLoading = false;
        alert(err.error?.detail || 'Sai tài khoản hoặc mật khẩu rồi ný!');
        console.error('Lỗi login:', err);
        this.cdr.detectChanges();
      }
    });
  }

  // --- CÁC HÀM CẦN THÊM ĐỂ FIX LỖI ---
  sendOTP() {
    if (!this.forgotEmail) {
      alert('Nhập email đã ný!');
      return;
    }
    this.isLoading = true;
    console.log('Bắt đầu gọi API gửi OTP tới:', this.forgotEmail);

    this.authService.forgotPasswordOtp(this.forgotEmail).subscribe({
      next: (res) => {
        this.isLoading = false;
        this.authStep = 'reset'; // Gửi xong mới chuyển bước
        console.log('Kết quả:', res);
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.isLoading = false;
        alert(err.error?.detail || 'Lỗi gửi OTP rồi ný');
        this.cdr.detectChanges();
      }
    });
  }

  resetPassword() {
    if (!this.resetData.otp || !this.resetData.new_password) {
      alert('Điền đủ thông tin đi ný!');
      return;
    }
    this.isLoading = true;
    
    // Tạo object đúng format VerifyOTPRequest
    const payload = {
      email: this.forgotEmail,
      otp: this.resetData.otp,
      new_password: this.resetData.new_password
    };

    this.authService.verifyOtpAndResetPassword(payload).subscribe({
      next: (res) => {
        this.isLoading = false;
        alert('Đổi mật khẩu thành công! Giờ đăng nhập đi.');
        this.authStep = 'login'; // Thành công thì quay lại form login
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.isLoading = false;
        alert(err.error?.detail || 'Lỗi xác thực OTP');
        this.cdr.detectChanges();
      }
    });
  }

  private hideModal() {
    const modal = bootstrap.Modal.getInstance(this.loginModalElement.nativeElement);
    modal?.hide();
  }

  private handleError(err: any) {
    console.error(err);
  }
}