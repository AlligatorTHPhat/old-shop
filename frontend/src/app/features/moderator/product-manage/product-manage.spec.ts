import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { vi } from 'vitest';

import { CategoryService } from '../../../shared/services/category.service';
import { ModeratorService } from '../../../shared/services/moderator.service';
import { ProductService } from '../../../shared/services/product.service';
import { ModeratorProductManageComponent } from './product-manage';

describe('ModeratorProductManageComponent', () => {
  let fixture: ComponentFixture<ModeratorProductManageComponent>;
  let shownModal: HTMLElement | null;
  const products = Array.from({ length: 6 }, (_, index) => ({
    product_id: index + 1,
    title: `Sản phẩm kiểm thử ${index + 1}`,
    description: `Mô tả ${index + 1}`,
    price: '100000',
    quantity: 10,
    status: 0,
    seller_id: 3,
    category_id: 1,
    product_images: [],
  }));

  beforeEach(async () => {
    shownModal = null;
    vi.stubGlobal('bootstrap', {
      Modal: class {
        constructor(private element: HTMLElement) {}
        show() {
          shownModal = this.element;
        }
      },
    });
    await TestBed.configureTestingModule({
      imports: [ModeratorProductManageComponent],
      providers: [
        { provide: CategoryService, useValue: { getCategories: () => of([{ category_id: 1, name: 'Điện tử' }]) } },
        { provide: ModeratorService, useValue: { getUsers: () => of([{ user_id: 3, username: 'seller' }]) } },
        { provide: ProductService, useValue: { getProductsByStatus: () => of(products) } },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(ModeratorProductManageComponent);
    fixture.detectChanges();
    await vi.waitFor(() => expect(fixture.componentInstance.products).toHaveLength(6));
    await fixture.whenStable();
  });

  afterEach(() => vi.unstubAllGlobals());

  it('renders pagination when the loaded list exceeds one page', () => {
    const page: HTMLElement = fixture.nativeElement;
    expect(page.querySelectorAll('tbody tr')).toHaveLength(5);
    expect(page.querySelector('.pagination-info')?.textContent).toContain('1 - 5');
  });

  it('opens the selected product after moving to the last partial page', async () => {
    const page: HTMLElement = fixture.nativeElement;
    const lastPage = Array.from(page.querySelectorAll<HTMLButtonElement>('.pagination button'))
      .find(button => button.textContent?.trim() === '2');
    lastPage!.click();
    await fixture.whenStable();
    expect(page.querySelectorAll('tbody tr')).toHaveLength(1);
    expect(page.querySelector('.pagination-info')?.textContent).toContain('6 - 6');

    page.querySelector<HTMLElement>('tbody .product-info .name')!.click();
    await fixture.whenStable();
    expect(shownModal?.id).toBe('productDetailModal');
    expect(page.querySelector('#productDetailModal .modal-title')?.textContent).toContain('Sản phẩm kiểm thử 6');
    expect(page.querySelector('#productDetailModal .modal-body')?.textContent).toContain('Mô tả 6');
  });
});
