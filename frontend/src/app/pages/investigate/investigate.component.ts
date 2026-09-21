import { Component, OnInit, OnDestroy } from '@angular/core';

import { CommonModule } from '@angular/common';

import { FormsModule } from '@angular/forms';

import { RouterLink } from '@angular/router';

import { MatIconModule } from '@angular/material/icon';

import { MatProgressBarModule } from '@angular/material/progress-bar';

import { Subscription, interval, switchMap } from 'rxjs';

import { ApiService, IdentityProfile, ScanStatus } from '../../services/api.service';

const PROFILE_KEY = 'cybermirror_profile';



const DEFAULT_SELECTED = [

  'web_search', 'username_scan', 'social_browser', 'email_scan',

  'phone_scan', 'credential_leaks', 'ahmia_search', 'domain_scan', 'identity_correlator',

];

const CONSENT_KEY = 'cybermirror_consent_v1';



@Component({

  selector: 'cm-investigate',

  standalone: true,

  imports: [CommonModule, FormsModule, RouterLink, MatIconModule, MatProgressBarModule],

  template: `

    <div class="consent-overlay" *ngIf="showConsent">

      <div class="consent-card card">

        <mat-icon>gavel</mat-icon>

        <h2>Legal &amp; Ethical Use</h2>

        <p>CyberMirror searches <strong>public</strong> data only. Use it for <strong>self-audit</strong> or with explicit permission from the subject.</p>

        <ul>

          <li>Do not use for harassment, stalking, or unauthorized surveillance</li>

          <li>Results are stored locally on your machine</li>

          <li>You are responsible for compliance with local laws</li>

        </ul>

        <button class="btn-primary" (click)="acceptConsent()">I understand — continue</button>

      </div>

    </div>



    <div class="page-header">

      <h1>Investigation Workspace</h1>

      <p class="subtitle">Full scan — 600+ sites, credential leaks, Ahmia Tor index, browser checks</p>

    </div>



    <div class="backend-banner" *ngIf="!backendOk">

      <mat-icon>cloud_off</mat-icon>

      <div><strong>Backend not connected</strong><p>Run <code>CyberMirror.bat</code> and keep the window open</p></div>

    </div>



    <div class="workspace">

      <div class="panel card">

        <div class="card-header"><mat-icon>person_search</mat-icon><h3>Identity Profile</h3></div>

        <p class="hint">Fill everything you know — more fields = more results.</p>

        <div class="form-grid">

          <div class="form-field"><label>Full Name</label><input [(ngModel)]="profile.full_name" placeholder="Jane Doe" /></div>

          <div class="form-field"><label>Username</label><input [(ngModel)]="profile.username" placeholder="janedoe" /></div>

          <div class="form-field"><label>Email</label><input [(ngModel)]="profile.email" type="email" /></div>

          <div class="form-field"><label>Phone</label><input [(ngModel)]="profile.phone" placeholder="+1 555-0100" /></div>

          <div class="form-field"><label>Location</label><input [(ngModel)]="profile.location" /></div>

          <div class="form-field"><label>Website</label><input [(ngModel)]="profile.website" placeholder="https://..." /></div>

          <div class="form-field full"><label>Company</label><input [(ngModel)]="profile.company" /></div>

        </div>



        <div class="card-header" style="margin-top:1.5rem"><mat-icon>memory</mat-icon><h3>Scan Modules</h3></div>

        <div class="provider-grid">

          <label class="provider-item" *ngFor="let m of nativeModules" [class.selected]="selected.includes(m.id)">

            <input type="checkbox" [checked]="selected.includes(m.id)" (change)="toggleModule(m.id)" />

            <div class="provider-info">

              <strong>{{ m.name }}</strong>

              <small>{{ m.description }}</small>

            </div>

          </label>

        </div>



        <div class="scan-progress" *ngIf="scanning">

          <mat-progress-bar mode="determinate" [value]="progress"></mat-progress-bar>

          <p class="msg">{{ progressMsg }}</p>

          <p class="msg muted" *ngIf="findingsSoFar">Found so far: {{ findingsSoFar }}</p>

          <div class="module-errors" *ngIf="moduleErrors.length">

            <strong>Module errors:</strong>

            <ul><li *ngFor="let e of moduleErrors">{{ e.module }} — {{ e.error }}</li></ul>

          </div>

          <button class="btn-secondary cancel-btn" (click)="cancelScan()">Cancel scan</button>

        </div>



        <button class="btn-secondary full-width" style="margin-top:0.5rem" (click)="saveProfile()">Save profile</button>



        <button class="btn-primary full-width" (click)="runScan()" [disabled]="scanning || !canScan() || !backendOk || showConsent">

          <mat-icon>{{ scanning ? 'hourglass_top' : 'radar' }}</mat-icon>

          {{ scanning ? 'Scanning… ' + progress + '%' : 'Run Full Scan' }}

        </button>

        <p class="hint warn" *ngIf="!backendOk">Start the backend (<code>CyberMirror.bat</code>) before scanning.</p>

        <p class="hint warn" *ngIf="backendOk && !canScan() && !scanning">
          Enter at least a name, username, email, phone, or website, and keep one module selected.
        </p>

        <p class="error" *ngIf="error">{{ error }}</p>

      </div>



      <div class="panel card results">

        <div class="card-header">

          <mat-icon>fact_check</mat-icon><h3>Evidence Center</h3>

          <span class="count-badge" *ngIf="filteredFindings.length">{{ filteredFindings.length }}</span>

          <span class="live-badge" *ngIf="scanning">● Live</span>

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



        <div class="scan-summary success" *ngIf="scanSummary && !scanning">

          <mat-icon>info</mat-icon><p>{{ scanSummary }}</p>

        </div>



        <div class="empty-state" *ngIf="!findings.length && !scanning && !scanSummary">

          <mat-icon>shield</mat-icon>

          <h3>Ready to scan</h3>

          <p>600+ platforms · credential leaks · Ahmia Tor · Playwright · web search · phone · WHOIS</p>

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

                  <br *ngIf="f.url"><a [href]="f.url" target="_blank" rel="noopener">{{ f.url | slice:0:55 }}</a>

                </td>

                <td>

                  <strong>{{ f.title }}</strong>

                  <p class="snippet" *ngIf="f.snippet">{{ f.snippet | slice:0:100 }}</p>

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



        <div class="result-actions" *ngIf="lastScanId && !scanning">

          <a class="btn-primary" [routerLink]="['/scan', lastScanId]">View Saved Results</a>

          <a class="btn-primary" [routerLink]="['/graph', lastScanId]">Graph</a>

          <a class="btn-secondary" [routerLink]="['/reports', lastScanId]">Export</a>

        </div>

      </div>

    </div>

  `,

  styles: [`

    .consent-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.75); z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 1rem; }

    .consent-card { max-width: 480px; padding: 2rem; text-align: center; }

    .consent-card mat-icon { font-size: 48px; width: 48px; height: 48px; color: var(--cm-accent); }

    .consent-card ul { text-align: left; margin: 1rem 0; color: var(--cm-muted); font-size: 0.9rem; }

    .workspace { display: grid; grid-template-columns: 420px 1fr; gap: 1.5rem; align-items: start; }

    .panel { max-height: calc(100vh - 180px); overflow-y: auto; }

    .full-width { width: 100%; margin-top: 1rem; justify-content: center; }

    .count-badge { margin-left: auto; background: var(--cm-accent); color: #fff; padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; }

    .live-badge { margin-left: 0.5rem; color: var(--cm-low); font-size: 0.75rem; animation: pulse 1.5s infinite; }

    @keyframes pulse { 50% { opacity: 0.5; } }

    .filters { display: flex; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap; }

    .filters input, .filters select { flex: 1; min-width: 120px; padding: 0.5rem; background: var(--cm-surface-2); border: 1px solid var(--cm-border); border-radius: 6px; color: var(--cm-text); }

    .table-wrap { overflow: auto; max-height: 480px; }

    .snippet { font-size: 0.85rem; color: var(--cm-muted); margin: 4px 0 0; }

    .snippet.reason { font-style: italic; }

    .rec { font-size: 0.85rem; max-width: 200px; color: var(--cm-text); }

    .hint, .muted { color: var(--cm-muted); }
    .hint.warn { color: #d29922; margin-top: 0.5rem; font-size: 0.85rem; }
    .error { color: var(--cm-critical); margin-top: 0.75rem; }

    .module-errors { margin-top: 0.75rem; font-size: 0.85rem; color: var(--cm-critical); }
    .module-errors ul { margin: 0.25rem 0 0; padding-left: 1.25rem; }

    .result-actions { display: flex; gap: 1rem; margin-top: 1.25rem; padding-top: 1rem; border-top: 1px solid var(--cm-border); }

    .backend-banner, .scan-summary { display: flex; gap: 0.75rem; padding: 0.75rem 1rem; border-radius: 8px; margin-bottom: 1rem; font-size: 0.9rem; }

    .backend-banner { background: rgba(248,81,73,0.12); border: 1px solid var(--cm-critical); }

    .scan-summary.success { background: rgba(63,185,80,0.1); border: 1px solid var(--cm-low); }

    @media (max-width: 1100px) { .workspace { grid-template-columns: 1fr; } }

  `],

})

export class InvestigateComponent implements OnInit, OnDestroy {

  profile: IdentityProfile = { full_name: '', username: '', email: '', phone: '', location: '', website: '', company: '' };

  nativeModules: any[] = [];

  selected = [...DEFAULT_SELECTED];

  findings: any[] = [];

  scanning = false;

  progress = 0;

  progressMsg = '';

  findingsSoFar = 0;

  error = '';

  scanSummary = '';

  lastScanId = '';

  backendOk = false;

  showConsent = false;

  filterText = '';

  filterSource = '';

  filterRisk = '';

  moduleErrors: { module: string; error: string }[] = [];

  private sub?: Subscription;

  private pollSub?: Subscription;

  private liveSub?: Subscription;

  private activeScanId = '';



  constructor(private api: ApiService) {}



  ngOnInit() {

    this.showConsent = !localStorage.getItem(CONSENT_KEY);

    const saved = localStorage.getItem(PROFILE_KEY);

    if (saved) {

      try { this.profile = { ...this.profile, ...JSON.parse(saved) }; } catch { /* ignore */ }

    }

    const savedMods = localStorage.getItem('cybermirror_modules');

    if (savedMods) {

      try { this.selected = JSON.parse(savedMods); } catch { /* ignore */ }

    }

    this.api.health().subscribe({ next: () => this.backendOk = true, error: () => this.backendOk = false });

    this.api.modules().subscribe({ next: m => { if (m?.length) this.nativeModules = m; } });

  }



  ngOnDestroy() {

    this.sub?.unsubscribe();

    this.pollSub?.unsubscribe();

    this.liveSub?.unsubscribe();

  }



  acceptConsent() {

    localStorage.setItem(CONSENT_KEY, '1');

    this.showConsent = false;

  }



  get realFindings() {

    return this.findings.filter(f => f.platform !== 'Summary' && f.platform !== 'System');

  }



  get sources() {

    return [...new Set(this.realFindings.map(f => f.source))];

  }



  get filteredFindings() {

    return this.realFindings.filter(f => {

      if (this.filterSource && f.source !== this.filterSource) return false;

      if (this.filterRisk && f.risk_level !== this.filterRisk) return false;

      if (this.filterText) {

        const t = this.filterText.toLowerCase();

        const hay = `${f.platform} ${f.title} ${f.url} ${f.snippet} ${f.recommendation}`.toLowerCase();

        if (!hay.includes(t)) return false;

      }

      return true;

    });

  }



  canScan() {

    const p = this.profile;

    return !!(p.username || p.email || p.full_name || p.phone || p.website) && this.selected.length > 0;

  }



  toggleModule(id: string) {

    const i = this.selected.indexOf(id);

    if (i >= 0) this.selected.splice(i, 1); else this.selected.push(id);

    localStorage.setItem('cybermirror_modules', JSON.stringify(this.selected));

  }



  saveProfile() {

    localStorage.setItem(PROFILE_KEY, JSON.stringify(this.profile));

  }



  cancelScan() {

    if (!this.activeScanId) return;

    this.api.cancelScan(this.activeScanId).subscribe({

      next: () => {

        this.progressMsg = 'Cancelling…';

        this.pollSub?.unsubscribe();

        this.liveSub?.unsubscribe();

        this.scanning = false;

        this.scanSummary = 'Scan cancelled.';

      },

    });

  }



  runScan() {

    if (this.showConsent) return;

    this.scanning = true;

    this.error = '';

    this.findings = [];

    this.scanSummary = '';

    this.progress = 0;

    this.findingsSoFar = 0;

    this.moduleErrors = [];
    this.progressMsg = 'Starting scan…';



    this.sub = this.api.startScan({ profile: this.profile, providers: this.selected }).subscribe({

      next: (started) => {

        this.lastScanId = started.id;

        this.activeScanId = started.id;



        this.liveSub = interval(2000).pipe(

          switchMap(() => this.api.liveFindings(started.id))

        ).subscribe({

          next: (res) => {

            if (res.findings?.length) {

              this.findings = res.findings;

              this.findingsSoFar = res.count;

            }

          },

        });



        this.pollSub = interval(1500).pipe(

          switchMap(() => this.api.scanStatus(started.id))

        ).subscribe({

          next: (st: ScanStatus) => {

            this.progress = st.progress || 0;

            this.progressMsg = st.message || st.status;

            this.findingsSoFar = st.findings_so_far || this.findingsSoFar;
            this.moduleErrors = st.module_errors || [];

            if (st.status === 'completed' || st.status === 'failed' || st.status === 'cancelled') {

              this.pollSub?.unsubscribe();

              this.liveSub?.unsubscribe();

              if (st.status === 'failed') {

                this.error = st.message || 'Scan failed';

                this.scanning = false;

                return;

              }

              if (st.status === 'cancelled') {

                this.scanning = false;

                this.scanSummary = 'Scan cancelled.';

                return;

              }

              this.api.getScan(started.id).subscribe({

                next: (res) => {

                  this.findings = res.findings ?? [];

                  this.scanning = false;

                  this.progress = 100;

                  const n = this.realFindings.length;

                  this.scanSummary = n

                    ? `Complete — ${n} finding(s) recorded with URLs and sources.`

                    : 'Complete — no public results. Try more fields or check Settings.';

                },

                error: () => { this.scanning = false; },

              });

            }

          },

          error: () => { this.error = 'Lost connection during scan'; this.scanning = false; },

        });

      },

      error: (e) => {

        this.error = e.error?.detail || e.message || 'Scan failed';

        this.scanning = false;

        this.backendOk = false;

      },

    });

  }

}

