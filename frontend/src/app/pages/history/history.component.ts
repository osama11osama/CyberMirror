import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../services/api.service';

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
      <button class="btn-secondary" (click)="compareResult = null">Close</button>
    </div>

    <div class="card" *ngIf="scans.length">
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
            <td>{{ s.created_at | date:'medium' }}</td>
            <td class="subject">{{ s.profile.full_name || s.profile.username || s.profile.email || '—' }}</td>
            <td>{{ s.finding_count }}</td>
            <td><span class="risk-badge" [class]="riskClass(s.risk_score)">{{ s.risk_score }}</span></td>
            <td>{{ s.status }}</td>
            <td class="actions" (click)="$event.stopPropagation()">
              <a class="btn-link primary" [routerLink]="['/scan', s.id]">View</a>
              <a class="btn-link" [routerLink]="['/graph', s.id]">Graph</a>
              <a class="btn-link" [routerLink]="['/reports', s.id]">Report</a>
            </td>
          </tr>
        </tbody>
      </table>
      <button class="btn-primary" style="margin-top:1rem" (click)="compare()" [disabled]="selected.length !== 2">
        Compare 2 selected scans
      </button>
    </div>

    <div class="card empty-state" *ngIf="!scans.length">
      <mat-icon>history</mat-icon>
      <h3>No scan history</h3>
      <p>Completed scans are saved automatically in SQLite on your machine</p>
      <a routerLink="/investigate" class="btn-primary">Start Investigation</a>
    </div>
  `,
  styles: [`
    .compare-panel { margin-bottom: 1rem; }
    .scan-row { cursor: pointer; transition: background 0.15s; }
    .scan-row:hover { background: rgba(56, 139, 253, 0.08); }
    .subject { font-weight: 500; color: var(--cm-text); }
    .actions { white-space: nowrap; }
    .btn-link { margin-right: 0.6rem; color: var(--cm-accent); text-decoration: none; font-size: 0.9rem; }
    .btn-link.primary { font-weight: 600; }
    .btn-link:hover { text-decoration: underline; }
  `],
})
export class HistoryComponent implements OnInit {
  scans: any[] = [];
  selected: string[] = [];
  compareResult: any = null;

  constructor(private api: ApiService, private router: Router) {}
  ngOnInit() { this.api.listScans().subscribe(s => this.scans = s); }

  openScan(id: string) {
    this.router.navigate(['/scan', id]);
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
