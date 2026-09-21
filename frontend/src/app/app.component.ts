import { Component, OnInit } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatListModule } from '@angular/material/list';
import { MatIconModule } from '@angular/material/icon';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatBadgeModule } from '@angular/material/badge';
import { CommonModule } from '@angular/common';
import { ApiService } from './services/api.service';
import { getApiToken, storeApiToken } from './services/auth.interceptor';

@Component({
  selector: 'cm-root',
  standalone: true,
  imports: [
    CommonModule, RouterOutlet, RouterLink, RouterLinkActive,
    MatSidenavModule, MatListModule, MatIconModule, MatToolbarModule, MatBadgeModule,
  ],
  template: `
    @if (needsUnlock) {
      <div class="unlock-gate">
        <div class="unlock-card">
          <div class="unlock-brand">
            <mat-icon>shield</mat-icon>
            <strong>CyberMirror</strong>
          </div>
          <h1>Unlock local API access</h1>
          <p>
            Authentication is enabled. Paste the API token from
            <code>data/.api_token</code>
            (Docker:
            <code>docker compose exec cybermirror cat /app/data/.api_token</code>),
            or open the UI with <code>#api_token=&lt;token&gt;</code>.
          </p>
          <label class="unlock-label" for="api-token-input">API token</label>
          <input
            id="api-token-input"
            class="unlock-input"
            type="password"
            autocomplete="off"
            [value]="unlockDraft"
            (input)="unlockDraft = $any($event.target).value"
            (keydown.enter)="submitUnlock()"
          />
          @if (unlockError) {
            <p class="unlock-error">{{ unlockError }}</p>
          }
          <button type="button" class="unlock-btn" (click)="submitUnlock()" [disabled]="unlockBusy">
            {{ unlockBusy ? 'Checking…' : 'Unlock' }}
          </button>
        </div>
      </div>
    } @else {
      <mat-sidenav-container class="layout">
        <mat-sidenav mode="side" opened class="sidebar">
          <div class="brand">
            <div class="logo"><mat-icon>shield</mat-icon></div>
            <div class="brand-text">
              <strong>CyberMirror</strong>
              <span>See Yourself as the Internet Sees You</span>
            </div>
          </div>

          <mat-nav-list class="nav-list">
            <a mat-list-item routerLink="/dashboard" routerLinkActive="active" [routerLinkActiveOptions]="{exact:true}">
              <mat-icon matListItemIcon>dashboard</mat-icon>
              <span matListItemTitle>Dashboard</span>
            </a>
            <a mat-list-item routerLink="/investigate" routerLinkActive="active">
              <mat-icon matListItemIcon>manage_search</mat-icon>
              <span matListItemTitle>Investigation</span>
            </a>
            <a mat-list-item routerLink="/history" routerLinkActive="active">
              <mat-icon matListItemIcon>history</mat-icon>
              <span matListItemTitle>History</span>
            </a>
            <a mat-list-item routerLink="/settings" routerLinkActive="active">
              <mat-icon matListItemIcon>tune</mat-icon>
              <span matListItemTitle>Settings</span>
            </a>
          </mat-nav-list>

          <div class="sidebar-footer">
            <div class="status" [class.online]="backendOk">
              <span class="dot"></span>
              {{ backendOk ? 'Backend connected' : 'Backend offline' }}
            </div>
            <small>Native Engine · v{{ appVersion }} · {{ releaseName }}</small>
          </div>
        </mat-sidenav>

        <mat-sidenav-content class="main">
          <mat-toolbar class="topbar">
            <span class="topbar-title">OSINT Self-Audit Platform</span>
            <span class="spacer"></span>
            <span class="consent-badge">
              <mat-icon>verified_user</mat-icon> Authorized use only
            </span>
          </mat-toolbar>
          <main class="content">
            <router-outlet />
          </main>
        </mat-sidenav-content>
      </mat-sidenav-container>
    }
  `,
  styles: [`
    .layout { height: 100vh; background: var(--cm-bg); }
    .sidebar {
      width: var(--cm-sidebar-w) !important;
      background: var(--cm-surface) !important;
      border-right: 1px solid var(--cm-border);
      display: flex;
      flex-direction: column;
    }
    .brand {
      display: flex; gap: 14px; align-items: center;
      padding: 1.5rem 1.25rem;
      border-bottom: 1px solid var(--cm-border);
    }
    .logo {
      width: 44px; height: 44px;
      background: linear-gradient(135deg, var(--cm-accent), var(--cm-accent-dim));
      border-radius: 10px;
      display: flex; align-items: center; justify-content: center;
    }
    .logo mat-icon { color: #fff; }
    .brand-text strong { display: block; font-size: 1.15rem; letter-spacing: -0.02em; color: #f0f6fc; }
    .brand-text span { display: block; color: #b1bac4; font-size: 0.68rem; line-height: 1.3; margin-top: 2px; }
    .nav-list { flex: 1; padding-top: 0.5rem; }
    .nav-list a {
      margin: 2px 8px;
      border-radius: 8px;
      color: #f0f6fc !important;
    }
    .nav-list a .mat-mdc-list-item-title,
    .nav-list a .mdc-list-item__primary-text {
      color: #f0f6fc !important;
    }
    .sidebar-footer {
      padding: 1rem 1.25rem;
      border-top: 1px solid var(--cm-border);
      color: #b1bac4;
      font-size: 0.75rem;
    }
    .sidebar-footer small { color: #8b949e; }
    .status { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; color: var(--cm-critical); }
    .status.online { color: var(--cm-low); }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
    .topbar {
      background: var(--cm-bg-elevated) !important;
      color: var(--cm-text) !important;
      border-bottom: 1px solid var(--cm-border);
      height: 56px;
    }
    .topbar-title { font-weight: 500; color: #f0f6fc !important; }
    .spacer { flex: 1; }
    .consent-badge {
      display: flex; align-items: center; gap: 6px;
      font-size: 0.8rem; color: #b1bac4;
      padding: 4px 12px; border: 1px solid var(--cm-border); border-radius: 20px;
    }
    .consent-badge mat-icon { font-size: 16px; width: 16px; height: 16px; color: #b1bac4; }
    .content { padding: 1.75rem 2rem; min-height: calc(100vh - 56px); background: var(--cm-bg); }

    .unlock-gate {
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 2rem;
      background:
        radial-gradient(ellipse at top, rgba(56, 139, 253, 0.12), transparent 55%),
        var(--cm-bg, #0d1117);
    }
    .unlock-card {
      width: min(440px, 100%);
      padding: 1.75rem;
      border: 1px solid var(--cm-border, #30363d);
      border-radius: 12px;
      background: var(--cm-surface, #161b22);
      color: #f0f6fc;
    }
    .unlock-brand {
      display: flex; align-items: center; gap: 10px;
      margin-bottom: 1rem; color: #f0f6fc;
    }
    .unlock-brand mat-icon { color: #58a6ff; }
    .unlock-card h1 {
      margin: 0 0 0.75rem;
      font-size: 1.35rem;
      font-weight: 600;
    }
    .unlock-card p {
      margin: 0 0 1.25rem;
      color: #b1bac4;
      font-size: 0.92rem;
      line-height: 1.45;
    }
    .unlock-card code {
      font-size: 0.8rem;
      color: #79c0ff;
    }
    .unlock-label {
      display: block;
      margin-bottom: 0.35rem;
      font-size: 0.8rem;
      color: #b1bac4;
    }
    .unlock-input {
      width: 100%;
      box-sizing: border-box;
      padding: 0.65rem 0.75rem;
      border-radius: 8px;
      border: 1px solid #30363d;
      background: #0d1117;
      color: #f0f6fc;
      margin-bottom: 0.75rem;
    }
    .unlock-btn {
      width: 100%;
      padding: 0.7rem 1rem;
      border: 0;
      border-radius: 8px;
      background: #238636;
      color: #fff;
      font-weight: 600;
      cursor: pointer;
    }
    .unlock-btn:disabled { opacity: 0.6; cursor: default; }
    .unlock-error { color: #f85149; margin: 0 0 0.75rem; font-size: 0.85rem; }
  `],
})
export class AppComponent implements OnInit {
  backendOk = false;
  needsUnlock = false;
  unlockDraft = '';
  unlockError = '';
  unlockBusy = false;
  appVersion = '2.4.0';
  releaseName = 'Correlation';

  constructor(private api: ApiService) {}

  ngOnInit() {
    localStorage.removeItem('cm_locale');
    document.documentElement.lang = 'en';
    document.documentElement.dir = 'ltr';

    const checkHealth = () => {
      this.api.health().subscribe({
        next: (h: any) => {
          this.backendOk = true;
          if (h?.version) this.appVersion = h.version;
          if (h?.release_name) this.releaseName = h.release_name;
          this.evaluateUnlockGate(!!h?.api_auth_enabled);
        },
        error: () => {
          this.backendOk = false;
        },
      });
    };
    checkHealth();
    setInterval(checkHealth, 15000);
  }

  private evaluateUnlockGate(authEnabled: boolean) {
    if (!authEnabled) {
      this.needsUnlock = false;
      return;
    }
    const token = getApiToken();
    if (!token) {
      this.needsUnlock = true;
      return;
    }
    // Validate stored/injected tokens so stale values re-open the unlock form.
    this.api.modules().subscribe({
      next: () => {
        this.needsUnlock = false;
      },
      error: (err: any) => {
        const status = err?.status;
        if (status === 401 || status === 403) {
          sessionStorage.removeItem('cybermirror_api_token');
          this.needsUnlock = true;
          return;
        }
        // Transient outages: keep the token; unlock gate stays closed if we already had one.
        this.backendOk = false;
      },
    });
  }

  submitUnlock() {
    const token = this.unlockDraft.trim();
    if (!token) {
      this.unlockError = 'Enter the API token.';
      return;
    }
    this.unlockBusy = true;
    this.unlockError = '';
    storeApiToken(token);
    // Probe a protected route to validate before entering the app.
    this.api.modules().subscribe({
      next: () => {
        this.unlockBusy = false;
        this.needsUnlock = false;
        this.unlockDraft = '';
      },
      error: (err: any) => {
        this.unlockBusy = false;
        const status = err?.status;
        if (status === 401 || status === 403) {
          sessionStorage.removeItem('cybermirror_api_token');
          this.unlockError = 'Invalid token. Check data/.api_token and try again.';
          return;
        }
        this.unlockError = 'Backend temporarily unavailable — token was kept. Try again.';
      },
    });
  }
}
