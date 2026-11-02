import { TestBed } from '@angular/core/testing';
import { HttpEventType, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { vi } from 'vitest';
import { environment } from '../../../../environments/environment';
import { UIService } from '../../../core/services/ui.service';
import { ProductManageComponent } from './product-manage';

describe('Seller product video submission', () => {
  const base = `${environment.apiUrl}/products`;
  const existing = {
    product_id: 42, title: 'Máy ảnh', category_id: 1, price: 1000, quantity: 1,
    video_url: '/media/videos/products/42/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.mp4',
  };
  let http: HttpTestingController;
  let component: ProductManageComponent;
  const showError = vi.fn();

  beforeEach(() => {
    showError.mockClear();
    TestBed.configureTestingModule({
      imports: [ProductManageComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), { provide: UIService, useValue: { showError } }],
    });
    const fixture = TestBed.createComponent(ProductManageComponent);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    http.expectOne(`${base}/seller/my-products`).flush([]);
    http.expectOne(`${environment.apiUrl}/categories`).flush([]);
  });

  afterEach(() => http.verify());

  it('creates a listing with a Drive link and omits empty optional numeric fields', () => {
    component.openModal();
    component.productForm.patchValue({ title: 'Máy ảnh', category_id: 1, price: 1000, quantity: 1,
      video_url: 'https://drive.google.com/file/d/abcdefghijk/view' });
    component.selectedFiles = [new File(['photo'], 'photo.png', { type: 'image/png' })];
    component.changeVideoMode('link');
    component.onSubmit();
    const request = http.expectOne(base);
    const body = request.request.body as FormData;
    expect(body.get('video_url')).toContain('drive.google.com');
    expect(body.has('video_file')).toBe(false);
    expect(body.has('weight_grams')).toBe(false);
    request.flush(existing);
    http.expectOne(`${base}/seller/my-products`).flush([]);
  });

  it('sends an MP4 and listing fields together and waits for the server response after upload', () => {
    component.openModal(existing);
    component.selectedVideo = new File(['video'], 'movie.mp4', { type: 'video/mp4' });
    component.onSubmit();
    const request = http.expectOne(`${base}/42/listing`);
    const body = request.request.body as FormData;
    expect(body.get('video_file')).toBe(component.selectedVideo);
    expect(JSON.parse(body.get('details') as string).video_url).toBeUndefined();
    request.event({ type: HttpEventType.UploadProgress, loaded: 5, total: 5 });
    expect(component.uploadProgress).toBe(100);
    expect(component.isSubmitting).toBe(true);
    request.flush(existing);
    expect(component.showModal).toBe(false);
    http.expectOne(`${base}/seller/my-products`).flush([]);
  });

  it('keeps an existing upload when editing other fields, and uses null for explicit removal', () => {
    component.openModal(existing);
    component.onSubmit();
    let request = http.expectOne(`${base}/42/listing`);
    expect(JSON.parse(request.request.body.get('details')).video_url).toBeUndefined();
    request.flush(existing);
    http.expectOne(`${base}/seller/my-products`).flush([]);

    component.openModal(existing);
    component.changeVideoMode('none');
    component.onSubmit();
    request = http.expectOne(`${base}/42/listing`);
    expect(JSON.parse(request.request.body.get('details')).video_url).toBeNull();
    request.flush({ ...existing, video_url: null });
    http.expectOne(`${base}/seller/my-products`).flush([]);
  });

  it('retains the form and selected upload after server validation fails', () => {
    component.openModal(existing);
    const file = new File(['video'], 'movie.mp4', { type: 'video/mp4' });
    component.selectedVideo = file;
    component.onSubmit();
    http.expectOne(`${base}/42/listing`).flush({ detail: 'Video không hợp lệ' }, { status: 400, statusText: 'Bad Request' });
    expect(component.showModal).toBe(true);
    expect(component.selectedVideo).toBe(file);
    expect(component.isSubmitting).toBe(false);
    expect(showError).toHaveBeenCalledWith('Video không hợp lệ', 'Không thể lưu sản phẩm');
  });
});
