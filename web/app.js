// app.js — Spatial Explorer demo entrypoint (ES module)

import { makeDemoCellTypes, makeDemoGenePanel, buildGeneIndex, generateDemoCells, hexToRgb, buildQuadtreeIndex, buildSpatialIndex } from './data.js';
import { createRenderer } from './render.js';
import { collectDom, createUi } from './ui.js';

// ---------- App state (single mutable store) ----------
const cellTypes0 = makeDemoCellTypes();
const genePanel0 = makeDemoGenePanel();

// 10K+ stress test dataset (performance target)
const demo = generateDemoCells(12000, genePanel0);

const state = {
  // dataset
  datasetName: 'synthetic-demo',
  cells: demo.cells,
  cellTypes: cellTypes0,
  genePanel: genePanel0,
  geneIndex: demo.geneIndex ?? buildGeneIndex(genePanel0),

  // filters + colors
  activeTypes: new Map(cellTypes0.map(t => [t.key, true])),
  typeColorRgb: new Map(cellTypes0.map(t => [t.key, hexToRgb(t.color)])),

  // perf helpers
  // Prefer quadtree for clustered real-world datasets; grid remains as a fallback option.
  spatialIndex: buildQuadtreeIndex(demo.cells, {maxItems: 48, maxDepth: 12}),
  _activeTypesVersion: 1,
  _geneRangeCache: new Map(),

  // selection + hover
  selectedId: null,
  hoveredId: null,

  // gene mode
  geneQuery: '',
  geneIdx: null,

  // scale bar calibration (µm per coordinate unit; for real datasets this is µm per pixel)
  // Set so the default scale bar resolves to ~100 µm at the initial zoom.
  umPerPixel: 200,

  // gate
  gate: {
    version: 1,
    enabled: true,
    advanced: false,
    conditions: [
      {gene: 'CD3E', sense: 'pos', cutoff: 0.5, join: 'AND'},
      {gene: 'EPCAM', sense: 'pos', cutoff: 0.5, join: 'AND'},
    ],
    expr: 'A AND B',
  },
  gateMask: null,
  gateMatchCount: 0,
  gateLastError: null,
};

const dom = collectDom();

let ui = null;

const renderer = createRenderer({
  canvas: dom.canvas,
  glCanvas: dom.glCanvas,
  getState: ()=>state,
  onLegendCounts: ()=> ui && ui.updateLegendCounts(),
});

ui = createUi({
  dom,
  renderer,
  state,
  dataApi: {},
});

// Init
renderer.resizeCanvas({initial:true});
ui.bind();
