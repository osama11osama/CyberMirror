import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../services/api.service';
import { asUtcDate } from '../../utils/dates';

@Component({
  selector: 'cm-history',
  standalone: true,
  imports: [CommonModule, RouterLink, MatIconModule],
  template: `
    <div class="page-header">
      <h1>Scan History</h1>
      <p class="subtitle">All scans saved locally — click any row to view full results without re-scanning</p>
    </div>

    <div class="card compare-panel" *ngIf="compareResult">
      <div class="card-header"><mat-icon>compare</mat-icon><h3>Comparison Result</h3></div>
      <p><strong>{{ compareResult.new_findings?.length || 0 }}</strong> new ·
         <strong>{{ compareResult.removed_findings?.length || 0 }}</strong> removed ·
         <strong>{{ compareResult.unchanged_count }}</strong> unchanged</p>
      <div class="compare-lists" *ngIf="compareResult.new_findings?.length">
        <h4>New findings</h4>
        <ul>
          <li *ngFor="let f of compareResult.new_findings | slice:0:10">{{ f.platform }} — {{ f.title }}</li>
        </ul>
      </div>
      <button class="btn-secondary" (click)="compareResult = null">Close</button>
    </div>

    <div class="card" *ngIf="scans.length || total > 0">
      <div class="pager-top">
        <span class="muted">{{ total }} scan(s) total</span>
        <div class="pager-btns">
          <button class="btn-secondary" (click)="prevPage()" [disabled]="offset === 0">← Prev</button>
          <span>Page {{ page }} / {{ totalPages }}</span>
          <button class="btn-secondary" (click)="nextPage()" [disabled]="offset + limit >= total">Next →</button>
        </div>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th></th>
            <th>Date</th>
            <th>Subject</th>
            <th>Findings</th>
            <th>Risk</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr *ngFor="let s of scans" class="scan-row" (click)="openScan(s.id)">
            <td (click)="$event.stopPropagation()">
              <input type="checkbox" [checked]="isSelected(s.id)" (change)="toggleSelect(s.id)" />
            </td>
            <td>{{ formatDate(s.created_at) | date:'medium' }}</td>
            <td class="subject">{{ s.profile.full_name || s.profile.username || s.profile.email || '—' }}</td>
            <td>{{ s.finding_count }}</td>
            <td><span class="risk-badge" [class]="riskClass(s.risk_score)">{{ s.risk_score }}</span></td>
            <td>{{ s.status }}</td>
            <td class="actions" (click)="$event.stopPropagation()">
              <a class="btn-link primary" [routerLink]="['/scan', s.id]">View</a>
              <a class="btn-link" [routerLink]="['/graph', s.id]">Graph</a>
              <a class="btn-link" [routerLink]="['/reports', s.id]">Report</a>
              <button class="btn-link danger" (click)="deleteScan(s.id, $event)">Delete</button>
            </td>
          </tr>
        </tbody>
      </table>
      <button class="btn-primary" style="margin-top:1rem" (click)="compare()" [disabled]="selected.length !== 2">
        Compare 2 selected scans
      </button>
    </div>

    <div class="card empty-state" *ngIf="!scans.length && !loading">
      <mat-icon>history</mat-icon>
      <h3>No scan history</h3>
      <p>Completed scans are saved automatically in SQLite on your machine</p>
      <a routerLink="/investigate" class="btn-primary">Start Investigation</a>
    </div>
  `,
  styles: [`
    .compare-panel { margin-bottom: 1rem; }
    .compare-lists { margin: 0.75rem 0; font-size: 0.9rem; }
    .compare-lists ul { margin: 0.25rem 0; padding-left: 1.25rem; color: var(--cm-muted); }
    .pager-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.5rem; }
    .pager-btns { display: flex; gap: 0.75rem; align-items: center; }
    .scan-row { cursor: pointer; transition: background 0.15s; }
    .scan-row:hover { background: rgba(56, 139, 253, 0.08); }
    .subject { font-weight: 500; color: var(--cm-text); }
    .actions { white-space: nowrap; }
    .btn-link { margin-right: 0.6rem; color: var(--cm-accent); text-decoration: none; font-size: 0.9rem; background: none; border: none; cursor: pointer; padding: 0; }
    .btn-link.primary { font-weight: 600; }
    .btn-link.danger { color: var(--cm-critical); }
    .btn-link:hover { text-decoration: underline; }
    .muted { color: var(--cm-muted); }
  `],
})
export class HistoryComponent implements OnInit {
  scans: any[] = [];
  selected: string[] = [];
  compareResult: any = null;
  total = 0;
  limit = 20;
  offset = 0;
  loading = true;

  constructor(private api: ApiService, private router: Router) {}

  formatDate(value: string) {
    return asUtcDate(value);
  }

  ngOnInit() { this.loadPage(); }

  get page() { return Math.floor(this.offset / this.limit) + 1; }
  get totalPages() { return Math.max(1, Math.ceil(this.total / this.limit)); }

  loadPage() {
    this.loading = true;
    this.api.scansCount().subscribe({
      next: c => {
        this.total = c.total;
        this.api.listScans(this.limit, this.offset).subscribe({
          next: s => { this.scans = s; this.loading = false; },
          error: () => { this.loading = false; },
        });
      },
      error: () => { this.loading = false; },
    });
  }

  prevPage() {
    if (this.offset >= this.limit) {
      this.offset -= this.limit;
      this.loadPage();
    }
  }

  nextPage() {
    if (this.offset + this.limit < this.total) {
      this.offset += this.limit;
      this.loadPage();
    }
  }

  openScan(id: string) {
    this.router.navigate(['/scan', id]);
  }

  deleteScan(id: string, ev: Event) {
    ev.stopPropagation();
    if (!confirm('Delete this scan and all its findings?')) return;
    this.api.deleteScan(id).subscribe({
      next: () => {
        this.selected = this.selected.filter(x => x !== id);
        this.loadPage();
      },
    });
  }

  isSelected(id: string) { return this.selected.includes(id); }
  toggleSelect(id: string) {
    const i = this.selected.indexOf(id);
    if (i >= 0) this.selected.splice(i, 1);
    else if (this.selected.length < 2) this.selected.push(id);
  }
  compare() {
    if (this.selected.length !== 2) return;
    this.api.compareScans(this.selected[0], this.selected[1]).subscribe(r => this.compareResult = r);
  }
  riskClass(score: number): string {
    if (score >= 70) return 'risk-Critical';
    if (score >= 50) return 'risk-High';
    if (score >= 30) return 'risk-Medium';
    return 'risk-Low';
  }
}
