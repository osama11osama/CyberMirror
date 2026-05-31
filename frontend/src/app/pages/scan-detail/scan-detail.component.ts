import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../services/api.service';

@Component({
  selector: 'cm-scan-detail',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, MatIconModule],
  template: `
    <div class="page-header">
      <h1>Saved Scan Results</h1>
      <p class="subtitle">Loaded from local history — no new search needed</p>
    </div>

    <div class="toolbar">
      <a class="btn-secondary" routerLink="/history"><mat-icon>arrow_back</mat-icon> History</a>
      <a class="btn-primary" [routerLink]="['/graph', scanId]"><mat-icon>hub</mat-icon> Graph</a>
      <a class="btn-secondary" [routerLink]="['/reports', scanId]"><mat-icon>description</mat-icon> Report</a>
    </div>

    <div class="loading card" *ngIf="loading">
      <mat-icon>hourglass_top</mat-icon> Loading saved scan…
    </div>

    <div class="error card" *ngIf="error">
      <mat-icon>error</mat-icon> {{ error }}
      <a routerLink="/history" class="btn-secondary" style="margin-top:1rem">Back to History</a>
    </div>

    <ng-container *ngIf="scan && !loading">
      <div class="meta-grid">
        <div class="card stat">
          <span class="label">Subject</span>
          <span class="value">{{ subjectLabel }}</span>
        </div>
        <div class="card stat">
          <span class="label">Date</span>
          <span class="value sm">{{ scan.created_at | date:'medium' }}</span>
        </div>
        <div class="card stat">
          <span class="label">Findings</span>
          <span class="value">{{ realFindings.length }}</span>
        </div>
        <div class="card stat">
          <span class="label">Risk Score</span>
          <span class="value risk-badge" [class]="riskClass(scan.risk_score)">{{ scan.risk_score }}</span>
        </div>
      </div>

      <div class="card profile-card">
        <div class="card-header"><mat-icon>person</mat-icon><h3>Profile searched</h3></div>
        <div class="profile-grid">
          <div *ngIf="scan.profile.full_name"><strong>Name</strong>{{ scan.profile.full_name }}</div>
          <div *ngIf="scan.profile.username"><strong>Username</strong>{{ scan.profile.username }}</div>
          <div *ngIf="scan.profile.email"><strong>Email</strong>{{ scan.profile.email }}</div>
          <div *ngIf="scan.profile.phone"><strong>Phone</strong>{{ scan.profile.phone }}</div>
          <div *ngIf="scan.profile.location"><strong>Location</strong>{{ scan.profile.location }}</div>
          <div *ngIf="scan.profile.website"><strong>Website</strong>{{ scan.profile.website }}</div>
          <div *ngIf="scan.profile.company"><strong>Company</strong>{{ scan.profile.company }}</div>
        </div>
        <p class="muted modules">Modules: {{ scan.providers?.join(', ') }}</p>
      </div>

      <div class="card">
        <div class="card-header">
          <mat-icon>fact_check</mat-icon>
          <h3>Evidence Center</h3>
          <span class="count-badge">{{ filteredFindings.length }}</span>
        </div>

        <div class="filters" *ngIf="realFindings.length">
          <input [(ngModel)]="filterText" placeholder="Filter results…" />
          <select [(ngModel)]="filterSource">
            <option value="">All sources</option>
            <option *ngFor="let s of sources" [value]="s">{{ s }}</option>
          </select>
          <select [(ngModel)]="filterRisk">
            <option value="">All risks</option>
            <option>Critical</option><option>High</option><option>Medium</option><option>Low</option><option>Info</option>
          </select>
        </div>

        <div class="empty-state" *ngIf="!realFindings.length">
          <mat-icon>search_off</mat-icon>
          <p>No findings saved for this scan</p>
        </div>

        <div class="table-wrap" *ngIf="filteredFindings.length">
          <table class="data-table">
            <thead>
              <tr><th>Where</th><th>What</th><th>Source</th><th>When</th><th>Risk</th></tr>
            </thead>
            <tbody>
              <tr *ngFor="let f of filteredFindings">
                <td>
                  <strong>{{ f.platform }}</strong>
                  <br *ngIf="f.url"><a [href]="f.url" target="_blank" rel="noopener">{{ f.url | slice:0:60 }}</a>
                </td>
                <td>
                  <strong>{{ f.title }}</strong>
                  <p class="snippet" *ngIf="f.snippet">{{ f.snippet | slice:0:120 }}</p>
                </td>
                <td>{{ f.source }}</td>
                <td class="muted">{{ f.timestamp | date:'short' }}</td>
                <td><span class="risk-badge" [class]="'risk-' + f.risk_level">{{ f.risk_level }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </ng-container>
  `,
  styles: [`
    .toolbar { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1rem; }
    .meta-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 1rem; }
    .stat { padding: 1rem 1.25rem; }
    .stat .label { display: block; font-size: 0.75rem; color: var(--cm-muted); text-transform: uppercase; margin-bottom: 0.35rem; }
    .stat .value { font-size: 1.35rem; font-weight: 600; }
    .stat .value.sm { font-size: 0.95rem; font-weight: 500; }
    .profile-card { margin-bottom: 1rem; }
    .profile-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.75rem 1.5rem; }
    .profile-grid strong { display: block; font-size: 0.7rem; color: var(--cm-muted); text-transform: uppercase; margin-bottom: 2px; }
    .modules { margin-top: 1rem; font-size: 0.85rem; }
    .count-badge { margin-left: auto; background: var(--cm-accent); color: #fff; padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; }
    .filters { display: flex; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap; }
    .filters input, .filters select { flex: 1; min-width: 120px; padding: 0.5rem; background: var(--cm-surface-2); border: 1px solid var(--cm-border); border-radius: 6px; color: var(--cm-text); }
    .table-wrap { overflow: auto; max-height: 520px; }
    .snippet { font-size: 0.85rem; color: var(--cm-muted); margin: 4px 0 0; }
    .muted { color: var(--cm-muted); }
    .loading, .error { padding: 2rem; text-align: center; color: var(--cm-muted); }
    @media (max-width: 900px) { .meta-grid { grid-template-columns: 1fr 1fr; } }
  `],
})
export class ScanDetailComponent implements OnInit {
  scanId = '';
  scan: any = null;
  loading = true;
  error = '';
  filterText = '';
  filterSource = '';
  filterRisk = '';

  constructor(private route: ActivatedRoute, private api: ApiService) {}

  ngOnInit() {
    this.scanId = this.route.snapshot.paramMap.get('scanId') ?? '';
    if (!this.scanId) {
      this.error = 'No scan ID provided';
      this.loading = false;
      return;
    }
    this.api.getScan(this.scanId).subscribe({
      next: (data) => {
        this.scan = data;
        this.loading = false;
      },
      error: () => {
        this.error = 'Scan not found — it may have been deleted';
        this.loading = false;
      },
    });
  }

  get subjectLabel(): string {
    if (!this.scan?.profile) return '—';
    const p = this.scan.profile;
    return p.full_name || p.username || p.email || p.phone || '—';
  }

  get realFindings() {
    return (this.scan?.findings ?? []).filter(
      (f: any) => f.platform !== 'Summary' && f.platform !== 'System'
    );
  }

  get sources() {
    return [...new Set(this.realFindings.map((f: any) => f.source))];
  }

  get filteredFindings() {
    return this.realFindings.filter((f: any) => {
      if (this.filterSource && f.source !== this.filterSource) return false;
      if (this.filterRisk && f.risk_level !== this.filterRisk) return false;
      if (this.filterText) {
        const t = this.filterText.toLowerCase();
        const hay = `${f.platform} ${f.title} ${f.url} ${f.snippet}`.toLowerCase();
        if (!hay.includes(t)) return false;
      }
      return true;
    });
  }

  riskClass(score: number): string {
    if (score >= 70) return 'risk-Critical';
    if (score >= 50) return 'risk-High';
    if (score >= 30) return 'risk-Medium';
    return 'risk-Low';
  }
}
