import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Product } from '../../core/models';
import { environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class ProductService {
  private apiUrl = `${environment.apiUrl}/products`;

  constructor(
    private http: HttpClient
  ) {}

  getProducts(params?: {
    skip?: number;
    limit?: number;
    category_id?: number;
    search?: string;
    sort_by?: string;
  }): Observable<Product[]> {
    let httpParams = new HttpParams();

    if (params) {
      if (params.skip !== undefined) httpParams = httpParams.set('skip', params.skip.toString());
      if (params.limit !== undefined) httpParams = httpParams.set('limit', params.limit.toString());
      if (params.category_id !== undefined) httpParams = httpParams.set('category_id', params.category_id.toString());
      if (params.search) httpParams = httpParams.set('search', params.search);
      if (params.sort_by) httpParams = httpParams.set('sort_by', params.sort_by);
    }

    const token = sessionStorage.getItem('token');
    const headers: any = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    return this.http.get<Product[]>(this.apiUrl, { params: httpParams, headers });
  }

  getProduct(id: number): Observable<Product> {
    const token = sessionStorage.getItem('token');
    const headers: any = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    return this.http.get<Product>(`${this.apiUrl}/${id}`, { headers });
  }

  createProduct(formData: FormData): Observable<Product> {
    return this.http.post<Product>(this.apiUrl, formData);
  }

  updateProduct(id: number, product: Partial<Product>): Observable<Product> {
    return this.http.put<Product>(`${this.apiUrl}/${id}`, product);
  }

  getProductsByStatus(status: number): Observable<Product[]> {
    const token = sessionStorage.getItem('token');
    const headers = { 'Authorization': `Bearer ${token}` };
    return this.http.get<Product[]>(`${this.apiUrl}/moderation/list`, { 
        params: { status: status.toString() }, 
        headers 
    });
  }

  updateProductStatus(productId: number, status: number, reason?: string): Observable<Product> {
    const token = sessionStorage.getItem('token');
    const headers = { 'Authorization': `Bearer ${token}` };
    const body: any = { new_status: status };
    if (reason) body.reject_reason = reason;
    return this.http.post<Product>(`${this.apiUrl}/${productId}/status`, body, { headers });
  }

  deleteProduct(id: number): Observable<void> {
    return this.http.delete<void>(`${this.apiUrl}/${id}`);
  }

  getMyProducts(params?: { skip?: number; limit?: number }): Observable<Product[]> {
    let httpParams = new HttpParams();
    if (params) {
      if (params.skip !== undefined) httpParams = httpParams.set('skip', params.skip.toString());
      if (params.limit !== undefined) httpParams = httpParams.set('limit', params.limit.toString());
    }

    const token = sessionStorage.getItem('token');
    const headers: any = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    return this.http.get<Product[]>(`${this.apiUrl}/seller/my-products`, { params: httpParams, headers });
  }

  submitReview(productId: number, data: { rating: number, content: string, title?: string }): Observable<any> {
    const token = sessionStorage.getItem('token');
    const headers = { 'Authorization': `Bearer ${token}` };
    return this.http.post<any>(`${this.apiUrl}/${productId}/reviews`, data, { headers });
  }

  getReportedReviews(): Observable<any[]> {
    const token = sessionStorage.getItem('token');
    const headers = { 'Authorization': `Bearer ${token}` };
    return this.http.get<any[]>(`${environment.apiUrl}/moderator/reviews/violations`, { headers });
  }
}