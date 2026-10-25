import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CategoryManageComponent } from './category-manage';

describe('CategoryManageComponent', () => {
  let component: CategoryManageComponent;
  let fixture: ComponentFixture<CategoryManageComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CategoryManageComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(CategoryManageComponent);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
