import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../services/api.service';

@Component({
  selector: 'cm-settings',
  standalone: true,
  imports: [CommonModule, FormsModule, MatIconModule],
  template: `
    <div class="page-header">
      <h1>Settings</h1>
      <p class="subtitle">Configure scan depth, browser engine, and scheduled rescans</p>
    </div>

    <div class="grid">
      <div class="card wmn-banner" *ngIf="wmnWarning">
        <mat-icon>warning</mat-icon>
        <div>
          <strong>WhatsMyName database not loaded</strong>
          <p>{{ wmnWarning }}</p>
          <p class="muted">Set the correct path below to scan 600+ platforms.</p>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><mat-icon>tune</mat-icon><h3>Scan Configuration</h3></div>
        <div class="form-field">
          <label>Username platforms limit</label>
          <input type="number" [(ngModel)]="cfg.username_scan_limit" min="50" max="800" />
        </div>
        <div class="form-field">
          <label>Web search queries</label>
          <input type="number" [(ngModel)]="cfg.web_search_max_queries" min="5" max="50" />
        </div>
        <div class="form-field">
          <label>Results per query</label>
          <input type="number" [(ngModel)]="cfg.web_search_results_per_query" min="3" max="15" />
        </div>
        <div class="form-field">
          <label>WMN data path</label>
          <input [(ngModel)]="cfg.wmn_data_path" />
        </div>
        <div class="form-field">
          <label>Cache TTL (seconds)</label>
          <input type="number" [(ngModel)]="cfg.cache_ttl_seconds" min="300" />
        </div>
        <label class="check-row">
          <input type="checkbox" [(ngModel)]="cfg.playwright_enabled" />
          Enable Playwright browser (Facebook, Instagram, LinkedIn)
        </label>
        <div class="form-field">
          <label>HIBP API key (optional — for breach checks)</label>
          <input [(ngModel)]="cfg.hibp_api_key" type="password" placeholder="Leave empty for web fallback" />
        </div>
        <button class="btn-primary" (click)="save()" [disabled]="saving">{{ saving ? 'Saving…' : 'Save Settings' }}</button>
        <p class="success" *ngIf="saved">Settings saved.</p>
      </div>

      <div class="card">
        <div class="card-header"><mat-icon>schedule</mat-icon><h3>Scheduled Rescan</h3></div>
        <p class="muted">Automatically rescan the last profile on an interval.</p>
        <label class="check-row">
          <input type="checkbox" [(ngModel)]="cfg.schedule_enabled" />
          Enable scheduled scans
        </label>
        <div class="form-field">
          <label>Interval (hours)</label>
          <input type="number" [(ngModel)]="cfg.schedule_interval_hours" min="24" />
          <small class="muted">168 = weekly</small>
        </div>

        <div class="card-header" style="margin-top:1.5rem"><mat-icon>checklist</mat-icon><h3>Modules</h3></div>
        <p class="error" *ngIf="loadError">{{ loadError }}</p>
        <div class="module-row" *ngFor="let m of modules">
          <strong>{{ m.name }}</strong>
          <span class="active">● Active</span>
          <small>{{ m.description }}</small>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
    .wmn-banner { grid-column: 1 / -1; display: flex; gap: 1rem; align-items: flex-start; background: rgba(210,153,34,0.12); border: 1px solid #d29922; }
    .wmn-banner mat-icon { color: #d29922; }
    .form-field { margin-bottom: 1rem; }
    .form-field label { display: block; margin-bottom: 0.35rem; color: var(--cm-muted); font-size: 0.85rem; }
    .form-field input { width: 100%; padding: 0.5rem; background: var(--cm-surface-2); border: 1px solid var(--cm-border); border-radius: 6px; color: var(--cm-text); }
    .check-row { display: flex; gap: 0.5rem; align-items: center; margin: 1rem 0; color: var(--cm-text); }
    .muted { color: var(--cm-muted); font-size: 0.9rem; }
    .success { color: var(--cm-low); margin-top: 0.75rem; }
    .error { color: var(--cm-critical); }
    .module-row { padding: 0.75rem 0; border-bottom: 1px solid var(--cm-border-light); }
    .module-row small { display: block; color: var(--cm-muted); margin-top: 4px; }
    .active { color: var(--cm-low); font-size: 0.85rem; }
    @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
  `],
})
export class SettingsComponent implements OnInit {
  modules: any[] = [];
  loadError = '';
  cfg: any = {
    username_scan_limit: 600,
    web_search_max_queries: 30,
    web_search_results_per_query: 8,
    wmn_data_path: '',
    playwright_enabled: true,
    hibp_api_key: '',
    schedule_enabled: false,
    schedule_interval_hours: 168,
    cache_ttl_seconds: 3600,
  };
  saving = false;
  saved = false;
  wmnWarning = '';

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.health().subscribe({
      next: h => {
        const wmn = h.wmn;
        if (wmn && !wmn.loaded) this.wmnWarning = wmn.message || 'WMN file missing';
      },
    });
    this.api.settings().subscribe({ next: s => this.cfg = { ...this.cfg, ...s } });
    this.api.modules().subscribe({
      next: m => { if (m?.length) this.modules = m; },
      error: () => this.loadError = 'Backend offline',
    });
  }

  save() {
    this.saving = true;
    this.saved = false;
    this.api.updateSettings(this.cfg).subscribe({
      next: () => { this.saving = false; this.saved = true; },
      error: () => { this.saving = false; },
    });
  }
}
