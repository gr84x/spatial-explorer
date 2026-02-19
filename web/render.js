// render.js — Canvas rendering + picking + view transforms (ES module)

import { clamp, lerp, hexToRgb, rgba, querySpatialIndex, forEachQuadtreeCandidate } from './data.js';
import { now, ema } from './perf.js';
import { computeScaleBar } from './scale_bar.js';
import { createWebGLPointsRenderer } from './webgl_points.js';

/**
 * Create the renderer responsible for drawing, hit-testing (picking), and
 * maintaining the current view transform.
 *
 * @param {object} args
 * @param {HTMLCanvasElement} args.canvas - 2D overlay canvas.
 * @param {HTMLCanvasElement | null} [args.glCanvas=null] - Optional WebGL underlay canvas.
 * @param {() => object} args.getState - Getter for the mutable app state.
 * @param {() => void} [args.onLegendCounts] - Callback to refresh legend counts.
 */
export function createRenderer({canvas, glCanvas=null, getState, onLegendCounts}){
  // canvas: 2D overlay (interaction + boundary/text/scale bar)
  // glCanvas: optional WebGL canvas underlay for fast point rendering
  if(!canvas) throw new Error('Renderer requires a canvas element.');

  const view = { scale: 240, tx: 0, ty: 0 };
  let _pendingInitialFit = false;

  // rAF render scheduler (prevents redundant full redraws during fast pan/zoom/hover)
  let _raf = 0;
  let _needs = false;
  let _lastRect = null;
  let _lastCssW = null;
  let _lastCssH = null;

  // tiny perf telemetry (used for PERF_NOTES + optional UI display)
  const perf = {
    renderMsEma: null,
    pickMsEma: null,
    lastRenderMs: null,
    lastPickMs: null,
  };

  // Optional WebGL underlay (instanced circles). If unavailable, we fall back to pure 2D canvas.
  const glBackend = glCanvas ? createWebGLPointsRenderer({canvas: glCanvas}) : null;
  let _glStaticUploaded = false;
  let _glLastColorKey = null;
  let _glLastGateRef = null;
  let _glLastLodStride = null;

  function _cssVar(name, fallback){
    try{
      const v = getComputedStyle(document.documentElement).getPropertyValue(name);
      const s = String(v || '').trim();
      return s || fallback;
    } catch {
      return fallback;
    }
  }

  function worldToScreen(x,y){
    return { x: x*view.scale + view.tx, y: y*view.scale + view.ty };
  }
  function screenToWorld(px,py){
    return { x: (px - view.tx)/view.scale, y: (py - view.ty)/view.scale };
  }

  function resetViewToFit(){
    const rect = canvas.getBoundingClientRect();
    const s = Math.min(rect.width, rect.height) * 0.44;
    view.scale = Math.max(140, s);
    view.tx = rect.width/2;
    view.ty = rect.height/2;
  }

  function resizeCanvas({initial=false} = {}){
    if(initial) _pendingInitialFit = true;
    const dpr = Math.max(1, Math.min(2.5, window.devicePixelRatio || 1));
    const rect = canvas.getBoundingClientRect();

    // If the element isn't laid out yet (e.g. display:none or still attaching),
    // don't lock in a bogus 1×1 backing store. A ResizeObserver / later render
    // will retrigger once layout is stable.
    if(rect.width <= 0 || rect.height <= 0){
      return;
    }

    // Persist the current CSS pixel size so we can detect layout-driven resizes
    // (e.g. fonts finishing loading / flex reflow) that don't emit a window
    // resize event.
    _lastCssW = rect.width;
    _lastCssH = rect.height;

    // Round to nearest device pixel to reduce CSS stretching due to fractional
    // backing store sizes.
    const pxW = Math.max(1, Math.round(rect.width * dpr));
    const pxH = Math.max(1, Math.round(rect.height * dpr));

    // Use the *actual* backing-store-to-CSS scale for each axis.
    const sx = pxW / Math.max(1e-6, rect.width);
    const sy = pxH / Math.max(1e-6, rect.height);

    // Overlay 2D canvas (interaction + annotation)
    canvas.width = pxW;
    canvas.height = pxH;
    const ctx = canvas.getContext('2d');
    ctx.setTransform(sx,0,0,sy,0,0);

    // WebGL underlay canvas (points)
    if(glCanvas && glBackend){
      glCanvas.width = pxW;
      glCanvas.height = pxH;
      glBackend.resizeViewport();
    }

    if(initial || _pendingInitialFit){
      resetViewToFit();
      _pendingInitialFit = false;
    } else {
      // Keep the visualization centered.
      view.tx = rect.width/2;
      view.ty = rect.height/2;
    }
    requestRender();
  }

  // Keep backing store in sync with CSS size even when layout changes occur
  // without a window resize or an interaction-driven render (e.g. web font load,
  // sidebar wrap, container transitions). If the backing store falls out of
  // sync, the browser stretches the canvas bitmap and circles become ellipses.
  let _ro = null;
  let _roRaf = 0;
  function _scheduleObservedResize(){
    if(_roRaf) return;
    _roRaf = requestAnimationFrame(()=>{
      _roRaf = 0;
      resizeCanvas({initial:false});
    });
  }

  if(typeof ResizeObserver === 'function'){
    try{
      _ro = new ResizeObserver(_scheduleObservedResize);
      _ro.observe(canvas);
    } catch {}
  }
  if(window.visualViewport && typeof window.visualViewport.addEventListener === 'function'){
    // Mobile pinch zoom can change devicePixelRatio without a classic window resize.
    window.visualViewport.addEventListener('resize', _scheduleObservedResize);
  }

  function cellRadiusPx(){
    return clamp(2.3 + (view.scale/260), 2.2, 4.6);
  }

  function visibleCells(){
    const st = getState();
    return st.cells.filter(c => st.activeTypes.get(c.type));
  }

  function geneColor(v, vMin, vMax){
    const t = (vMax <= vMin) ? 0 : clamp((v - vMin) / (vMax - vMin), 0, 1);
    const tt = Math.pow(t, 0.65);
    const low = {r: 120, g: 130, b: 150};
    const root = getComputedStyle(document.documentElement);
    const mid = hexToRgb(root.getPropertyValue('--accent').trim() || '#60a5fa');
    const hi  = hexToRgb(root.getPropertyValue('--green').trim()  || '#22c55e');

    const c = tt < 0.55
      ? { r: Math.round(lerp(low.r, mid.r, tt/0.55)), g: Math.round(lerp(low.g, mid.g, tt/0.55)), b: Math.round(lerp(low.b, mid.b, tt/0.55)) }
      : { r: Math.round(lerp(mid.r, hi.r, (tt-0.55)/0.45)), g: Math.round(lerp(mid.g, hi.g, (tt-0.55)/0.45)), b: Math.round(lerp(mid.b, hi.b, (tt-0.55)/0.45)) };

    return rgba(c, 0.95);
  }

  function computeGeneRange(idx){
    const st = getState();

    // Cache key includes activeTypes version so toggling types invalidates.
    const v = st._activeTypesVersion || 0;
    if(!st._geneRangeCache) st._geneRangeCache = new Map();
    const key = idx + '|' + v;
    const hit = st._geneRangeCache.get(key);
    if(hit) return hit;

    // For 10K+ points, sorting every frame is too expensive.
    // We compute percentiles once per gene+filter change and cache.
    const vals = [];
    const cells = st.cells;
    const active = st.activeTypes;
    for(let i=0;i<cells.length;i++){
      const c = cells[i];
      if(!active.get(c.type)) continue;
      vals.push(c.expr ? (c.expr[idx] ?? 0) : 0);
    }
    if(vals.length === 0){
      const out = {min:0, max:1};
      st._geneRangeCache.set(key, out);
      return out;
    }

    vals.sort((a,b)=>a-b);
    const p = (q)=> vals[(q*(vals.length-1))|0];
    const out = {min:p(0.05), max:p(0.95)};
    st._geneRangeCache.set(key, out);
    return out;
  }

  function drawTissueBoundary(ctx, w, h){
    ctx.save();
    ctx.translate(view.tx, view.ty);
    ctx.scale(view.scale, view.scale);
    ctx.lineWidth = 1/view.scale;
    ctx.beginPath();
    const steps = 200;
    for(let i=0;i<=steps;i++){
      const a = i/steps * Math.PI*2;
      const r = 1.05;
      const x = r*Math.cos(a);
      const y = r*Math.sin(a);
      if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
    }
    ctx.closePath();
    ctx.fillStyle = _cssVar('--tissue-fill', 'rgba(255,255,255,.015)');
    ctx.fill();
    ctx.strokeStyle = _cssVar('--tissue-stroke', 'rgba(255,255,255,.07)');
    ctx.stroke();
    ctx.restore();
  }

  function drawScaleBar(ctx, w, h){
    const st = getState();
    const bar = computeScaleBar({umPerPixel: st.umPerPixel, viewScale: view.scale, targetPx: 110});
    if(!bar) return;

    const {barPx, label} = bar;

    const pad = 14;
    const barH = 6;

    ctx.save();
    ctx.font = '12px ' + getComputedStyle(document.body).fontFamily;
    const textW = ctx.measureText(label).width;

    const boxW = Math.max(barPx, textW) + 16;
    const boxH = 32;
    const bx = w - pad - boxW;
    const by = h - pad - boxH;

    ctx.fillStyle = _cssVar('--scalebox-bg', 'rgba(16,18,20,.72)');
    ctx.strokeStyle = _cssVar('--scalebox-stroke', 'rgba(255,255,255,.12)');
    ctx.lineWidth = 1;
    ctx.beginPath();
    const r = 10;
    ctx.moveTo(bx+r, by);
    ctx.arcTo(bx+boxW, by, bx+boxW, by+boxH, r);
    ctx.arcTo(bx+boxW, by+boxH, bx, by+boxH, r);
    ctx.arcTo(bx, by+boxH, bx, by, r);
    ctx.arcTo(bx, by, bx+boxW, by, r);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();

    const barX = w - pad - barPx;
    const barY = h - pad - 12;
    ctx.fillStyle = _cssVar('--scalebar', 'rgba(255,255,255,.85)');
    ctx.fillRect(barX, barY, barPx, barH);
    ctx.fillStyle = _cssVar('--scalebar-top', 'rgba(0,0,0,.35)');
    ctx.fillRect(barX, barY, barPx, 1);

    ctx.fillStyle = _cssVar('--scale-text', 'rgba(255,255,255,.82)');
    ctx.textBaseline = 'bottom';
    ctx.fillText(label, w - pad - textW, barY - 4);

    ctx.restore();
  }

  function renderTo(ctx, w, h){
    const st = getState();

    ctx.clearRect(0,0,w,h);
    drawTissueBoundary(ctx, w, h);

    const scale = view.scale;
    const tx = view.tx;
    const ty = view.ty;
    const rPx = cellRadiusPx();

    const cells = st.cells;
    const active = st.activeTypes;
    const selId = st.selectedId;
    const hovId = st.hoveredId;
    const geneIdx = st.geneIdx;

    let range = null;
    if(geneIdx != null) range = computeGeneRange(geneIdx);

    // non-selected first
    ctx.save();
    ctx.globalAlpha = 0.85;
    for(let i=0;i<cells.length;i++){
      const c = cells[i];
      if(!active.get(c.type)) continue;
      const id = c.id;
      if(id === selId || id === hovId) continue;

      const px = c.x * scale + tx;
      const py = c.y * scale + ty;

      let fill;
      if(geneIdx != null && c.expr){
        fill = geneColor(c.expr[geneIdx] ?? 0, range.min, range.max);
      } else {
        const rgb = st.typeColorRgb.get(c.type) || {r:200,g:200,b:200};
        fill = rgba(rgb, 0.92);
      }

      ctx.beginPath();
      ctx.fillStyle = fill;
      ctx.arc(px, py, rPx, 0, Math.PI*2);
      ctx.fill();
    }
    ctx.restore();

    // outlines in gene mode
    if(geneIdx != null){
      ctx.save();
      ctx.globalAlpha = 0.65;
      ctx.lineWidth = 1;
      for(let i=0;i<cells.length;i++){
        const c = cells[i];
        if(!active.get(c.type)) continue;
        const id = c.id;
        if(id === selId || id === hovId) continue;

        const px = c.x * scale + tx;
        const py = c.y * scale + ty;
        const rgb = st.typeColorRgb.get(c.type) || {r:200,g:200,b:200};
        ctx.strokeStyle = rgba(rgb, 0.55);
        ctx.beginPath();
        ctx.arc(px, py, rPx+0.8, 0, Math.PI*2);
        ctx.stroke();
      }
      ctx.restore();
    }

    // Gate highlight overlay
    if(st.gateMask && st.gate && st.gate.enabled){
      ctx.save();
      ctx.globalAlpha = 0.95;
      ctx.lineWidth = 2;
      ctx.strokeStyle = 'rgba(250,204,21,.92)';
      const mask = st.gateMask;
      for(let i=0;i<cells.length;i++){
        const c = cells[i];
        if(!active.get(c.type)) continue;
        if(!mask[c.id-1]) continue;
        const px = c.x * scale + tx;
        const py = c.y * scale + ty;
        ctx.beginPath();
        ctx.arc(px, py, rPx+2.4, 0, Math.PI*2);
        ctx.stroke();
      }
      ctx.restore();
    }

    // hovered / selected
    for(const id of [hovId, selId]){
      if(id == null) continue;
      const c = cells[id-1];
      if(!c || !active.get(c.type)) continue;

      const px = c.x * scale + tx;
      const py = c.y * scale + ty;

      const rgb = st.typeColorRgb.get(c.type) || {r:200,g:200,b:200};
      const fill = (geneIdx != null && c.expr)
        ? geneColor(c.expr[geneIdx] ?? 0, range.min, range.max)
        : rgba(rgb, 0.96);

      ctx.save();
      ctx.beginPath();
      ctx.fillStyle = fill;
      ctx.arc(px, py, rPx+1.4, 0, Math.PI*2);
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = _cssVar('--hover-ring', 'rgba(255,255,255,.85)');
      ctx.stroke();
      ctx.restore();
    }

    // corner annotation
    ctx.save();
    ctx.font = '12px ' + getComputedStyle(document.body).fontFamily;
    ctx.fillStyle = _cssVar('--annotation', 'rgba(255,255,255,.66)');
    const gtxt = geneIdx == null ? 'Cell type' : `Gene: ${st.genePanel[geneIdx]} (expression)`;
    ctx.fillText(gtxt, 14, h - 14);
    ctx.restore();

    drawScaleBar(ctx, w, h);

    if(onLegendCounts) onLegendCounts();
  }

  function _geneColorRgb(v, vMin, vMax, {midRgb, hiRgb}){
    const t = (vMax <= vMin) ? 0 : clamp((v - vMin) / (vMax - vMin), 0, 1);
    const tt = Math.pow(t, 0.65);
    const low = {r: 120, g: 130, b: 150};
    const mid = midRgb;
    const hi = hiRgb;

    const c = tt < 0.55
      ? { r: Math.round(lerp(low.r, mid.r, tt/0.55)), g: Math.round(lerp(low.g, mid.g, tt/0.55)), b: Math.round(lerp(low.b, mid.b, tt/0.55)) }
      : { r: Math.round(lerp(mid.r, hi.r, (tt-0.55)/0.45)), g: Math.round(lerp(mid.g, hi.g, (tt-0.55)/0.45)), b: Math.round(lerp(mid.b, hi.b, (tt-0.55)/0.45)) };

    return c;
  }

  function _lodStrideForScale(scale){
    // Simple LOD: when zoomed far out, subsample instances to reduce overdraw.
    if(scale >= 160) return 1;
    const s = Math.ceil(160 / Math.max(1e-6, scale));
    return clamp(s, 1, 12) | 0;
  }

  function _ensureGlBuffers({rect}){
    if(!glBackend || !glCanvas) return;
    const st = getState();

    // Upload static positions once per dataset reference.
    if(!_glStaticUploaded || glBackend._cellsRef !== st.cells){
      const worldXY = new Float32Array(st.cells.length * 2);
      for(let i=0;i<st.cells.length;i++){
        const c = st.cells[i];
        worldXY[i*2+0] = c.x;
        worldXY[i*2+1] = c.y;
      }
      glBackend.uploadStatic({worldXY});
      glBackend._cellsRef = st.cells;
      _glStaticUploaded = true;
      _glLastColorKey = null;
      _glLastGateRef = null;
      _glLastLodStride = null;
    }

    const geneIdx = st.geneIdx;
    const activeVer = st._activeTypesVersion || 0;
    const lodStride = _lodStrideForScale(view.scale);

    const colorKey = `${geneIdx == null ? 'type' : geneIdx}|${activeVer}|${lodStride}`;

    const needsColor = (_glLastColorKey !== colorKey);
    const needsGate = (_glLastGateRef !== st.gateMask);

    if(!needsColor && !needsGate) return;

    const n = st.cells.length;

    const colors = new Uint8Array(n * 4);
    const radii = new Float32Array(n);
    const visible = new Uint8Array(n);
    const gate = new Uint8Array(n);

    const rPx = cellRadiusPx();

    // Cache theme colors used for gene gradient. This is only recomputed on buffer rebuild.
    const root = getComputedStyle(document.documentElement);
    const midRgb = hexToRgb(root.getPropertyValue('--accent').trim() || '#60a5fa');
    const hiRgb  = hexToRgb(root.getPropertyValue('--green').trim()  || '#22c55e');

    let range = null;
    if(geneIdx != null) range = computeGeneRange(geneIdx);

    const active = st.activeTypes;
    const typeColorRgb = st.typeColorRgb;

    for(let i=0;i<n;i++){
      const c = st.cells[i];
      const isActive = !!active.get(c.type);
      const isLodOn = (lodStride <= 1) ? true : ((c.id % lodStride) === 0);
      const vis = (isActive && isLodOn) ? 255 : 0;
      visible[i] = vis;

      radii[i] = rPx;

      // Fill + ring colors
      const typeRgb = typeColorRgb.get(c.type) || {r:200,g:200,b:200};

      // Ring (type outline) is always the type color.
      // Fill is either type color (default) or gene gradient.
      let fillRgb = typeRgb;
      let fillA = 235;
      if(geneIdx != null && c.expr){
        fillRgb = _geneColorRgb(c.expr[geneIdx] ?? 0, range.min, range.max, {midRgb, hiRgb});
        fillA = 242;
      }

      colors[i*4+0] = fillRgb.r;
      colors[i*4+1] = fillRgb.g;
      colors[i*4+2] = fillRgb.b;
      colors[i*4+3] = fillA;

      // Gate mask for gate ring pass (keep 0 if invisible)
      const m = st.gateMask;
      gate[i] = (vis && m && m[c.id-1]) ? 255 : 0;
    }

    // Build ring colors (type outlines) only when needed.
    let ringColors = null;
    if(geneIdx != null){
      ringColors = new Uint8Array(n * 4);
      for(let i=0;i<n;i++){
        if(!visible[i]){ ringColors[i*4+3] = 0; continue; }
        const c = st.cells[i];
        const rgb = typeColorRgb.get(c.type) || {r:200,g:200,b:200};
        ringColors[i*4+0] = rgb.r;
        ringColors[i*4+1] = rgb.g;
        ringColors[i*4+2] = rgb.b;
        ringColors[i*4+3] = 140; // ~0.55
      }
    }

    glBackend.uploadDynamic({
      fillColorsRgba: colors,
      ringColorsRgba: ringColors,
      radiiPx: radii,
      visibleMask: visible,
      gateMask: gate,
    });

    _glLastColorKey = colorKey;
    _glLastGateRef = st.gateMask;
    _glLastLodStride = lodStride;
  }

  function _renderOverlay(ctx, w, h){
    // Overlay only: boundary + labels + scale bar + hover/selection rings.
    const st = getState();

    ctx.clearRect(0,0,w,h);
    drawTissueBoundary(ctx, w, h);

    // hover/selection (2 arcs only; cheap)
    const scale = view.scale;
    const tx = view.tx;
    const ty = view.ty;
    const rPx = cellRadiusPx();

    let range = null;
    if(st.geneIdx != null) range = computeGeneRange(st.geneIdx);

    for(const id of [st.hoveredId, st.selectedId]){
      if(id == null) continue;
      const c = st.cells[id-1];
      if(!c || !st.activeTypes.get(c.type)) continue;

      const px = c.x * scale + tx;
      const py = c.y * scale + ty;

      const rgb = st.typeColorRgb.get(c.type) || {r:200,g:200,b:200};
      const fill = (st.geneIdx != null && c.expr)
        ? geneColor(c.expr[st.geneIdx] ?? 0, range.min, range.max)
        : rgba(rgb, 0.96);

      ctx.save();
      ctx.beginPath();
      ctx.fillStyle = fill;
      ctx.arc(px, py, rPx+1.4, 0, Math.PI*2);
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = _cssVar('--hover-ring', 'rgba(255,255,255,.85)');
      ctx.stroke();
      ctx.restore();
    }

    // corner annotation
    ctx.save();
    ctx.font = '12px ' + getComputedStyle(document.body).fontFamily;
    ctx.fillStyle = _cssVar('--annotation', 'rgba(255,255,255,.66)');
    const gtxt = st.geneIdx == null ? 'Cell type' : `Gene: ${st.genePanel[st.geneIdx]} (expression)`;
    ctx.fillText(gtxt, 14, h - 14);
    ctx.restore();

    drawScaleBar(ctx, w, h);

    if(onLegendCounts) onLegendCounts();
  }

  function render(){
    const t0 = now();
    const rect = canvas.getBoundingClientRect();

    // Layout changes can resize the canvas without triggering a window resize
    // event (e.g. web fonts loading, flex wrapping). If the backing store size
    // doesn't match the displayed CSS size, the browser will scale the bitmap
    // and circles can appear as ellipses.
    if(_lastCssW == null || _lastCssH == null || Math.abs(rect.width - _lastCssW) > 0.5 || Math.abs(rect.height - _lastCssH) > 0.5){
      resizeCanvas({initial:false});
      return;
    }

    _lastRect = rect;

    if(glBackend && glCanvas){
      _ensureGlBuffers({rect});

      const st = getState();

      // Draw points
      glBackend.render({
        canvasCssWidth: rect.width,
        canvasCssHeight: rect.height,
        scale: view.scale,
        tx: view.tx,
        ty: view.ty,
        drawTypeOutlines: (st.geneIdx != null),
        drawGateRings: !!(st.gateMask && st.gate && st.gate.enabled),
      });

      // Overlay pass
      const ctx = canvas.getContext('2d');
      _renderOverlay(ctx, rect.width, rect.height);
    } else {
      const ctx = canvas.getContext('2d');
      renderTo(ctx, rect.width, rect.height);
    }

    const dt = now() - t0;
    perf.lastRenderMs = dt;
    perf.renderMsEma = ema(perf.renderMsEma, dt, 0.15);
  }

  function requestRender(){
    _needs = true;
    if(_raf) return;
    _raf = requestAnimationFrame(()=>{
      _raf = 0;
      if(!_needs) return;
      _needs = false;
      render();
    });
  }

  function findNearestCell(clientX, clientY){
    const t0 = now();
    const st = getState();
    const rect = _lastRect || canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;

    const wpt = screenToWorld(x,y);
    const rWorld = (cellRadiusPx() + 4) / view.scale;
    const r2 = rWorld * rWorld;

    let best = null;
    let bestD2 = Infinity;

    const idx = st.spatialIndex;
    const active = st.activeTypes;

    if(idx && idx.kind === 'quadtree'){
      forEachQuadtreeCandidate(idx, wpt.x, wpt.y, rWorld, (id)=>{
        const c = st.cells[id-1];
        if(!c || !active.get(c.type)) return;
        const dx = c.x - wpt.x;
        const dy = c.y - wpt.y;
        const d2 = dx*dx + dy*dy;
        if(d2 < r2 && d2 < bestD2){
          best = c;
          bestD2 = d2;
        }
      });
    } else if(idx && idx.kind === 'grid' && idx.buckets && idx.buckets.length){
      const q = querySpatialIndex(idx, wpt.x, wpt.y, rWorld);
      if(q){
        const {ix0, ix1, iy0, iy1} = q;
        for(let iy=iy0; iy<=iy1; iy++){
          const row = iy * idx.nx;
          for(let ix=ix0; ix<=ix1; ix++){
            const bucket = idx.buckets[row + ix];
            for(let k=0;k<bucket.length;k++){
              const id = bucket[k];
              const c = st.cells[id-1];
              if(!c || !active.get(c.type)) continue;
              const dx = c.x - wpt.x;
              const dy = c.y - wpt.y;
              const d2 = dx*dx + dy*dy;
              if(d2 < r2 && d2 < bestD2){
                best = c;
                bestD2 = d2;
              }
            }
          }
        }
      }
    } else {
      // fallback: brute force
      const cells = st.cells;
      for(let i=0;i<cells.length;i++){
        const c = cells[i];
        if(!active.get(c.type)) continue;
        const dx = c.x - wpt.x;
        const dy = c.y - wpt.y;
        const d2 = dx*dx + dy*dy;
        if(d2 < r2 && d2 < bestD2){
          best = c;
          bestD2 = d2;
        }
      }
    }

    const dt = now() - t0;
    perf.lastPickMs = dt;
    perf.pickMsEma = ema(perf.pickMsEma, dt, 0.2);
    return best;
  }

  return {
    view,
    perf,
    worldToScreen,
    screenToWorld,
    resetViewToFit,
    resizeCanvas,
    cellRadiusPx,
    visibleCells,
    computeGeneRange,
    geneColor,
    renderTo,
    render,
    requestRender,
    findNearestCell,
  };
}
