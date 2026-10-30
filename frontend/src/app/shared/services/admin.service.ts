import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { catchError, Observable, throwError } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AdminDashboardStats } from '../../core/models';

@Injectable({
  providedIn: 'root'
})
export class AdminService {
  private apiUrl = `${environment.apiUrl}`;

  constructor(private http: HttpClient) {}

  // Dashboard Stats
  getStats(salesYear?: number): Observable<AdminDashboardStats> {
    const params: Record<string, string> = salesYear ? { sales_year: salesYear.toString() } : {};
    return this.http.get<AdminDashboardStats>(`${this.apiUrl}/admin/stats`, { params });
  }

  // User Management
  getUsers(skip: number = 0, limit: number = 20): Observable<any[]> {
    let params = new HttpParams()
      .set('skip', skip.toString())
      .set('limit', limit.toString());
    return this.http.get<any[]>(`${this.apiUrl}/admin/users`, { params });
  }

  getModerators(includeDeleted: boolean = false): Observable<any[]> {
    let params = new HttpParams().set('include_deleted', includeDeleted.toString());
    return this.http.get<any[]>(`${this.apiUrl}/admin/moderators`, { params });
  }

  createModerator(moderator: any): Observable<any> {
    return this.http.post(`${this.apiUrl}/admin/moderators`, moderator);
  }

  toggleModeratorStatus(userId: number, action: 'lock' | 'unlock', reason: string): Observable<any> {
    return this.http.patch(`${this.apiUrl}/admin/moderators/${userId}/status`, { action, reason });
  }

  banUser(userId: number, reason: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/moderator/users/${userId}/ban`, { reason });
  }

  unbanUser(userId: number, reason: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/moderator/users/${userId}/unban`, { reason });
  }

  deleteUser(userId: number): Observable<any> {
    return this.http.delete(`${this.apiUrl}/users/${userId}`);
  }
  
  getViolationLogs(skip: number = 0, limit: number = 100): Observable<any[]> {
    return this.http.get<any[]>(`${this.apiUrl}/admin/violation-logs`, {
      params: { skip: skip.toString(), limit: limit.toString() }
    });
  }

  // Voucher Management
  getVouchers(): Observable<any[]> {
    return this.http.get<any[]>(`${this.apiUrl}/admin/vouchers`);
  }

  createVoucher(data: any): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/admin/vouchers`, data);
  }

  updateVoucher(id: number, data: any): Observable<any> {
    return this.http.patch<any>(`${this.apiUrl}/admin/vouchers/${id}`, data);
  }

  deleteVoucher(id: number): Observable<any> {
    return this.http.delete<any>(`${this.apiUrl}/admin/vouchers/${id}`);
  }

  hardDeleteVoucher(id: number): Observable<any> {
    return this.http.delete<any>(`${this.apiUrl}/admin/vouchers/${id}/hard-delete`);
  }

  // Feedback Management
  getFeedbacks(skip: number = 0, limit: number = 100): Observable<any[]> {
    let params = new HttpParams()
      .set('skip', skip.toString())
      .set('limit', limit.toString());
    return this.http.get<any[]>(`${this.apiUrl}/admin/feedbacks`, { params });
  }

  updateFeedbackStatus(feedbackId: number, status: number): Observable<any> {
    let params = new HttpParams().set('status_update', status.toString());
    return this.http.patch(`${this.apiUrl}/admin/feedbacks/${feedbackId}`, {}, { params });
  }

  // Category Management
  getCategories(activeOnly: boolean = false, includeDeleted: boolean = false): Observable<any[]> {
    let params = new HttpParams()
      .set('active_only', activeOnly.toString())
      .set('include_deleted', includeDeleted.toString());
    return this.http.get<any[]>(`${this.apiUrl}/categories`, { params });
  }

  createCategory(category: any): Observable<any> {
    return this.http.post(`${this.apiUrl}/categories`, category);
  }

  updateCategory(categoryId: number, category: any): Observable<any> {
    return this.http.put(`${this.apiUrl}/categories/${categoryId}`, category).pipe(
      catchError((error) => {
        return throwError(() => error);
      })
    );
  }

  deleteCategory(id: number): Observable<any> {
    return this.http.delete(`${this.apiUrl}/categories/${id}`).pipe(
      catchError((error) => {
        return throwError(() => error);
      })
    );
  }

  hardDeleteCategory(categoryId: number): Observable<any> {
    return this.http.delete(`${this.apiUrl}/categories/${categoryId}/hard-delete`);
  }

  restoreCategory(categoryId: number): Observable<any> {
    return this.http.post(`${this.apiUrl}/categories/${categoryId}/restore`, {});
  }
}
