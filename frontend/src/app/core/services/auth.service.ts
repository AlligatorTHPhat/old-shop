import { Injectable, signal, inject } from '@angular/core';
import { Router } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { Observable, tap, switchMap, of } from 'rxjs';
import { environment } from '../../../environments/environment';
import { User, VerifyOTPRequest } from '../models';

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);
  private apiUrl = `${environment.apiUrl}/auth`;

  currentUser = signal<any>(null);
  isLoggedIn = signal(false);

  constructor() {
    this.checkAuth();
  }
  isInitialized = signal(false);
  
  private checkAuth() {
    const token = sessionStorage.getItem('token');
    const cachedUser = sessionStorage.getItem('user');

    if (!token) {
      this.currentUser.set(null);
      this.isLoggedIn.set(false);
      this.isInitialized.set(true); // No token, initialization complete
      return;
    }

    if (cachedUser) {
      try {
        this.currentUser.set(JSON.parse(cachedUser));
        this.isLoggedIn.set(true);
      } catch {
        sessionStorage.removeItem('user');
      }
    }

    // Luôn refresh user từ API /me để tránh dữ liệu cũ trong sessionStorage
    this.getUserProfile().subscribe({
      next: () => this.isInitialized.set(true),
      error: () => { 
        this.logout(); 
        this.isInitialized.set(true); 
      }
    });
  }

  register(userData: any): Observable<any> {
    return this.http.post(`${this.apiUrl}/register`, userData);
  }

  login(email: string, password: string): Observable<any> {
    const formData = new FormData();
    formData.append('username', email);
    formData.append('password', password);

    return this.http.post<LoginResponse>(`${this.apiUrl}/login`, formData).pipe(
      tap(res => {
        sessionStorage.setItem('token', res.access_token);
      }),
      switchMap(() => this.getUserProfile()),
      tap((user) => {
        const roleId = (user.roles?.length > 0) ? Number(user.roles[0].role_id) : null;
        
        setTimeout(() => {
          if (roleId === 1) this.router.navigate(['/admin/dashboard']);
          else if (roleId === 2) this.router.navigate(['/moderator/dashboard']);
          else this.router.navigate(['/home']);
        }, 100);
      })
    );
  }

  getUserProfile(): Observable<any> {
    const token = sessionStorage.getItem('token');
    return this.http.get<any>(`${this.apiUrl}/me`).pipe(
      tap(user => {
        sessionStorage.setItem('user', JSON.stringify(user));
        this.currentUser.set(user);
        this.isLoggedIn.set(true);
      })
    );
  }

  isAuthenticated(): boolean {
    return !!sessionStorage.getItem('token');
  }

  getUserRole(): number | null {
    const user = this.currentUser();
    // Lấy thẳng từ roles[0]
    if (user && user.roles && user.roles.length > 0) {
      return Number(user.roles[0].role_id);
    }
    return null;
  }

  updateProfile(data: User): Observable<User> {
    const userApiUrl = `${environment.apiUrl}/users`; 
    return this.http.put<User>(`${userApiUrl}/me`, data);
  }
  updateLocalUser(user: User) {
    sessionStorage.setItem('user', JSON.stringify(user));
    this.currentUser.set(user);
  }

  uploadAvatar(file: File): Observable<User> {
    const userApiUrl = `${environment.apiUrl}/users`;
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post<User>(`${userApiUrl}/me/avatar`, formData).pipe(
      tap(updatedUser => this.updateLocalUser(updatedUser))
    );
  }

  changePassword(currentPassword: string, newPassword: string) {
    const userApiUrl = `${environment.apiUrl}/users`;
    return this.http.post<any>(`${userApiUrl}/me/change-password`, {
      current_password: currentPassword,
      new_password: newPassword
    });
  }

  forgotPasswordOtp(email: string): Observable<any> {
    const url = `${this.apiUrl}/forgot-password-otp?email=${encodeURIComponent(email)}`;
    return this.http.post(url, {}); 
  }

  verifyOtpAndResetPassword(data: VerifyOTPRequest): Observable<any> {
    return this.http.post(`${this.apiUrl}/verify-reset-password`, data);
  }

  logout() {
    sessionStorage.clear();
    this.currentUser.set(null);
    this.isLoggedIn.set(false);
    this.router.navigate(['/home']);
  }
  getMe(): Observable<User> {
    return this.http.get<User>(`${this.apiUrl}/me`);
  }
}