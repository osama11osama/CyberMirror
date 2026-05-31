import { Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import cytoscape, { Core, NodeSingular } from 'cytoscape';
import { ApiService } from '../../services/api.service';

interface NodeDetail {
  id: string;
  label: string;
  type: string;
  url?: string;
  title?: string;
  snippet?: string;
  description?: string;
  source?: string;
  platform?: string;
  risk?: string;
  category?: string;
}

@Component({
  selector: 'cm-graph',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, MatIconModule],
  template: `
    <div class="page-header">
      <h1>Relationship Graph</h1>
      <p class="subtitle">Click a node for details · Double-click to open link</p>
    </div>

    <div class="toolbar">
      <a class="btn-secondary" routerLink="/history"><mat-icon>arrow_back</mat-icon> History</a>
      <select *ngIf="scans.length" [(ngModel)]="scanId" (ngModelChange)="loadGraph()" class="scan-select">
        <option *ngFor="let s of scans" [value]="s.id">{{ s.created_at | date:'short' }} — {{ s.profile.username || s.profile.email || 'scan' }}</option>
      </select>
      <select [(ngModel)]="riskFilter" (ngModelChange)="applyFilter()" class="scan-select">
        <option value="">All risks</option>
        <option>Critical</option><option>High</option><option>Medium</option><option>Low</option>
      </select>
      <a class="btn-primary" *ngIf="scanId" [routerLink]="['/reports', scanId]">Export Report</a>
    </div>

    <div class="graph-layout">
      <div class="card graph-card">
        <div #cyContainer class="cy-container"></div>
        <div class="legend">
          <span><i class="dot person"></i> Person</span>
          <span><i class="dot email"></i> Email</span>
          <span><i class="dot user"></i> Username</span>
          <span><i class="dot profile"></i> Public Profile</span>
          <span class="hint">Single-click = info · Double-click = open URL</span>
        </div>
      </div>

      <div class="card detail-panel" *ngIf="selected">
        <div class="card-header">
          <mat-icon>info</mat-icon>
          <h3>{{ selected.label }}</h3>
          <button class="close-btn" (click)="clearSelection()" aria-label="Close">×</button>
        </div>
        <span class="type-badge">{{ selected.type }}</span>
        <p class="detail-row" *ngIf="selected.platform"><strong>Platform</strong> {{ selected.platform }}</p>
        <p class="detail-row" *ngIf="selected.title"><strong>Finding</strong> {{ selected.title }}</p>
        <p class="detail-row" *ngIf="selected.source"><strong>Source</strong> {{ selected.source }}</p>
        <p class="detail-row" *ngIf="selected.risk">
          <strong>Risk</strong>
          <span class="risk-badge" [class]="'risk-' + selected.risk">{{ selected.risk }}</span>
        </p>
        <p class="detail-row snippet" *ngIf="selected.snippet">{{ selected.snippet }}</p>
        <p class="detail-row snippet" *ngIf="selected.description && !selected.snippet">{{ selected.description }}</p>
        <a *ngIf="selected.url" class="btn-primary open-link" [href]="selected.url" target="_blank" rel="noopener">
          <mat-icon>open_in_new</mat-icon> Open in new tab
        </a>
        <p class="muted" *ngIf="!selected.url">No URL for this node</p>
      </div>

      <div class="card detail-panel empty" *ngIf="!selected">
        <mat-icon>touch_app</mat-icon>
        <p>Click any node to see details</p>
        <p class="muted">Double-click a profile node to open its URL</p>
      </div>
    </div>
  `,
  styles: [`
    .toolbar { display: flex; gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap; align-items: center; }
    .scan-select { padding: 0.45rem 0.75rem; background: var(--cm-surface-2); border: 1px solid var(--cm-border); border-radius: 6px; color: var(--cm-text); min-width: 200px; }
    .graph-layout { display: grid; grid-template-columns: 1fr 320px; gap: 1rem; align-items: start; }
    .graph-card { padding: 0; overflow: hidden; }
    .cy-container { height: calc(100vh - 280px); min-height: 500px; width: 100%; background: var(--cm-bg); }
    .legend {
      display: flex; flex-wrap: wrap; gap: 1rem; padding: 0.75rem 1.25rem;
      border-top: 1px solid var(--cm-border); font-size: 0.8rem; color: var(--cm-muted);
    }
    .legend .hint { margin-left: auto; font-style: italic; }
    .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
    .dot.person { background: #ffa657; }
    .dot.email { background: #ff6b6b; }
    .dot.user { background: #388bfd; }
    .dot.profile { background: #3fb950; }
    .detail-panel { padding: 1rem 1.25rem; min-height: 200px; position: sticky; top: 1rem; }
    .detail-panel.empty { text-align: center; color: var(--cm-muted); padding: 2rem 1rem; }
    .detail-panel.empty mat-icon { font-size: 40px; width: 40px; height: 40px; opacity: 0.5; }
    .close-btn {
      margin-left: auto; background: none; border: none; color: var(--cm-muted);
      font-size: 1.4rem; cursor: pointer; line-height: 1;
    }
    .card-header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; }
    .card-header h3 { margin: 0; font-size: 1rem; word-break: break-word; }
    .type-badge {
      display: inline-block; background: var(--cm-surface-2); padding: 2px 8px;
      border-radius: 4px; font-size: 0.75rem; color: var(--cm-muted); margin-bottom: 0.75rem;
    }
    .detail-row { margin: 0.5rem 0; font-size: 0.9rem; line-height: 1.5; }
    .detail-row strong { display: block; color: var(--cm-muted); font-size: 0.75rem; text-transform: uppercase; }
    .snippet { color: var(--cm-muted); font-size: 0.85rem; }
    .open-link { display: inline-flex; align-items: center; gap: 0.35rem; margin-top: 1rem; width: 100%; justify-content: center; }
    .muted { color: var(--cm-muted); font-size: 0.85rem; }
    @media (max-width: 1000px) { .graph-layout { grid-template-columns: 1fr; } .detail-panel { position: static; } }
  `],
})
export class GraphComponent implements OnInit, OnDestroy {
  @ViewChild('cyContainer', { static: true }) cyEl!: ElementRef;

  scanId = '';
  scans: any[] = [];
  riskFilter = '';
  selected: NodeDetail | null = null;
  private cy?: Core;
  private rawGraph: any = null;

  constructor(private route: ActivatedRoute, private api: ApiService) {}

  ngOnInit() {
    this.scanId = this.route.snapshot.paramMap.get('scanId') ?? '';
    this.api.listScans(30).subscribe(s => {
      this.scans = s;
      if (!this.scanId && s.length) this.scanId = s[0].id;
      if (this.scanId) this.loadGraph();
    });
  }

  loadGraph() {
    if (!this.scanId) return;
    this.api.graph(this.scanId).subscribe(data => {
      this.rawGraph = data;
      this.applyFilter();
    });
  }

  applyFilter() {
    if (!this.rawGraph) return;
    let data = this.rawGraph;
    if (this.riskFilter) {
      const allowed = new Set(
        data.nodes.filter((n: any) => n.type === 'Finding' && n.data?.risk === this.riskFilter).map((n: any) => n.id)
      );
      const nodes = data.nodes.filter((n: any) => n.type !== 'Finding' || allowed.has(n.id));
      const ids = new Set(nodes.map((n: any) => n.id));
      const edges = data.edges.filter((e: any) => ids.has(e.source) && ids.has(e.target));
      data = { nodes, edges };
    }
    this.renderGraph(data);
  }

  ngOnDestroy() {
    this.cy?.destroy();
  }

  clearSelection() {
    this.selected = null;
    this.cy?.$('node:selected').unselect();
  }

  private nodeDetail(node: NodeSingular): NodeDetail {
    const d = node.data();
    return {
      id: d.id,
      label: d.label,
      type: d.type,
      url: d.url,
      title: d.title,
      snippet: d.snippet,
      description: d.description,
      source: d.source,
      platform: d.platform,
      risk: d.risk,
      category: d.category,
    };
  }

  private openNodeUrl(node: NodeSingular) {
    const url = node.data('url');
    if (url) {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  }

  renderGraph(data: any) {
    const typeColors: Record<string, string> = {
      Person: '#ffa657', Email: '#ff6b6b', Username: '#388bfd',
      Phone: '#f0c040', Website: '#79c0ff', Location: '#8b949e',
      PublicProfile: '#3fb950', Finding: '#6e7681',
    };

    const elements = [
      ...data.nodes.map((n: any) => ({
        data: { id: n.id, label: n.label, type: n.type, ...n.data },
      })),
      ...data.edges.map((e: any) => ({
        data: { id: e.id, source: e.source, target: e.target, label: e.label },
      })),
    ];

    if (this.cy) {
      this.cy.destroy();
    }

    this.cy = cytoscape({
      container: this.cyEl.nativeElement,
      elements,
      style: [
        {
          selector: 'node',
          style: {
            'background-color': '#388bfd',
            label: 'data(label)',
            color: '#f0f3f6',
            'text-valign': 'bottom',
            'text-margin-y': 8,
            'font-size': 11,
            width: 36,
            height: 36,
            'border-width': 2,
            'border-color': '#30363d',
            'overlay-opacity': 0,
          },
        },
        {
          selector: 'node:selected',
          style: {
            'border-width': 4,
            'border-color': '#58a6ff',
            'background-blacken': -0.1,
          },
        },
        ...Object.entries(typeColors).map(([type, color]) => ({
          selector: `node[type="${type}"]`,
          style: {
            'background-color': color,
            width: type === 'Person' ? 48 : 36,
            height: type === 'Person' ? 48 : 36,
          },
        })),
        {
          selector: 'edge',
          style: {
            width: 2,
            'line-color': '#484f58',
            'target-arrow-color': '#484f58',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            label: 'data(label)',
            'font-size': 9,
            color: '#8b949e',
          },
        },
      ],
      layout: { name: 'cose', animate: true, padding: 60, nodeRepulsion: 12000, idealEdgeLength: 80 },
      wheelSensitivity: 0.3,
      minZoom: 0.3,
      maxZoom: 3,
    });

    this.cy.on('tap', 'node', (evt) => {
      const node = evt.target as NodeSingular;
      this.cy!.$('node:selected').unselect();
      node.select();
      this.selected = this.nodeDetail(node);
    });

    this.cy.on('dbltap', 'node', (evt) => {
      this.openNodeUrl(evt.target as NodeSingular);
    });

    this.cy.on('tap', (evt) => {
      if (evt.target === this.cy) {
        this.clearSelection();
      }
    });
  }
}
