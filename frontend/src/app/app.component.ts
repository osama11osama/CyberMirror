import { Component, OnInit } from '@angular/core';

import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { MatSidenavModule } from '@angular/material/sidenav';

import { MatListModule } from '@angular/material/list';

import { MatIconModule } from '@angular/material/icon';

import { MatToolbarModule } from '@angular/material/toolbar';

import { MatBadgeModule } from '@angular/material/badge';

import { CommonModule } from '@angular/common';

import { ApiService } from './services/api.service';



@Component({

  selector: 'cm-root',

  standalone: true,

  imports: [

    CommonModule, RouterOutlet, RouterLink, RouterLinkActive,

    MatSidenavModule, MatListModule, MatIconModule, MatToolbarModule, MatBadgeModule,

  ],

  template: `

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

          <small>Native Engine · v2.1.0</small>

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

  `],

})

export class AppComponent implements OnInit {

  backendOk = false;

  constructor(private api: ApiService) {}

  ngOnInit() {
    localStorage.removeItem('cm_locale');
    document.documentElement.lang = 'en';
    document.documentElement.dir = 'ltr';
    this.api.health().subscribe({ next: () => this.backendOk = true, error: () => this.backendOk = false });
  }

}


