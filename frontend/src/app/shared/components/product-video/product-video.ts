import { CommonModule } from '@angular/common';
import { Component, Input, OnChanges } from '@angular/core';
import { mediaUrl } from '../../../core/utils/media-url';

@Component({
  selector: 'app-product-video',
  standalone: true,
  imports: [CommonModule],
  template: `
    <section *ngIf="url" class="my-3" aria-label="Video sản phẩm">
      <ng-container *ngIf="isUpload; else externalVideo">
        <video *ngIf="!failed" [src]="resolvedUrl" controls preload="metadata" playsinline
          class="w-100 rounded border" style="max-height: 420px; background: #111"
          (error)="failed = true">
          Trình duyệt không hỗ trợ phát video.
        </video>
        <p *ngIf="failed" class="text-danger small" role="alert">
          Không tải được video. Vui lòng thử lại sau.
        </p>
        <a [href]="resolvedUrl" target="_blank" rel="noopener noreferrer" class="d-inline-block mt-2">
          Mở video MP4
        </a>
      </ng-container>
      <ng-template #externalVideo>
        <a *ngIf="resolvedUrl" [href]="resolvedUrl" target="_blank" rel="noopener noreferrer"
          class="btn btn-outline-primary">
          {{ isDrive ? 'Xem trên Google Drive' : 'Xem video' }}
        </a>
        <p *ngIf="isDrive" class="small text-muted mt-2 mb-0">
          Video được mở trên Google Drive. Chủ video cần cấp quyền xem qua liên kết.
        </p>
      </ng-template>
    </section>
  `,
})
export class ProductVideoComponent implements OnChanges {
  @Input() url: string | null | undefined;
  failed = false;

  ngOnChanges() { this.failed = false; }

  get isUpload(): boolean {
    return !!this.url?.startsWith('/media/videos/products/');
  }

  get isDrive(): boolean {
    try { return new URL(this.url || '').hostname === 'drive.google.com'; }
    catch { return false; }
  }

  get resolvedUrl(): string {
    if (this.isUpload) return mediaUrl(this.url, '');
    return this.url?.startsWith('https://') ? this.url : '';
  }
}
