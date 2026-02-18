// data.js — Spatial Explorer data loading/parsing + gate evaluation (ES module)

// ---------- Math / helpers ----------
export function clamp(x, a, b){ return Math.max(a, Math.min(b, x)); }
export function lerp(a,b,t){ return a + (b-a)*t; }

// ---------- RNG (deterministic; used for synthetic dataset) ----------
export function mulberry32(seed){
  let a = seed >>> 0;
  return function(){
    a |= 0; a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

export function makeRandn(rand){
  return function randn(){
    // Box-Muller
    let u = 0, v = 0;
    while(u === 0) u = rand();
    while(v === 0) v = rand();
    return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
  };
}

// ---------- Color + palette ----------
export function hexToRgb(hex){
  const h = String(hex || '#000').replace('#','').trim();
  const v = parseInt(h.length===3 ? h.split('').map(ch=>ch+ch).join('') : h, 16);
  return {r:(v>>16)&255,g:(v>>8)&255,b:v&255};
}
export function rgba(rgb,a){ return `rgba(${rgb.r},${rgb.g},${rgb.b},${a})`; }

export function palette(i){
  const pal = [
    '#60a5fa','#34d399','#fbbf24','#fb7185','#a78bfa','#38bdf8','#f472b6',
    '#f97316','#22c55e','#e879f9','#facc15','#93c5fd','#86efac','#c4b5fd'
  ];
  return pal[i % pal.length];
}

// ---------- Spatial helper ----------
export function zoneLabel(rNorm){
  if(rNorm < 0.35) return 'core';
  if(rNorm < 0.70) return 'mid';
  return 'rim';
}

// ---------- Spatial indices (picking) ----------
// World coordinates are assumed to be in the same units as cell x/y.
// Indices are static per dataset and cheap to query.

// (A) Uniform grid (very fast for near-uniform density; used as fallback)
export function buildSpatialIndex(cells, {cellSize=0.04} = {}){
  const n = cells.length;
  if(n === 0) return {kind:'grid', cellSize, minX:0, minY:0, nx:0, ny:0, buckets:[]};

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for(let i=0;i<n;i++){
    const c = cells[i];
    const x = c.x, y = c.y;
    if(x < minX) minX = x;
    if(y < minY) minY = y;
    if(x > maxX) maxX = x;
    if(y > maxY) maxY = y;
  }

  // pad bounds slightly so edge points don't clamp to nx/ny
  const pad = cellSize * 1.5;
  minX -= pad; minY -= pad; maxX += pad; maxY += pad;

  const nx = Math.max(1, Math.ceil((maxX - minX) / cellSize));
  const ny = Math.max(1, Math.ceil((maxY - minY) / cellSize));
  const buckets = new Array(nx * ny);
  for(let i=0;i<buckets.length;i++) buckets[i] = [];

  for(let i=0;i<n;i++){
    const c = cells[i];
    const ix = Math.max(0, Math.min(nx - 1, Math.floor((c.x - minX) / cellSize)));
    const iy = Math.max(0, Math.min(ny - 1, Math.floor((c.y - minY) / cellSize)));
    buckets[iy * nx + ix].push(c.id);
  }

  // Freeze buckets to typed arrays to reduce GC during queries.
  for(let i=0;i<buckets.length;i++){
    buckets[i] = Int32Array.from(buckets[i]);
  }

  return {kind:'grid', cellSize, minX, minY, nx, ny, buckets};
}

export function querySpatialIndex(index, x, y, r){
  if(!index || index.kind !== 'grid' || !index.nx || !index.ny) return null;
  const {cellSize, minX, minY, nx, ny} = index;

  const ix0 = Math.max(0, Math.min(nx - 1, Math.floor((x - r - minX) / cellSize)));
  const ix1 = Math.max(0, Math.min(nx - 1, Math.floor((x + r - minX) / cellSize)));
  const iy0 = Math.max(0, Math.min(ny - 1, Math.floor((y - r - minY) / cellSize)));
  const iy1 = Math.max(0, Math.min(ny - 1, Math.floor((y + r - minY) / cellSize)));

  return {ix0, ix1, iy0, iy1};
}

// (B) Quadtree (better for clustered / non-uniform densities)
// Stores ids in leaves; nodes subdivide until maxItems or maxDepth.
export function buildQuadtreeIndex(cells, {maxItems=48, maxDepth=12, pad=0.02} = {}){
  const n = cells.length;
  if(n === 0){
    return {kind:'quadtree', x0:0,y0:0,x1:0,y1:0, maxItems, maxDepth, root:{x0:0,y0:0,x1:0,y1:0, ids:new Int32Array(0), children:null}};
  }

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for(let i=0;i<n;i++){
    const c = cells[i];
    const x = c.x, y = c.y;
    if(x < minX) minX = x;
    if(y < minY) minY = y;
    if(x > maxX) maxX = x;
    if(y > maxY) maxY = y;
  }
  minX -= pad; minY -= pad; maxX += pad; maxY += pad;

  const ids = new Int32Array(n);
  for(let i=0;i<n;i++) ids[i] = cells[i].id;

  function buildNode(x0,y0,x1,y1, idsArr, depth){
    if(depth >= maxDepth || idsArr.length <= maxItems){
      return {x0,y0,x1,y1, ids: idsArr, children: null};
    }
    const mx = (x0+x1)*0.5;
    const my = (y0+y1)*0.5;

    const q0 = []; // NW: x<=mx, y<=my
    const q1 = []; // NE: x>mx,  y<=my
    const q2 = []; // SW: x<=mx, y>my
    const q3 = []; // SE: x>mx,  y>my

    for(let i=0;i<idsArr.length;i++){
      const id = idsArr[i];
      const c = cells[id-1];
      if(!c) continue;
      const east = c.x > mx;
      const south = c.y > my;
      if(!east && !south) q0.push(id);
      else if(east && !south) q1.push(id);
      else if(!east && south) q2.push(id);
      else q3.push(id);
    }

    // If subdivision doesn't reduce (pathological), keep as leaf.
    if(q0.length === idsArr.length || q1.length === idsArr.length || q2.length === idsArr.length || q3.length === idsArr.length){
      return {x0,y0,x1,y1, ids: idsArr, children: null};
    }

    const children = [
      buildNode(x0, y0, mx, my, Int32Array.from(q0), depth+1),
      buildNode(mx, y0, x1, my, Int32Array.from(q1), depth+1),
      buildNode(x0, my, mx, y1, Int32Array.from(q2), depth+1),
      buildNode(mx, my, x1, y1, Int32Array.from(q3), depth+1),
    ];
    return {x0,y0,x1,y1, ids: new Int32Array(0), children};
  }

  const root = buildNode(minX, minY, maxX, maxY, ids, 0);
  return {kind:'quadtree', x0:minX, y0:minY, x1:maxX, y1:maxY, maxItems, maxDepth, root};
}

function _aabbIntersectsCircle(x0,y0,x1,y1, cx,cy, r){
  const rx = (cx < x0) ? (x0 - cx) : (cx > x1 ? cx - x1 : 0);
  const ry = (cy < y0) ? (y0 - cy) : (cy > y1 ? cy - y1 : 0);
  return (rx*rx + ry*ry) <= (r*r);
}

export function forEachQuadtreeCandidate(index, cx, cy, r, fn){
  if(!index || index.kind !== 'quadtree' || !index.root) return;
  const stack = [index.root];
  while(stack.length){
    const node = stack.pop();
    if(!_aabbIntersectsCircle(node.x0,node.y0,node.x1,node.y1, cx,cy,r)) continue;
    if(node.children && node.children.length){
      // push all children
      for(let i=0;i<4;i++) stack.push(node.children[i]);
    } else {
      const ids = node.ids;
      for(let i=0;i<ids.length;i++) fn(ids[i]);
    }
  }
}

export function computeRNormFromXY(cells){
  let maxR = 1e-9;
  for(const c of cells){
    const r = Math.hypot(c.x, c.y);
    if(r > maxR) maxR = r;
  }
  for(const c of cells){
    c.rNorm = clamp(Math.hypot(c.x, c.y) / maxR, 0, 1);
  }
}

export function buildGeneIndex(genePanel){
  return new Map(genePanel.map((g,i)=>[String(g).toUpperCase(), i]));
}

// ---------- Demo biology (synthetic dataset only) ----------
export function makeDemoCellTypes(){
  return [
    {key:"Tumor",          color:"#fb7185"},
    {key:"Fibroblast",     color:"#fbbf24"},
    {key:"Endothelial",   color:"#38bdf8"},
    {key:"Macrophage",    color:"#a78bfa"},
    {key:"T cell",        color:"#34d399"},
    {key:"B cell",        color:"#60a5fa"},
    {key:"Epithelial",    color:"#f472b6"},
  ];
}

export function makeDemoGenePanel(){
  return [
    "EPCAM","KRT8","KRT18","MKI67","VIM",
    "COL1A1","COL1A2","DCN","LUM","ACTA2",
    "PECAM1","VWF","KDR",
    "LST1","TYROBP","C1QA","S100A8","S100A9",
    "CD3D","CD3E","TRAC","IL7R","NKG7",
    "MS4A1","CD79A","CD19","MZB1",
    "MALAT1","RPLP0"
  ];
}

const markerBoost = {
  "Tumor":        {EPCAM: 3.0, KRT8:2.2, KRT18:2.0, MKI67:1.3, VIM:0.7},
  "Epithelial":   {EPCAM: 2.4, KRT8:2.0, KRT18:2.0, VIM:0.5},
  "Fibroblast":   {COL1A1:3.2, COL1A2:2.6, DCN:2.1, LUM:2.0, ACTA2:1.2, VIM:0.9},
  "Endothelial":  {PECAM1:3.0, VWF:2.2, KDR:1.6},
  "Macrophage":   {LST1:2.8, TYROBP:2.3, C1QA:2.0, S100A8:1.0, S100A9:1.0},
  "T cell":       {CD3D:2.3, CD3E:2.5, TRAC:2.2, IL7R:1.4, NKG7:0.8},
  "B cell":       {MS4A1:2.2, CD79A:2.2, CD19:2.4, MZB1:1.2},
};

function makeDemoGeneBase(genePanel){
  const geneBase = Object.fromEntries(genePanel.map(g => [g, 0.15]));
  geneBase.MALAT1 = 1.6;
  geneBase.RPLP0  = 1.2;
  geneBase.VIM    = 0.35;
  return geneBase;
}

function makeDemoGeneDropout(genePanel){
  const geneDropout = Object.fromEntries(genePanel.map(g => [g, 0.08]));
  ["CD3D","CD3E","TRAC","IL7R","NKG7","MS4A1","CD79A","CD19","MZB1","LST1","TYROBP","C1QA","S100A8","S100A9","PECAM1","VWF","KDR"].forEach(g=>geneDropout[g]=0.22);
  return geneDropout;
}

function pickType(rand, x,y){
  const r = Math.sqrt(x*x + y*y);
  const rNorm = clamp(r,0,1);
  let w = {
    "Tumor": 0.42,
    "Fibroblast": 0.22,
    "Endothelial": 0.08,
    "Macrophage": 0.11,
    "T cell": 0.11,
    "B cell": 0.03,
    "Epithelial": 0.03,
  };
  w["Tumor"]       *= (1.30 - 0.90*rNorm);
  w["Fibroblast"]  *= (0.70 + 1.10*Math.pow(rNorm, 1.3));
  w["T cell"]      *= (0.55 + 1.20*Math.pow(rNorm, 1.6));
  w["B cell"]      *= (0.45 + 1.35*Math.pow(rNorm, 1.9));
  w["Macrophage"]  *= (0.80 + 0.60*Math.pow(rNorm, 1.1));
  w["Epithelial"]  *= (0.70 + 0.35*Math.sin(8*Math.atan2(y,x) + 1.0));
  w["Endothelial"] *= (0.95 + 0.30*Math.sin(4*Math.atan2(y,x) - 0.6));

  let sum = 0;
  for(const k in w){ sum += Math.max(0, w[k]); }
  let t = rand()*sum;
  for(const k in w){
    t -= Math.max(0, w[k]);
    if(t <= 0) return k;
  }
  return "Tumor";
}

function exprForDemo(rand, randn, cellType, rNorm, genePanel, geneIndex, geneBase, geneDropout){
  const e = new Float32Array(genePanel.length);

  for(let i=0;i<genePanel.length;i++){
    const g = genePanel[i];
    const base = geneBase[g] ?? 0.15;
    const p0 = geneDropout[g] ?? 0.08;
    const isZero = rand() < (p0 + 0.10*(1-base));
    let val = isZero ? 0 : Math.max(0, base + 0.22*randn());
    if(g === 'MKI67') val += (1.0 - rNorm) * 0.55;
    if(g === 'COL1A1' || g === 'COL1A2') val += rNorm * 0.25;
    e[i] = val;
  }

  const boosts = markerBoost[cellType] || {};
  for(const [g,boost] of Object.entries(boosts)){
    const idx = geneIndex.get(String(g).toUpperCase());
    if(idx == null) continue;
    const jitter = 0.15*randn();
    e[idx] = Math.max(0, e[idx] + boost + jitter);
  }

  if(cellType === 'Macrophage'){
    const i8 = geneIndex.get('S100A8'), i9 = geneIndex.get('S100A9');
    const inflamed = rand() < 0.18 ? 1.0 : 0.0;
    if(i8!=null) e[i8] += inflamed * 1.8;
    if(i9!=null) e[i9] += inflamed * 1.7;
  }
  if(cellType === 'Tumor'){
    const emt = rand() < 0.22 ? 1.0 : 0.0;
    const iv = geneIndex.get('VIM');
    if(iv!=null) e[iv] += emt * 1.2;
  }

  return e;
}

export function generateDemoCells(n, genePanel, {seed=0xC0FFEE} = {}){
  const rand = mulberry32(seed);
  const randn = makeRandn(rand);

  const geneIndex = buildGeneIndex(genePanel);
  const geneBase = makeDemoGeneBase(genePanel);
  const geneDropout = makeDemoGeneDropout(genePanel);

  const cells = [];
  for(let i=0;i<n;i++){
    const a = rand() * Math.PI * 2;
    const rr = Math.sqrt(rand());
    let x = rr * Math.cos(a);
    let y = rr * Math.sin(a);
    x *= 1.08;
    y *= 0.94;
    x += 0.06*Math.sin(3*a) * (1-rr);
    y += 0.05*Math.cos(5*a) * (1-rr);

    const notch = (x > 0.75 && y > 0.15);
    if(notch){ i--; continue; }

    const r = Math.sqrt(x*x + y*y);
    const rNorm = clamp(r/1.08, 0, 1);

    const type = pickType(rand, x,y);
    const expr = exprForDemo(rand, randn, type, rNorm, genePanel, geneIndex, geneBase, geneDropout);

    cells.push({
      id: i+1,
      cell_id: String(i+1),
      x, y,
      rNorm,
      type,
      expr,
    });
  }

  return {cells, geneIndex};
}

// ---------- CSV/TSV loading (simple fast parser; no quoted-field support) ----------
export function normalizeHeader(h){
  return String(h || '').trim().replace(/^\uFEFF/, '');
}

export function inferDelimiter(headerLine){
  return headerLine.includes('\t') ? '\t' : ',';
}

export function splitLine(line, delim){
  return line.split(delim).map(s => s.trim());
}

export function buildLoadedDataset(text, filename){
  const lines = text.split(/\r?\n/).filter(l => l.trim().length>0);
  if(lines.length < 2) throw new Error('File has no data rows.');

  const delim = inferDelimiter(lines[0]);
  const headersRaw = splitLine(lines[0], delim).map(normalizeHeader);
  const headers = headersRaw.map(h => h.trim());
  const lower = headers.map(h => h.toLowerCase());

  const idx = (name)=> lower.indexOf(name);
  const iCell = idx('cell_id');
  const iX = idx('x');
  const iY = idx('y');
  const iType = idx('cell_type');

  if(iCell < 0 || iX < 0 || iY < 0){
    throw new Error('Missing required columns. Required: cell_id, x, y. Optional: cell_type.');
  }

  const geneCols = [];
  for(let i=0;i<headers.length;i++){
    if(i===iCell || i===iX || i===iY || i===iType) continue;
    const name = headers[i];
    if(!name) continue;
    geneCols.push({name, i});
  }

  const newGenePanel = geneCols.map(g => g.name);
  const newGeneIndex = new Map(newGenePanel.map((g,i)=>[String(g).toUpperCase(), i]));

  const typeSet = new Map();
  const out = [];

  let badRows = 0;
  for(let r=1;r<lines.length;r++){
    const parts = splitLine(lines[r], delim);
    if(parts.length < headers.length){
      badRows++;
      continue;
    }

    const cell_id = parts[iCell];
    const x = Number.parseFloat(parts[iX]);
    const y = Number.parseFloat(parts[iY]);
    if(!cell_id || !Number.isFinite(x) || !Number.isFinite(y)){
      badRows++;
      continue;
    }

    const t = (iType>=0 ? (parts[iType] || 'Unknown') : 'Unknown');
    typeSet.set(t, true);

    const expr = new Float32Array(newGenePanel.length);
    for(let j=0;j<geneCols.length;j++){
      const raw = parts[geneCols[j].i];
      const v = raw === '' ? 0 : Number.parseFloat(raw);
      expr[j] = Number.isFinite(v) ? v : 0;
    }

    const id = out.length + 1;
    out.push({ id, cell_id, x, y, type: t, expr, rNorm: 0 });
  }

  if(out.length === 0) throw new Error('No valid rows found (check x/y numeric and required columns).');

  computeRNormFromXY(out);

  const typeKeys = [...typeSet.keys()].sort((a,b)=>a.localeCompare(b));
  const newCellTypes = typeKeys.map((k,i)=>({key:k, color: palette(i)}));

  return {
    filename,
    cells: out,
    cellTypes: newCellTypes,
    genePanel: newGenePanel,
    geneIndex: newGeneIndex,
    badRows,
    delim,
  };
}

// ---------- Gate helpers (boolean gating) ----------
export function gateLabelForIndex(i){
  // A, B, ... Z, AA, AB, ...
  let n = i;
  let s = '';
  while(true){
    const r = n % 26;
    s = String.fromCharCode(65 + r) + s;
    n = Math.floor(n/26) - 1;
    if(n < 0) break;
  }
  return s;
}

export function normalizeGateExpr(raw){
  let s = String(raw || '').trim();
  if(!s) return '';
  s = s.replace(/\&\&/g, ' AND ');
  s = s.replace(/\|\|/g, ' OR ');
  s = s.replace(/!/g, ' NOT ');
  s = s.replace(/\s+/g, ' ').trim();
  return s;
}

export function tokenizeGateExpr(expr){
  const s = normalizeGateExpr(expr).toUpperCase();
  if(s === '') return [];
  const tokens = [];
  const re = /\(|\)|\bAND\b|\bOR\b|\bNOT\b|\b[A-Z]+\b/g;
  let m;
  while((m = re.exec(s))){
    tokens.push(m[0]);
  }
  return tokens;
}

export function compileGateToPostfix(tokens){
  // Shunting-yard for operators: NOT > AND > OR
  const out = [];
  const ops = [];
  const prec = { 'NOT': 3, 'AND': 2, 'OR': 1 };
  const rightAssoc = { 'NOT': true };

  for(const t of tokens){
    if(t === '('){
      ops.push(t);
      continue;
    }
    if(t === ')'){
      while(ops.length && ops[ops.length-1] !== '(') out.push(ops.pop());
      if(!ops.length) throw new Error('Mismatched parentheses.');
      ops.pop();
      continue;
    }

    if(t === 'AND' || t === 'OR' || t === 'NOT'){
      while(ops.length){
        const top = ops[ops.length-1];
        if(!(top === 'AND' || top === 'OR' || top === 'NOT')) break;
        const pTop = prec[top] || 0;
        const pT = prec[t] || 0;
        if(pTop > pT || (pTop === pT && !rightAssoc[t])) out.push(ops.pop());
        else break;
      }
      ops.push(t);
      continue;
    }

    // Operand (condition label)
    out.push(t);
  }

  while(ops.length){
    const op = ops.pop();
    if(op === '(' || op === ')') throw new Error('Mismatched parentheses.');
    out.push(op);
  }
  return out;
}

function evalConditionMask({cells, geneIndex}, cond){
  const n = cells.length;
  const mask = new Uint8Array(n);

  const gene = String(cond.gene || '').trim().toUpperCase();
  const idx = gene ? geneIndex.get(gene) : null;
  const cutoff = Number(cond.cutoff);
  const c = Number.isFinite(cutoff) ? cutoff : 0;

  if(idx == null){
    return {mask, missing: gene || null};
  }

  const pos = cond.sense !== 'neg';
  for(let i=0;i<n;i++){
    const v = cells[i].expr ? (cells[i].expr[idx] ?? 0) : 0;
    const ok = pos ? (v >= c) : (v < c);
    mask[i] = ok ? 1 : 0;
  }
  return {mask, missing: null};
}

function applyNot(mask){
  const out = new Uint8Array(mask.length);
  for(let i=0;i<mask.length;i++) out[i] = mask[i] ? 0 : 1;
  return out;
}
function applyAnd(a,b){
  const out = new Uint8Array(a.length);
  for(let i=0;i<a.length;i++) out[i] = (a[i] & b[i]);
  return out;
}
function applyOr(a,b){
  const out = new Uint8Array(a.length);
  for(let i=0;i<a.length;i++) out[i] = (a[i] | b[i]);
  return out;
}

export function evaluateGate({cells, geneIndex, gateEnabled, gateConditions, gateExpr}){
  // Returns: { mask: Uint8Array|null, matchCount: number, error: string|null }
  const enabled = !!gateEnabled;
  if(!enabled || !gateConditions || gateConditions.length === 0){
    return {mask: null, matchCount: 0, error: null};
  }

  const labelToMask = new Map();
  const missingGenes = [];

  for(let i=0;i<gateConditions.length;i++){
    const label = gateLabelForIndex(i);
    const {mask, missing} = evalConditionMask({cells, geneIndex}, gateConditions[i]);
    if(missing) missingGenes.push(missing);
    labelToMask.set(label, mask);
  }

  const expr = normalizeGateExpr(gateExpr);
  if(!expr){
    return {mask: null, matchCount: 0, error: 'Expression is empty.'};
  }

  try{
    const tokens = tokenizeGateExpr(expr);
    const postfix = compileGateToPostfix(tokens);

    const stack = [];
    for(const t of postfix){
      if(t === 'AND' || t === 'OR'){
        const b = stack.pop();
        const a = stack.pop();
        if(!a || !b) throw new Error('Invalid expression (missing operands).');
        stack.push(t === 'AND' ? applyAnd(a,b) : applyOr(a,b));
      } else if(t === 'NOT'){
        const a = stack.pop();
        if(!a) throw new Error('Invalid expression (NOT missing operand).');
        stack.push(applyNot(a));
      } else {
        const m = labelToMask.get(t);
        if(!m) throw new Error(`Unknown condition label: ${t}`);
        stack.push(m);
      }
    }
    if(stack.length !== 1) throw new Error('Invalid expression (did not reduce to a single result).');

    const mask = stack[0];
    let matchCount = 0;
    for(let i=0;i<mask.length;i++) matchCount += mask[i] ? 1 : 0;

    let error = null;
    if(missingGenes.length){
      const uniq = [...new Set(missingGenes)].filter(Boolean);
      error = `Missing genes: ${uniq.slice(0,4).join(', ')}${uniq.length>4?'…':''}`;
    }

    return {mask, matchCount, error};
  } catch (err){
    return {mask: null, matchCount: 0, error: String(err && err.message ? err.message : err)};
  }
}

// ---------- Filename helpers (exports) ----------
export function sanitizeForFilename(s){
  return String(s || '')
    .trim()
    .replace(/\s+/g,'-')
    .replace(/[^a-zA-Z0-9._-]+/g,'-')
    .replace(/-+/g,'-')
    .replace(/^-|-$/g,'');
}

export function timestampForFilename(d = new Date()){
  return d.toISOString().replace(/[:]/g,'').replace(/\.\d{3}Z$/,'Z').replace('T','_');
}
