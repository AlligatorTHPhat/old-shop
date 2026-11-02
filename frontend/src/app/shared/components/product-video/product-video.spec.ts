import { TestBed } from '@angular/core/testing';
import { ProductVideoComponent } from './product-video';

describe('ProductVideoComponent', () => {
  it('uses a player for managed MP4 and a link for Drive, clearing a prior playback error', async () => {
    const fixture = TestBed.createComponent(ProductVideoComponent);
    fixture.componentRef.setInput('url', '/media/videos/products/seed/product-demo.mp4');
    fixture.detectChanges();
    const page: HTMLElement = fixture.nativeElement;
    expect(page.querySelector('video')?.getAttribute('src')).toContain('/media/videos/products/seed/product-demo.mp4');
    page.querySelector('video')!.dispatchEvent(new Event('error'));
    fixture.detectChanges();
    expect(page.querySelector('[role="alert"]')).toBeTruthy();

    fixture.componentRef.setInput('url', 'https://drive.google.com/file/d/abcdefghijk/view');
    fixture.detectChanges();
    expect(page.querySelector('video')).toBeNull();
    expect(page.querySelector('[role="alert"]')).toBeNull();
    expect(page.querySelector('a')?.textContent).toContain('Xem trên Google Drive');
    expect(page.querySelector('a')?.rel).toContain('noopener');
  });

  it('does not expose unsafe external URLs or render a player for an absent video', () => {
    const fixture = TestBed.createComponent(ProductVideoComponent);
    fixture.componentRef.setInput('url', 'javascript:alert(1)');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('a')).toBeNull();
    fixture.componentRef.setInput('url', null);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('section')).toBeNull();
  });
});
