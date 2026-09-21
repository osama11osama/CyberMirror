import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { NgxEchartsDirective, provideEchartsCore } from 'ngx-echarts';
import * as echarts from 'echarts/core';
import { ApiService } from '../../services/api.service';
import { asUtcDate } from '../../utils/dates';

@Component({
  selector: 'cm-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, MatIconModule, NgxEchartsDirective],
  providers: [provideEchartsCore({ echarts })],
  template: `
    <div class="page-header">
      <h1>Dashboard</h1>
      <p class="subtitle">Overview of your public digital footprint</p>
    </div>

    <div class="scan-picker card" *ngIf="scans.length">
      <label>Select scan</label>
      <select [(ngModel)]="selectedScanId" (ngModelChange)="loadScan()">
        <option *ngFor="let s of scans" [value]="s.id">
          {{ formatDate(s.created_at) | date:'medium' }} — {{ s.profile.username || s.profile.email || 'scan' }} ({{ s.risk_score }})
        </option>
      </select>
    </div>

    <div class="stat-grid" *ngIf="activeScan">
      <div class="stat-card" [class.critical]="activeScan.risk_score >= 70">
        <span class="label">Risk Score</span>
        <span class="value accent">{{ activeScan.risk_score }}</span>
      </div>
      <div class="stat-card success">
        <span class="label">Total Findings</span>
        <span class="value">{{ activeScan.finding_count }}</span>
      </div>
      <div class="stat-card high" *ngIf="stats">
        <span class="label">High-Risk Items</span>
        <span class="value">{{ stats.high_risk_count }}</span>
      </div>
      <div class="stat-card">
        <span class="label">Last Scan</span>
        <span class="value sm">{{ formatDate(activeScan.created_at) | date:'medium' }}</span>
      </div>
    </div>

    <div class="card empty-state" *ngIf="!activeScan">
      <mat-icon>radar</mat-icon>
      <h3>No scans yet</h3>
      <a routerLink="/investigate" class="btn-primary">Start Investigation</a>
    </div>

    <div class="charts-row" *ngIf="stats">
      <div class="card chart-card wide">
        <div class="card-header"><mat-icon>show_chart</mat-icon><h3>Risk trend</h3></div>
        <div echarts [options]="trendChart" class="chart"></div>
      </div>
      <div class="card chart-card">
        <div class="card-header"><mat-icon>pie_chart</mat-icon><h3>Exposure by Risk</h3></div>
        <div echarts [options]="riskChart" class="chart"></div>
      </div>
      <div class="card chart-card">
        <div class="card-header"><mat-icon>source</mat-icon><h3>Findings by Source</h3></div>
        <div echarts [options]="sourceChart" class="chart"></div>
      </div>
    </div>

    <div class="actions" *ngIf="activeScan">
      <a class="btn-primary" [routerLink]="['/scan', activeScan.id]">View Results</a>
      <a class="btn-primary" [routerLink]="['/graph', activeScan.id]">Graph</a>
      <a class="btn-secondary" [routerLink]="['/reports', activeScan.id]">Export</a>
      <a class="btn-secondary" routerLink="/investigate">New Scan</a>
    </div>
  `,
  styles: [`
    .scan-picker { margin-bottom: 1rem; padding: 1rem; }
    .scan-picker label { display: block; margin-bottom: 0.35rem; color: var(--cm-muted); font-size: 0.85rem; }
    .scan-picker select { width: 100%; padding: 0.5rem; background: var(--cm-surface-2); border: 1px solid var(--cm-border); border-radius: 6px; color: var(--cm-text); }
    .charts-row { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 1rem; margin-bottom: 1.5rem; }
    .chart { height: 260px; }
    .actions { display: flex; gap: 1rem; flex-wrap: wrap; }
    .value.sm { font-size: 1rem !important; }
    @media (max-width: 1200px) { .charts-row { grid-template-columns: 1fr; } }
  `],
})
export class DashboardComponent implements OnInit {
  scans: any[] = [];
  selectedScanId = '';
  activeScan: any = null;
  stats: any = null;
  riskChart: any = {};
  sourceChart: any = {};
  trendChart: any = {};

  constructor(private api: ApiService) {}

  formatDate(value: string) {
    return asUtcDate(value);
  }

  ngOnInit() {
    this.api.listScans(30).subscribe(scans => {
      this.scans = scans;
      if (scans.length) {
        this.selectedScanId = scans[0].id;
        this.activeScan = scans[0];
        this.loadScan();
      }
    });
    this.api.trends(15).subscribe(t => this.buildTrend(t.scans || []));
  }

  loadScan() {
    const s = this.scans.find(x => x.id === this.selectedScanId);
    if (!s) return;
    this.activeScan = s;
    this.api.dashboard(s.id).subscribe(st => {
      this.stats = st;
      this.buildCharts(st);
    });
  }

  buildTrend(rows: any[]) {
    this.trendChart = {
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: rows.map(r => r.created_at?.slice(0, 10)), axisLabel: { color: '#8b949e' } },
      yAxis: { type: 'value', axisLabel: { color: '#8b949e' }, splitLine: { lineStyle: { color: '#30363d' } } },
      series: [{
        type: 'line', smooth: true, data: rows.map(r => r.risk_score),
        itemStyle: { color: '#388bfd' }, areaStyle: { color: 'rgba(56,139,253,0.15)' },
      }],
    };
  }

  buildCharts(s: any) {
    const colors = ['#ff6b6b', '#ffa657', '#f0c040', '#3fb950', '#79c0ff', '#8b949e'];
    this.riskChart = {
      tooltip: { trigger: 'item' },
      series: [{
        type: 'pie', radius: ['45%', '70%'],
        data: Object.entries(s.by_risk || {}).map(([name, value]) => ({ name, value })),
        color: colors,
      }],
    };
    this.sourceChart = {
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: Object.keys(s.by_source || {}), axisLabel: { color: '#8b949e', rotate: 30 } },
      yAxis: { type: 'value', axisLabel: { color: '#8b949e' }, splitLine: { lineStyle: { color: '#30363d' } } },
      series: [{ type: 'bar', data: Object.values(s.by_source || {}), itemStyle: { color: '#388bfd' } }],
    };
  }
}
