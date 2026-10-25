import { Component, OnInit, inject, ChangeDetectionStrategy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { User } from '../../../core/models/index';
import { AuthService } from '../../../core/services/auth.service';
import { take } from 'rxjs/operators';
import { mediaUrl } from '../../../core/utils/media-url';

@Component({
  selector: 'app-customer-profile',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './profile.html',
  styleUrls: ['./profile.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush
})

export class ProfileComponent implements OnInit {
  private authService = inject(AuthService);
  private cdr = inject(ChangeDetectorRef);
  
  user: User | null = null;
  currentPassword: string = '';
  newPassword: string = '';
  confirmPassword: string = '';
  passwordError: string | null = null;
  readonly defaultAvatar = 'assets/images/default-avt.png';

  // Getter an toàn để template sử dụng
  get userProfile(): User {
    return this.user!; 
  }

  ngOnInit() { this.loadUserProfile(); }

  loadUserProfile() {
    this.authService.getMe().pipe(take(1)).subscribe({
      next: (data: User) => {
        this.user = data;
        this.cdr.markForCheck();
      },
      error: (err) => console.error('Lỗi tải profile:', err)
    });
  }

  getAvatarUrl(path: string | null | undefined): string {
    return mediaUrl(path, this.defaultAvatar);
  }

  onImageError(event: any) { event.target.src = this.defaultAvatar; }
  
  triggerFileUpload() {
    document.getElementById('avatarInput')?.click();
  }

  onFileSelected(event: any) {
    const file = event.target.files[0];
    if (file) {
      this.authService.uploadAvatar(file).subscribe({
        next: (updatedUser: User) => {
          this.user = updatedUser;
          this.cdr.markForCheck();
          // alert('Avatar updated successfully!');
        },
        error: (err) => console.error('Error uploading avatar:', err)
      });
    }
  }

  saveChanges() {
    if (!this.user) return;

    this.authService.updateProfile(this.user).subscribe({
      next: (updatedUser: User) => {
        this.authService.updateLocalUser(updatedUser); 
        this.user = updatedUser;
        alert('Cập nhật thành công!');
      },
      error: (err: any) => {
        console.error('Lỗi khi lưu:', err);
      }
    });
  }

  changePassword() {
    if (!this.user) return;
    if (!this.currentPassword || !this.newPassword) {
      alert('Vui lòng nhập đầy đủ thông tin');
      return;
    }
    if (this.newPassword !== this.confirmPassword) {
      alert('Mật khẩu mới không khớp');
      return;
    }

    this.authService.changePassword(this.currentPassword, this.newPassword).subscribe({
      next: () => {
        alert('Đổi mật khẩu thành công');
        this.currentPassword = this.newPassword = this.confirmPassword = '';
        this.passwordError = null;
        this.cdr.markForCheck();
      },
      error: (err: any) => {
        console.error('Lỗi đổi mật khẩu:', err);
        // Parse validation errors from backend (Pydantic -> { detail: [ { msg, ... } ] })
        const detail = err?.error?.detail;
        if (Array.isArray(detail)) {
          try {
            this.passwordError = detail.map((d: any) => d.msg || JSON.stringify(d)).join('; ');
          } catch (e) {
            this.passwordError = JSON.stringify(detail);
          }
        } else if (typeof detail === 'string') {
          this.passwordError = detail;
        } else {
          this.passwordError = err?.error?.message || 'Không thể đổi mật khẩu';
        }
        this.cdr.markForCheck();
      }
    });
  }
}