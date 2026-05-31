import { Component, OnInit } from '@angular/core';

import { CommonModule } from '@angular/common';

import { FormsModule } from '@angular/forms';

import { Router, RouterLink } from '@angular/router';

import { MatIconModule } from '@angular/material/icon';

import { MatProgressBarModule } from '@angular/material/progress-bar';

import { NgxEchartsDirective, provideEchartsCore } from 'ngx-echarts';

import * as echarts from 'echarts/core';

import { ApiService } from '../../services/api.service';



@Component({

  selector: 'cm-dashboard',

  standalone: true,

  imports: [CommonModule, RouterLink, MatIconModule, NgxEchartsDirective],

  providers: [provideEchartsCore({ echarts })],

  template: `

    <div class="page-header">

      <h1>Dashboard</h1>

      <p class="subtitle">Overview of your public digital footprint</p>

    </div>



    <div class="stat-grid" *ngIf="latestScan">

      <div class="stat-card" [class.critical]="latestScan.risk_score >= 70">

        <span class="label">Risk Score</span>

        <span class="value accent">{{ latestScan.risk_score }}</span>

      </div>

      <div class="stat-card success">

        <span class="label">Total Findings</span>

        <span class="value">{{ latestScan.finding_count }}</span>

      </div>

      <div class="stat-card high" *ngIf="stats">

        <span class="label">High-Risk Items</span>

        <span class="value">{{ stats.high_risk_count }}</span>

      </div>

      <div class="stat-card">

        <span class="label">Last Scan</span>

        <span class="value" style="font-size:1rem">{{ latestScan.created_at | date:'medium' }}</span>

      </div>

    </div>



    <div class="card empty-state" *ngIf="!latestScan">

      <mat-icon>radar</mat-icon>

      <h3>No scans yet</h3>

      <p>Start your first self-audit investigation</p>

      <a routerLink="/investigate" class="btn-primary" style="margin-top:1rem">Start Investigation</a>

    </div>



    <div class="charts-row" *ngIf="stats">

      <div class="card chart-card">

        <div class="card-header"><mat-icon>pie_chart</mat-icon><h3>Exposure by Risk</h3></div>

        <div echarts [options]="riskChart" class="chart"></div>

      </div>

      <div class="card chart-card">

        <div class="card-header"><mat-icon>source</mat-icon><h3>Findings by Source</h3></div>

        <div echarts [options]="sourceChart" class="chart"></div>

      </div>

      <div class="card chart-card">

        <div class="card-header"><mat-icon>category</mat-icon><h3>By Category</h3></div>

        <div echarts [options]="categoryChart" class="chart"></div>

      </div>

    </div>



    <div class="actions" *ngIf="latestScan">

      <a class="btn-primary" [routerLink]="['/scan', latestScan.id]">
        <mat-icon>visibility</mat-icon> View Saved Results
      </a>

      <a class="btn-primary" [routerLink]="['/graph', latestScan.id]">

        <mat-icon>hub</mat-icon> Relationship Graph

      </a>

      <a class="btn-secondary" [routerLink]="['/reports', latestScan.id]">Export Reports</a>

      <a class="btn-secondary" routerLink="/investigate">New Scan</a>

    </div>

  `,

  styles: [`

    .charts-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 1.5rem; }

    .chart { height: 260px; }

    .actions { display: flex; gap: 1rem; flex-wrap: wrap; }

    @media (max-width: 1200px) { .charts-row { grid-template-columns: 1fr; } }

  `],

})

export class DashboardComponent implements OnInit {

  latestScan: any = null;

  stats: any = null;

  riskChart: any = {};

  sourceChart: any = {};

  categoryChart: any = {};



  constructor(private api: ApiService) {}



  ngOnInit() {

    this.api.listScans().subscribe(scans => {

      if (scans.length) {

        this.latestScan = scans[0];

        this.api.dashboard(this.latestScan.id).subscribe(s => {

          this.stats = s;

          this.buildCharts(s);

        });

      }

    });

  }



  buildCharts(s: any) {

    const colors = ['#ff6b6b', '#ffa657', '#f0c040', '#3fb950', '#79c0ff', '#8b949e'];

    this.riskChart = {

      tooltip: { trigger: 'item' },

      series: [{

        type: 'pie', radius: ['45%', '70%'],

        data: Object.entries(s.by_risk || {}).map(([name, value]) => ({ name, value })),

        itemStyle: { borderRadius: 6, borderColor: '#161b22', borderWidth: 2 },

        color: colors,

      }],

    };

    this.sourceChart = {

      tooltip: { trigger: 'axis' },

      xAxis: { type: 'category', data: Object.keys(s.by_source || {}), axisLabel: { color: '#8b949e' } },

      yAxis: { type: 'value', axisLabel: { color: '#8b949e' }, splitLine: { lineStyle: { color: '#30363d' } } },

      series: [{ type: 'bar', data: Object.values(s.by_source || {}), itemStyle: { color: '#388bfd', borderRadius: [4,4,0,0] } }],

    };

    this.categoryChart = {

      tooltip: { trigger: 'item' },

      series: [{

        type: 'pie', radius: '65%',

        data: Object.entries(s.by_category || {}).map(([name, value]) => ({

          name: name.replace(/_/g, ' '), value,

        })),

        color: colors,

      }],

    };

  }

}


