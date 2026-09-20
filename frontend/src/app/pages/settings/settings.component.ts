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
      <p class="subtitle">Configure scan depth, modules, and security</p>
    </div>

    <div class="grid">
      <div class="card wmn-banner" *ngIf="wmnWarning">
        <mat-icon>warning</mat-icon>
        <div>
          <strong>WhatsMyName database not loaded</strong>
          <p>{{ wmnWarning }}</p>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><mat-icon>tune</mat-icon><h3>Scan Configuration</h3></div>
        <div class="form-field">
          <label>Username platforms limit</label>
          <input type="number" [(ngModel)]="cfg.username_scan_limit" min="50" max="800" />
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
          Enable Playwright browser
        </label>
        <div class="form-field">
          <label>HIBP API key (breaches + paste dumps — stored encrypted locally)</label>
          <input [(ngModel)]="cfg.hibp_api_key" type="password" placeholder="Paste key — not shown after save" />
        </div>
        <div class="form-field">
          <label>Ahmia max results per scan</label>
          <input type="number" [(ngModel)]="cfg.ahmia_max_results" min="3" max="30" />
        </div>
        <button class="btn-primary" (click)="save()" [disabled]="saving">{{ saving ? 'Saving…' : 'Save Settings' }}</button>
        <button class="btn-secondary" style="margin-left:0.5rem" (click)="clearCache()">Clear cache</button>
        <p class="success" *ngIf="saved">Settings saved.</p>
        <p class="success" *ngIf="cacheMsg">{{ cacheMsg }}</p>
      </div>

      <div class="card">
        <div class="card-header"><mat-icon>checklist</mat-icon><h3>Enabled modules</h3></div>
        <p class="error" *ngIf="loadError">{{ loadError }}</p>
        <label class="module-row" *ngFor="let m of modules">
          <input type="checkbox" [checked]="isEnabled(m.id)" (change)="toggleModule(m.id)" />
          <div>
            <strong>{{ m.name }}</strong>
            <small>{{ m.description }}</small>
          </div>
        </label>
        <div class="card-header" style="margin-top:1.5rem"><mat-icon>schedule</mat-icon><h3>Scheduled Rescan</h3></div>
        <label class="check-row">
          <input type="checkbox" [(ngModel)]="cfg.schedule_enabled" />
          Enable scheduled scans
        </label>
        <p class="hint">Scheduled scans use the same Enabled modules list as manual scans.</p>
        <div class="form-field">
          <label>Interval (hours)</label>
          <input type="number" [(ngModel)]="cfg.schedule_interval_hours" min="24" />
        </div>
      </div>
    </div>
  `,
  styles: [`
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
    .wmn-banner { grid-column: 1 / -1; display: flex; gap: 1rem; background: rgba(210,153,34,0.12); border: 1px solid #d29922; padding: 1rem; border-radius: 8px; }
    .form-field { margin-bottom: 1rem; }
    .form-field label { display: block; margin-bottom: 0.35rem; color: var(--cm-muted); font-size: 0.85rem; }
    .form-field input, .form-field select { width: 100%; padding: 0.5rem; background: var(--cm-surface-2); border: 1px solid var(--cm-border); border-radius: 6px; color: var(--cm-text); }
    .check-row, .module-row { display: flex; gap: 0.75rem; align-items: flex-start; margin: 0.75rem 0; color: var(--cm-text); }
    .module-row small { display: block; color: var(--cm-muted); margin-top: 4px; }
    .hint { color: var(--cm-muted); font-size: 0.85rem; margin: 0.25rem 0 0.75rem; }
    .success { color: var(--cm-low); margin-top: 0.75rem; }
    .error { color: var(--cm-critical); }
    @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
  `],
})
export class SettingsComponent implements OnInit {
  modules: any[] = [];
  loadError = '';
  cacheMsg = '';
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
    ahmia_max_results: 10,
    ahmia_max_queries: 3,
    enabled_modules: [] as string[],
  };
  saving = false;
  saved = false;
  wmnWarning = '';

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.health().subscribe({
      next: h => { if (h.wmn && !h.wmn.loaded) this.wmnWarning = h.wmn.message; },
    });
    this.api.settings().subscribe({
      next: s => {
        this.cfg = { ...this.cfg, ...s, hibp_api_key: '' };
        if (!this.cfg.enabled_modules?.length) {
          this.cfg.enabled_modules = this.modules.map((m: any) => m.id);
        }
      },
    });
    this.api.modules().subscribe({
      next: m => {
        if (m?.length) {
          this.modules = m;
          if (!this.cfg.enabled_modules?.length) {
            this.cfg.enabled_modules = m.filter((x: any) => x.enabled !== false).map((x: any) => x.id);
          }
        }
      },
      error: () => this.loadError = 'Backend offline',
    });
  }

  isEnabled(id: string) {
    return (this.cfg.enabled_modules || []).includes(id);
  }

  toggleModule(id: string) {
    const list: string[] = [...(this.cfg.enabled_modules || [])];
    const i = list.indexOf(id);
    if (i >= 0) list.splice(i, 1); else list.push(id);
    this.cfg.enabled_modules = list;
  }

  save() {
    this.saving = true;
    this.saved = false;
    this.api.updateSettings(this.cfg).subscribe({
      next: () => { this.saving = false; this.saved = true; this.cfg.hibp_api_key = ''; },
      error: () => { this.saving = false; },
    });
  }

  clearCache() {
    this.api.clearCache().subscribe(r => {
      this.cacheMsg = `Cleared ${r.cleared} cache entries`;
    });
  }
}
