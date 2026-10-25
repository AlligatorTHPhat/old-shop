import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface ContactInfo {
  contact_id?: number;
  user_id?: number;
  full_name: string;
  phone_number: string;
  address: string;
  province?: string;
  district?: string;
  ward?: string;
  is_default: boolean;
  created_at?: string;
}

@Injectable({
  providedIn: 'root'
})
export class ContactService {
  private http = inject(HttpClient);
  private apiUrl = `${environment.apiUrl}/users/me/contacts`;

  constructor() {}

  getContactInfos(): Observable<ContactInfo[]> {
    return this.http.get<ContactInfo[]>(this.apiUrl);
  }

  createContactInfo(contact: ContactInfo): Observable<ContactInfo> {
    return this.http.post<ContactInfo>(this.apiUrl, contact);
  }

  updateContactInfo(contactId: number, contact: ContactInfo): Observable<ContactInfo> {
    return this.http.put<ContactInfo>(`${this.apiUrl}/${contactId}`, contact);
  }

  deleteContactInfo(contactId: number): Observable<any> {
    return this.http.delete(`${this.apiUrl}/${contactId}`);
  }

  setDefaultContact(contactId: number): Observable<any> {
    return this.http.post(`${this.apiUrl}/${contactId}/set-default`, {});
  }
}
