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

      <div class="card explain" *ngIf="scan.risk_explanation">
        <div class="card-header"><mat-icon>insights</mat-icon><h3>Exposure score explanation</h3></div>
        <p class="muted">{{ scan.risk_explanation.disclaimer }}</p>
        <ul>
          <li *ngFor="let r of scan.risk_explanation.reasons">{{ r }}</li>
        </ul>
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

      <div class="card intel" *ngIf="intelLoading">
        <mat-icon>hourglass_top</mat-icon> Building deep intelligence…
      </div>

      <div class="card intel" *ngIf="intel">
        <div class="card-header"><mat-icon>psychology</mat-icon><h3>Deep Intelligence</h3>
          <button type="button" class="btn-secondary sm" (click)="loadIntel(true)">Refresh</button>
        </div>
        <p class="muted">Identity hypotheses are not factual ownership claims. Stay dates stay separate from review dates.</p>

        <h4>Identity hypotheses</h4>
        <ul class="intel-list" *ngIf="intel.hypotheses?.length; else noHyp">
          <li *ngFor="let h of intel.hypotheses">
            <strong>{{ h.candidate_value }}</strong>
            <span class="verify-badge">{{ h.status }}</span>
            <span class="muted"> conf {{ h.confidence }}</span>
            <div class="snippet">{{ (h.reasons || []).join(' · ') }}</div>
          </li>
        </ul>
        <ng-template #noHyp><p class="muted">No hypotheses yet.</p></ng-template>

        <h4>Timeline</h4>
        <div class="filters timeline-filters" *ngIf="allTimelineEntries.length">
          <select [(ngModel)]="tlEventType">
            <option value="">All event types</option>
            <option *ngFor="let t of timelineEventTypes" [value]="t">{{ t }}</option>
          </select>
          <select [(ngModel)]="tlPlatform">
            <option value="">All platforms</option>
            <option *ngFor="let p of timelinePlatforms" [value]="p">{{ p }}</option>
          </select>
          <select [(ngModel)]="tlVerification">
            <option value="">All verification</option>
            <option *ngFor="let v of timelineVerifications" [value]="v">{{ v }}</option>
          </select>
          <select [(ngModel)]="tlOrigin">
            <option value="">Observed + derived</option>
            <option value="observed">Observed</option>
            <option value="derived">Derived</option>
          </select>
          <input type="number" step="0.1" min="0" max="1" [(ngModel)]="tlMinConfidence" placeholder="Min conf" />
          <input [(ngModel)]="tlLocation" placeholder="Location filter" />
          <input type="date" [(ngModel)]="tlDateFrom" title="From date" />
          <input type="date" [(ngModel)]="tlDateTo" title="To date" />
        </div>
        <ul class="intel-list" *ngIf="filteredTimelineDated.length; else noTl">
          <li *ngFor="let e of filteredTimelineDated">
            <strong>{{ e.date_label }}</strong>
            <span class="muted"> ({{ e.precision }})</span>
            — {{ e.event_type }}: {{ e.description }}
            <span class="verify-badge">{{ e.verification_label }}</span>
            <span class="muted" *ngIf="e.independent_observations"> · {{ e.independent_observations }} indep.</span>
            <div class="tl-nav">
              <button type="button" class="linkish" *ngIf="e.evidence_ids?.length" (click)="focusEvidence(e)">Evidence</button>
              <button type="button" class="linkish" *ngIf="e.hypothesis_id" (click)="focusHypothesis(e.hypothesis_id)">Identity</button>
              <button type="button" class="linkish" (click)="focusJournalForEvent(e)">Journal</button>
              <a *ngIf="e.source_url" [href]="e.source_url" target="_blank" rel="noopener">Source</a>
            </div>
          </li>
        </ul>
        <ng-template #noTl><p class="muted">No dated timeline events.</p></ng-template>
        <div *ngIf="filteredTimelineUnknown.length">
          <h4>Unknown-date events</h4>
          <ul class="intel-list">
            <li *ngFor="let e of filteredTimelineUnknown">
              {{ e.event_type }}: {{ e.description }}
              <span class="verify-badge">{{ e.verification_label }}</span>
              <div class="tl-nav">
                <button type="button" class="linkish" (click)="focusJournalForEvent(e)">Journal</button>
              </div>
            </li>
          </ul>
        </div>

        <h4 id="journal-section">Investigation Journal</h4>
        <ol class="intel-list journal" *ngIf="intel.journal?.steps?.length">
          <li *ngFor="let s of intel.journal.steps" [class.hl]="s.id === focusedJournalStepId" [id]="'journal-' + s.id">
            <strong>{{ s.step_type }}</strong> — {{ s.reason }}
            <span class="muted" *ngIf="s.status !== 'ok'"> [{{ s.status }}]</span>
          </li>
        </ol>
        <p class="muted" *ngIf="focusedJournalStepId && journalTrail.length">
          Trail: {{ journalTrailLabels }}
        </p>
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
              <tr><th>Where</th><th>What</th><th>Source</th><th>Verify</th><th>Risk</th><th>Recommendation</th></tr>
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
                  <p class="snippet reason" *ngIf="f.risk_reason">{{ f.risk_reason }}</p>
                </td>
                <td>{{ f.source }}</td>
                <td><span class="verify-badge">{{ f.verification || f.outcome || '—' }}</span></td>
                <td><span class="risk-badge" [class]="'risk-' + f.risk_level">{{ f.risk_level }}</span></td>
                <td class="rec">{{ f.recommendation || '—' }}</td>
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
    .explain { margin-bottom: 1rem; padding: 1rem 1.25rem; }
    .explain ul { margin: 0.5rem 0 0; padding-left: 1.2rem; color: var(--cm-muted); font-size: 0.9rem; }
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
    .snippet.reason { font-style: italic; }
    .rec { font-size: 0.85rem; max-width: 220px; }
    .muted { color: var(--cm-muted); }
    .loading, .error { padding: 2rem; text-align: center; color: var(--cm-muted); }
    .intel { margin-bottom: 1rem; padding: 1rem 1.25rem; }
    .intel h4 { margin: 1rem 0 0.4rem; font-size: 0.95rem; }
    .intel-list { margin: 0.35rem 0 0; padding-left: 1.2rem; font-size: 0.9rem; }
    .intel-list.journal { padding-left: 1.4rem; }
    .btn-secondary.sm { margin-left: auto; padding: 0.25rem 0.6rem; font-size: 0.8rem; }
    .timeline-filters { margin: 0.5rem 0 0.75rem; }
    .tl-nav { display: flex; gap: 0.65rem; flex-wrap: wrap; margin-top: 0.25rem; font-size: 0.8rem; }
    .tl-nav a, button.linkish {
      background: none; border: none; color: var(--cm-accent); cursor: pointer; padding: 0;
      font: inherit; text-decoration: underline;
    }
    .intel-list .hl { background: color-mix(in srgb, var(--cm-accent) 18%, transparent); border-radius: 4px; padding: 0.15rem 0.25rem; }
    @media (max-width: 900px) { .meta-grid { grid-template-columns: 1fr 1fr; } }
  `],
})
export class ScanDetailComponent implements OnInit {
  scanId = '';
  scan: any = null;
  intel: any = null;
  intelLoading = false;
  loading = true;
  error = '';
  filterText = '';
  filterSource = '';
  filterRisk = '';
  tlEventType = '';
  tlPlatform = '';
  tlVerification = '';
  tlOrigin = '';
  tlMinConfidence: number | null = null;
  tlLocation = '';
  tlDateFrom = '';
  tlDateTo = '';
  focusedJournalStepId = '';
  focusedEvidenceIds: string[] = [];
  journalTrail: any[] = [];

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
        this.loadIntel(false);
      },
      error: () => {
        this.error = 'Scan not found — it may have been deleted';
        this.loading = false;
      },
    });
  }

  loadIntel(refresh: boolean) {
    this.intelLoading = true;
    this.api.intelligence(this.scanId, refresh).subscribe({
      next: (data) => {
        this.intel = data;
        this.intelLoading = false;
      },
      error: () => {
        this.intelLoading = false;
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
      if (this.focusedEvidenceIds.length) {
        const id = f.id || f.evidence_id;
        if (id && !this.focusedEvidenceIds.includes(id)) {
          // Soft-focus: still show when evidence ids are artifact-linked only.
        }
      }
      if (this.filterText) {
        const t = this.filterText.toLowerCase();
        const hay = `${f.platform} ${f.title} ${f.url} ${f.snippet}`.toLowerCase();
        if (!hay.includes(t)) return false;
      }
      return true;
    });
  }

  get allTimelineEntries(): any[] {
    const dated = this.intel?.timeline?.dated ?? [];
    const unknown = this.intel?.timeline?.unknown_date ?? [];
    return [...dated, ...unknown];
  }

  get timelineEventTypes(): string[] {
    return [...new Set(this.allTimelineEntries.map((e) => e.event_type).filter(Boolean))];
  }

  get timelinePlatforms(): string[] {
    return [...new Set(this.allTimelineEntries.map((e) => e.platform).filter(Boolean))];
  }

  get timelineVerifications(): string[] {
    return [...new Set(this.allTimelineEntries.map((e) => e.verification_label).filter(Boolean))];
  }

  private timelinePasses(e: any): boolean {
    if (this.tlEventType && e.event_type !== this.tlEventType) return false;
    if (this.tlPlatform && e.platform !== this.tlPlatform) return false;
    if (this.tlVerification && e.verification_label !== this.tlVerification) return false;
    if (this.tlOrigin && e.origin !== this.tlOrigin) return false;
    if (this.tlMinConfidence != null && Number(e.confidence) < Number(this.tlMinConfidence)) return false;
    if (this.tlLocation && !(e.location || '').toLowerCase().includes(this.tlLocation.toLowerCase())) return false;
    if (this.tlDateFrom || this.tlDateTo) {
      if (e.unknown_date) return false;
      const label = e.date_label || '';
      let iso = label;
      if (/^\d{4}$/.test(label)) iso = `${label}-01-01`;
      else if (/^\d{4}-\d{2}$/.test(label)) iso = `${label}-01`;
      if (this.tlDateFrom && iso < this.tlDateFrom) return false;
      if (this.tlDateTo && iso > this.tlDateTo) return false;
    }
    return true;
  }

  get filteredTimelineDated(): any[] {
    return (this.intel?.timeline?.dated ?? []).filter((e: any) => this.timelinePasses(e));
  }

  get filteredTimelineUnknown(): any[] {
    return (this.intel?.timeline?.unknown_date ?? []).filter((e: any) => this.timelinePasses(e));
  }

  get journalTrailLabels(): string {
    return this.journalTrail.map((s) => s.step_type).join(' → ');
  }

  focusEvidence(entry: any) {
    this.focusedEvidenceIds = [...(entry.evidence_ids || [])];
    const el = document.querySelector('.card .card-header mat-icon');
    // Scroll toward evidence table.
    document.querySelector('.data-table')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  focusHypothesis(hypothesisId: string) {
    const hyp = (this.intel?.hypotheses || []).find((h: any) => h.id === hypothesisId);
    if (hyp) {
      this.filterText = hyp.candidate_value || '';
    }
    document.querySelector('.intel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  focusJournalForEvent(entry: any) {
    const steps = this.intel?.journal?.steps || [];
    const hit =
      steps.find((s: any) => (s.output_refs || []).includes(entry.event_id)) ||
      steps.find((s: any) => (s.input_refs || []).some((id: string) => (entry.evidence_ids || []).includes(id))) ||
      steps.find((s: any) => s.step_type === 'conclusion');
    this.focusedJournalStepId = hit?.id || '';
    this.journalTrail = this.buildTrail(this.focusedJournalStepId);
    document.getElementById('journal-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    if (this.focusedJournalStepId) {
      document.getElementById('journal-' + this.focusedJournalStepId)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  private buildTrail(stepId: string): any[] {
    const steps: any[] = this.intel?.journal?.steps || [];
    if (!stepId) return [];
    const byId = new Map<string, any>(steps.map((s: any) => [s.id, s]));
    const start = byId.get(stepId);
    if (!start) return [];
    const out: any[] = [start];
    const seen = new Set<string>([start.id]);
    let queue: string[] = [...(start.parent_ids || [])];
    while (queue.length) {
      const pid = queue.shift() as string;
      const parent = byId.get(pid);
      if (!parent || seen.has(parent.id)) continue;
      seen.add(parent.id);
      out.push(parent);
      queue.push(...(parent.parent_ids || []));
    }
    return out.reverse();
  }

  riskClass(score: number): string {
    if (score >= 70) return 'risk-Critical';
    if (score >= 50) return 'risk-High';
    if (score >= 30) return 'risk-Medium';
    return 'risk-Low';
  }
}
