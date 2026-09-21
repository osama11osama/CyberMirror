import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService, ExportResponse } from '../../services/api.service';

@Component({
  selector: 'cm-reports',
  standalone: true,
  imports: [CommonModule, RouterLink, MatIconModule],
  template: `
    <div class="page-header">
      <h1>Reports</h1>
      <p class="subtitle">Export professional audit reports</p>
    </div>

    <div class="card export-card">
      <div class="card-header"><mat-icon>description</mat-icon><h3>Export Formats</h3></div>
      <div class="export-grid">
        <button class="export-btn" (click)="export('html')">
          <mat-icon>html</mat-icon>
          <strong>HTML Report</strong>
          <small>Professional visual report</small>
        </button>
        <button class="export-btn" (click)="export('json')">
          <mat-icon>data_object</mat-icon>
          <strong>JSON</strong>
          <small>Machine-readable data</small>
        </button>
        <button class="export-btn" (click)="export('csv')">
          <mat-icon>table_chart</mat-icon>
          <strong>CSV</strong>
          <small>Spreadsheet export</small>
        </button>
        <button class="export-btn" (click)="export('pdf')">
          <mat-icon>picture_as_pdf</mat-icon>
          <strong>PDF / Print</strong>
          <small>HTML report — print to PDF</small>
        </button>
      </div>
      <p class="msg success" *ngIf="message">{{ message }}</p>

      <div class="intel-box" *ngIf="summary">
        <h3>Intelligence summary</h3>
        <p class="muted">{{ summary.disclaimer }}</p>
        <p>
          Identity hypotheses: {{ summary.identity_summary?.length || 0 }} ·
          Travel events: {{ summary.travel_exposure?.length || 0 }} ·
          Journal steps: {{ summary.journal_step_count || 0 }}
        </p>
        <ul *ngIf="summary.identity_summary?.length">
          <li *ngFor="let h of summary.identity_summary">
            {{ h.candidate }} — <em>{{ h.status }}</em> ({{ h.confidence }})
          </li>
        </ul>
      </div>

      <a class="btn-secondary" [routerLink]="['/graph', scanId]" style="margin-top:1rem">Back to Graph</a>
    </div>
  `,
  styles: [`
    .export-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; }
    .export-btn {
      display: flex; flex-direction: column; align-items: center; gap: 0.5rem;
      padding: 1.5rem; background: var(--cm-bg); border: 1px solid var(--cm-border);
      border-radius: 10px; cursor: pointer; color: var(--cm-text); transition: border-color 0.2s;
    }
    .export-btn:hover { border-color: var(--cm-accent); }
    .export-btn mat-icon { font-size: 32px; width: 32px; height: 32px; color: var(--cm-accent); }
    .export-btn small { color: var(--cm-muted); }
    .msg.success { color: var(--cm-low); margin-top: 1rem; }
    .intel-box { margin-top: 1.25rem; padding-top: 1rem; border-top: 1px solid var(--cm-border); }
    .muted { color: var(--cm-muted); font-size: 0.9rem; }
  `],
})
export class ReportsComponent implements OnInit {
  scanId = '';
  message = '';
  summary: any = null;

  constructor(private route: ActivatedRoute, private api: ApiService) {}

  ngOnInit() {
    this.scanId = this.route.snapshot.paramMap.get('scanId') ?? '';
    if (!this.scanId) return;
    this.api.intelligence(this.scanId).subscribe({
      next: (intel) => {
        this.summary = {
          disclaimer:
            'Identity hypotheses are not factual identity assertions. Possible/unresolved candidates must not be treated as confirmed ownership.',
          identity_summary: (intel?.hypotheses || []).map((h: any) => ({
            candidate: h.candidate_value,
            status: h.status,
            confidence: h.confidence,
          })),
          travel_exposure: (intel?.bundle?.events || []).filter((e: any) => e.type === 'travel'),
          journal_step_count: intel?.journal?.steps?.length || 0,
        };
      },
    });
  }

  export(format: string) {
    this.api.export(this.scanId, format).subscribe((res: ExportResponse) => {
      this.message = `Exported ${format.toUpperCase()} → ${res.path}`;
      this.api.downloadExport(this.scanId, format).subscribe((blob: Blob) => {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = `cybermirror_${this.scanId.slice(0, 8)}.${format}`;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      });
    });
  }
}
