import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { vi } from 'vitest';
import { environment } from '../../../../environments/environment';
import { ModeratorProductManageComponent } from './product-manage';

describe('Moderator product pagination', () => {
  let fixture: ComponentFixture<ModeratorProductManageComponent>;
  let http: HttpTestingController;
  let shownModal: HTMLElement | null;
  const endpoint = `${environment.apiUrl}/products/moderation/page`;
  const item = (id: number, status = 0) => ({
    product_id: id, title: `Sản phẩm ${id}`, description: `Mô tả ${id}`,
    price: '100000', quantity: 10, status, seller_id: 3, category_id: 1,
    seller_name: 'seller', category_name: 'Điện tử', product_images: [],
    video_url: '/media/videos/products/seed/product-demo.mp4',
  });
  const firstItems = Array.from({ length: 5 }, (_, index) => item(1001 - index));
  const pageResponse = (items = firstItems, total = 147, skip = 0) => ({ items, total, skip, limit: 5 });

  beforeEach(async () => {
    shownModal = null;
    vi.stubGlobal('bootstrap', {
      Modal: class {
        constructor(private element: HTMLElement) {}
        show() { shownModal = this.element; }
        static getInstance() { return { hide: vi.fn() }; }
      },
    });
    await TestBed.configureTestingModule({
      imports: [ModeratorProductManageComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ModeratorProductManageComponent);
    fixture.detectChanges();
    const initial = http.expectOne(req => req.url === endpoint);
    expect(initial.request.params.get('skip')).toBe('0');
    expect(initial.request.params.get('limit')).toBe('5');
    expect(initial.request.params.get('status')).toBe('0');
    initial.flush(pageResponse());
    fixture.detectChanges();
  });

  afterEach(() => {
    fixture.destroy();
    http.verify({ ignoreCancelled: true });
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('uses the server total and fetches records beyond the first 100', () => {
    const page: HTMLElement = fixture.nativeElement;
    expect(page.querySelectorAll('tbody tr')).toHaveLength(5);
    expect(page.querySelector('.pagination-info')?.textContent).toContain('147');
    const lastPage = Array.from(page.querySelectorAll<HTMLButtonElement>('.pagination button'))
      .find(button => button.textContent?.trim() === '30');
    lastPage!.click();
    const request = http.expectOne(req => req.url === endpoint);
    expect(request.request.params.get('skip')).toBe('145');
    request.flush(pageResponse([item(2), item(1)], 147, 145));
    fixture.detectChanges();
    expect(page.querySelectorAll('tbody tr')).toHaveLength(2);
    expect(page.querySelector('.pagination-info')?.textContent).toContain('146 - 147');
    page.querySelector<HTMLElement>('tbody .product-info .name')!.click();
    fixture.detectChanges();
    expect(shownModal?.id).toBe('productDetailModal');
    expect(page.querySelector('#productDetailModal .modal-title')?.textContent).toContain('Sản phẩm 2');
    expect(page.querySelector('#productDetailModal .modal-body')?.textContent).toContain('Mô tả 2');
    expect(page.querySelector('#productDetailModal video')?.getAttribute('src')).toContain('product-demo.mp4');
  });

  it('requests previous and next pages instead of slicing a local array', () => {
    const page: HTMLElement = fixture.nativeElement;
    page.querySelector<HTMLButtonElement>('[aria-label="Trang sau"]')!.click();
    let request = http.expectOne(req => req.url === endpoint);
    expect(request.request.params.get('skip')).toBe('5');
    request.flush(pageResponse(firstItems, 147, 5));
    fixture.detectChanges();
    page.querySelector<HTMLButtonElement>('[aria-label="Trang trước"]')!.click();
    request = http.expectOne(req => req.url === endpoint);
    expect(request.request.params.get('skip')).toBe('0');
    request.flush(pageResponse());
  });

  it('debounces server search, resets the page and sends the full search term', () => {
    vi.useFakeTimers();
    const component = fixture.componentInstance;
    component.currentPage = 20;
    component.onSearchChange('Sản');
    vi.advanceTimersByTime(100);
    component.onSearchChange('  Sản phẩm mới  ');
    vi.advanceTimersByTime(299);
    http.expectNone(req => req.url === endpoint);
    vi.advanceTimersByTime(1);
    const request = http.expectOne(req => req.url === endpoint);
    expect(request.request.params.get('search')).toBe('Sản phẩm mới');
    expect(request.request.params.get('skip')).toBe('0');
    request.flush(pageResponse([item(1001)], 1));
    fixture.detectChanges();
    expect(component.currentPage).toBe(1);
    expect(component.totalProducts).toBe(1);
  });

  it('cancels an old request when changing tabs and clears pending search', () => {
    fixture.componentInstance.goToPage(2);
    const oldRequest = http.expectOne(req => req.url === endpoint);
    fixture.componentInstance.selectTab('approved');
    expect(oldRequest.cancelled).toBe(true);
    let request = http.expectOne(req => req.url === endpoint);
    expect(request.request.params.get('status')).toBe('1');
    expect(request.request.params.get('skip')).toBe('0');
    request.flush(pageResponse([item(5, 1)], 1));
    vi.useFakeTimers();
    fixture.componentInstance.onSearchChange('old query');
    fixture.componentInstance.selectTab('rejected');
    request = http.expectOne(req => req.url === endpoint);
    expect(request.request.params.get('status')).toBe('2');
    expect(request.request.params.has('search')).toBe(false);
    request.flush(pageResponse([item(6, 2)], 1));
    vi.advanceTimersByTime(400);
    http.expectNone(req => req.url === endpoint);
  });

  it('returns to the preceding page when moderation empties the last page', () => {
    const component = fixture.componentInstance;
    component.goToPage(30);
    http.expectOne(req => req.url === endpoint).flush(pageResponse([item(2)], 146, 145));
    component.openModal(component.products[0], 'approved');
    component.confirmAction();
    const action = http.expectOne(`${environment.apiUrl}/products/2/status`);
    expect(action.request.body.new_status).toBe(1);
    action.flush(item(2, 1));
    http.expectOne(req => req.url === endpoint && req.params.get('skip') === '145')
      .flush(pageResponse([], 145, 145));
    http.expectOne(req => req.url === endpoint && req.params.get('skip') === '140')
      .flush(pageResponse(firstItems, 145, 140));
    fixture.detectChanges();
    expect(component.currentPage).toBe(29);
    expect(fixture.nativeElement.querySelector('.pagination-info')?.textContent).toContain('141 - 145');
  });

  it('shows load failures with retry instead of claiming that the queue is empty', () => {
    fixture.componentInstance.goToPage(2);
    http.expectOne(req => req.url === endpoint).flush({}, { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();
    const page: HTMLElement = fixture.nativeElement;
    expect(page.querySelector('[role="alert"]')?.textContent).toContain('Không tải được');
    expect(page.querySelector('.empty-state')).toBeNull();
    page.querySelector<HTMLButtonElement>('[role="alert"] button')!.click();
    http.expectOne(req => req.url === endpoint).flush(pageResponse(firstItems, 147, 5));
    fixture.detectChanges();
    expect(page.querySelectorAll('tbody tr')).toHaveLength(5);
    expect(page.querySelector('[role="alert"]')).toBeNull();
  });

  it('reloads the first page to discover newly submitted products', () => {
    fixture.componentInstance.currentPage = 10;
    fixture.componentInstance.refreshProducts();
    const request = http.expectOne(req => req.url === endpoint);
    expect(request.request.params.get('skip')).toBe('0');
    request.flush(pageResponse([item(1002), ...firstItems.slice(0, 4)], 148));
    expect(fixture.componentInstance.products[0].product_id).toBe(1002);
    expect(fixture.componentInstance.totalProducts).toBe(148);
  });
});
