import { Component, OnInit, inject, ChangeDetectionStrategy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { User } from '../../../core/models/index';
import { AuthService } from '../../../core/services/auth.service';
import { take } from 'rxjs/operators';
import { mediaUrl } from '../../../core/utils/media-url';

@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './profile.html',
  styleUrls: ['./profile.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class AdminProfileComponent implements OnInit {
  private authService = inject(AuthService);
  private cdr = inject(ChangeDetectorRef);

  user: User | null = null;
  currentPassword = '';
  newPassword = '';
  confirmPassword = '';
  
  // Getter an toàn
  get userProfile(): User { return this.user!; }

  ngOnInit() {
    this.loadUserProfile();
  }

  loadUserProfile() {
    this.authService.getMe().pipe(take(1)).subscribe({
      next: (data: User) => {
        this.user = data;
        this.cdr.markForCheck();
      }
    });
  }

  getAvatarUrl(path: string | null | undefined): string {
    return mediaUrl(path);
  }

  onImageError(event: any) { event.target.src = 'assets/images/default-avt.png'; }

  triggerFileUpload() { document.getElementById('avatarInput')?.click(); }

  onFileSelected(event: any) {
    const file = event.target.files[0];
    if (file) {
      this.authService.uploadAvatar(file).subscribe({
        next: (updatedUser) => {
          this.user = updatedUser;
          this.cdr.markForCheck();
        }
      });
    }
  }

  saveChanges() {
    if (!this.user) return;
    this.authService.updateProfile(this.user).subscribe(() => alert('Đã cập nhật!'));
  }

  changePassword() {
    if (this.newPassword !== this.confirmPassword) {
      alert('Mật khẩu mới không khớp');
      return;
    }
    this.authService.changePassword(this.currentPassword, this.newPassword).subscribe({
      next: () => {
        alert('Đổi mật khẩu thành công');
        this.currentPassword = this.newPassword = this.confirmPassword = '';
      },
      error: (err) => alert('Lỗi: ' + (err.error?.detail || 'Không thể đổi mật khẩu'))
    });
  }
}