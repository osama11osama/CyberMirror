import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, interval, switchMap, takeWhile, last } from 'rxjs';

const API = (window as any).cyberMirror?.apiBase ?? 'http://127.0.0.1:8787/api';

export interface IdentityProfile {
  full_name: string;
  username: string;
  email: string;
  phone: string;
  location: string;
  website: string;
  company: string;
}

export interface ScanRequest {
  profile: IdentityProfile;
  providers: string[];
  async_mode?: boolean;
}

export interface ExportResponse {
  path: string;
  format: string;
}

export interface ScanStatus {
  scan_id: string;
  status: string;
  progress: number;
  message: string;
  current_provider?: string;
  findings_so_far: number;
  module_errors?: { module: string; error: string }[];
}

export interface ScanStartResponse {
  id: string;
  status: string;
  message: string;
  providers: string[];
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  constructor(private http: HttpClient) {}

  health(): Observable<any> {
    return this.http.get<any>(`${API}/health`);
  }

  modules(): Observable<any[]> { return this.http.get<any[]>(`${API}/modules`); }
  providers(): Observable<any[]> { return this.modules(); }
  settings(): Observable<any> { return this.http.get(`${API}/settings`); }
  updateSettings(body: any): Observable<any> { return this.http.put(`${API}/settings`, body); }
  clearCache(): Observable<any> { return this.http.post(`${API}/cache/clear`, {}); }
  trends(limit = 20): Observable<any> { return this.http.get(`${API}/dashboard/trends`, { params: { limit } }); }

  startScan(body: ScanRequest): Observable<ScanStartResponse> {
    return this.http.post<ScanStartResponse>(`${API}/scans`, { ...body, async_mode: true });
  }

  scanStatus(id: string): Observable<ScanStatus> {
    return this.http.get<ScanStatus>(`${API}/scans/${id}/status`);
  }

  liveFindings(id: string): Observable<{ findings: any[]; count: number }> {
    return this.http.get<{ findings: any[]; count: number }>(`${API}/scans/${id}/findings/live`);
  }

  cancelScan(id: string): Observable<any> {
    return this.http.post(`${API}/scans/${id}/cancel`, {});
  }

  pollScan(id: string, intervalMs = 1500): Observable<ScanStatus> {
    return interval(intervalMs).pipe(
      switchMap(() => this.scanStatus(id)),
      takeWhile(s => s.status === 'running', true),
      last()
    );
  }

  listScans(limit = 50, offset = 0): Observable<any[]> {
    return this.http.get<any[]>(`${API}/scans`, { params: { limit, offset } });
  }

  scansCount(): Observable<{ total: number }> {
    return this.http.get<{ total: number }>(`${API}/scans/count`);
  }

  deleteScan(id: string): Observable<any> {
    return this.http.delete(`${API}/scans/${id}`);
  }

  getScan(id: string): Observable<any> { return this.http.get(`${API}/scans/${id}`); }
  compareScans(a: string, b: string): Observable<any> {
    return this.http.get(`${API}/scans/compare/${a}/${b}`);
  }
  dashboard(id: string): Observable<any> { return this.http.get(`${API}/scans/${id}/dashboard`); }
  graph(id: string): Observable<any> { return this.http.get(`${API}/scans/${id}/graph`); }

  export(id: string, format: string): Observable<ExportResponse> {
    return this.http.post<ExportResponse>(`${API}/scans/${id}/export`, { format });
  }

  downloadExport(id: string, format: string): Observable<Blob> {
    return this.http.get(`${API}/scans/${id}/export/${format}/download`, {
      responseType: 'blob',
    });
  }
}
