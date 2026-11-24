import { testProviders } from '../../../testing/providers';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { ShopComponent } from './shop';

describe('ShopComponent', () => {
  let component: ShopComponent;
  let fixture: ComponentFixture<ShopComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      providers: testProviders,
      imports: [ShopComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(ShopComponent);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('shows matching images and follows the server cursor', () => {
    const http = TestBed.inject(HttpTestingController);
    component.searchQuery = 'alphaonly';
    component.graphImageSearch = true;
    component.onSearch();
    const first = http.expectOne(req => req.url.endsWith('/images/search'));
    expect(first.request.params.get('q')).toBe('alphaonly');
    const image = { image_id: 9, product_id: 5, image_url: '/media/9.jpg', caption: 'Ảnh riêng' };
    first.flush({ items: [image], next_cursor: 'cursor-signed' });
    expect(component.matchedImages).toEqual([image]);
    component.runImageSearch(true);
    const next = http.expectOne(req => req.url.endsWith('/images/search'));
    expect(next.request.params.get('cursor')).toBe('cursor-signed');
    next.flush({ items: [], next_cursor: null });
    expect(component.matchedImages).toEqual([image]);
    expect(component.imageSearchCursor).toBeNull();
  });

  it('displays an error when the image search service is unavailable', () => {
    const http = TestBed.inject(HttpTestingController);
    component.searchQuery = 'mô tả';
    component.runImageSearch();
    http.expectOne(req => req.url.endsWith('/images/search')).flush({}, { status: 503, statusText: 'Unavailable' });
    expect(component.loadingImages).toBe(false);
    expect(component.imageSearchError).toContain('chưa khả dụng');
  });
});
