import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
  {
    path: 'dashboard',
    loadComponent: () =>
      import('./pages/dashboard/dashboard.component').then(m => m.DashboardComponent),
  },
  {
    path: 'investigate',
    loadComponent: () =>
      import('./pages/investigate/investigate.component').then(m => m.InvestigateComponent),
  },
  {
    path: 'graph/:scanId',
    loadComponent: () =>
      import('./pages/graph/graph.component').then(m => m.GraphComponent),
  },
  {
    path: 'reports/:scanId',
    loadComponent: () =>
      import('./pages/reports/reports.component').then(m => m.ReportsComponent),
  },
  {
    path: 'history',
    loadComponent: () =>
      import('./pages/history/history.component').then(m => m.HistoryComponent),
  },
  {
    path: 'scan/:scanId',
    loadComponent: () =>
      import('./pages/scan-detail/scan-detail.component').then(m => m.ScanDetailComponent),
  },
  {
    path: 'settings',
    loadComponent: () =>
      import('./pages/settings/settings.component').then(m => m.SettingsComponent),
  },
];
