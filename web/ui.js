// ui.js — UI controls + DOM/event wiring (ES module)

import {
  clamp,
  hexToRgb,
  rgba,
  zoneLabel,
  palette,
  gateLabelForIndex,
  evaluateGate,
  buildLoadedDataset,
  sanitizeForFilename,
  timestampForFilename,
  buildQuadtreeIndex,
  buildSpatialIndex,
} from './data.js';

import { fmtMs } from './perf.js';
import { computeScaleBar } from './scale_bar.js';

// ---------- URL state (shareable links) ----------
const URL_STATE_VERSION = 1;

function _parseNum(v){
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function readStateFromUrl(){
  const raw = (location.hash && location.hash.length > 1)
    ? location.hash.slice(1)
    : (location.search && location.search.length > 1 ? location.search.slice(1) : '');
  const p = new URLSearchParams(raw);
  const v = _parseNum(p.get('v')) ?? URL_STATE_VERSION;
  if(v !== URL_STATE_VERSION) return null;

  const z = _parseNum(p.get('z'));
  const x = _parseNum(p.get('x'));
  const y = _parseNum(p.get('y'));
  const g = p.get('g');
  const c = _parseNum(p.get('c'));
  const u = _parseNum(p.get('u'));

  const st = {};
  if(z != null) st.z = z;
  if(x != null) st.x = x;
  if(y != null) st.y = y;
  if(typeof g === 'string' && g.trim() !== '') st.g = g.trim();
  if(c != null) st.c = c;
  if(u != null) st.u = u;
  return st;
}

export function createUi({dom, renderer, state, dataApi}){
  // state is a mutable object owned by app.js
  // renderer is createRenderer(...)
  const {
    canvas,
    tip,
    dropEl,
    welcomeEl,
    welcomeUploadBtn,
    welcomeDismissBtn,
    legendEl,
    visStatus,
    datasetLabel,
    datasetBadgeText,

    geneInput,
    geneList,
    geneHint,

    loadBtn,
    fileInput,

    exportBtn,
    exportSvgBtn,
    exportScaleSel,
    umPerPxEl,

    emptySel,
    selWrap,
    selIdEl,
    selTypeEl,
    selXYEl,
    selZoneEl,
    barsEl,

    gateRowsEl,
    gateAddBtn,
    gateClearBtn,
    gateEnabledEl,
    gateExprEl,
    gateAdvancedEl,
    gateStatusEl,
    gateCopyBtn,
    gatePasteBtn,

    resetBtn,
    zinBtn,
    zoutBtn,
    themeToggleBtn,
  } = dom;

  let _restoringFromUrl = false;
  let _urlSyncTimer = null;

  // ---------- Theme (light/dark) ----------
  const THEME_KEY = 'spatialExplorer.theme';
  const mql = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;

  function systemTheme(){
    return (mql && mql.matches) ? 'light' : 'dark';
  }

  function appliedTheme(){
    const t = document.documentElement.getAttribute('data-theme');
    return (t === 'light' || t === 'dark') ? t : null;
  }

  function effectiveTheme(){
    return appliedTheme() || systemTheme();
  }

  function setThemePreference(pref){
    // pref: 'light' | 'dark' | null (null => follow system)
    if(pref === 'light' || pref === 'dark'){
      document.documentElement.setAttribute('data-theme', pref);
      try{ localStorage.setItem(THEME_KEY, pref); } catch {}
    } else {
      document.documentElement.removeAttribute('data-theme');
      try{ localStorage.removeItem(THEME_KEY); } catch {}
    }
    updateThemeToggleLabel();
    renderer.requestRender();
  }

  function updateThemeToggleLabel(){
    if(!themeToggleBtn) return;
    const eff = effectiveTheme();
    const next = eff === 'light' ? 'dark' : 'light';
    themeToggleBtn.textContent = next === 'light' ? 'Light' : 'Dark';
    themeToggleBtn.setAttribute('aria-label', `Switch to ${next} theme`);
    themeToggleBtn.title = `Switch to ${next} theme`;
  }

  function initTheme(){
    let saved = null;
    try{ saved = localStorage.getItem(THEME_KEY); } catch {}
    if(saved === 'light' || saved === 'dark'){
      document.documentElement.setAttribute('data-theme', saved);
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
    updateThemeToggleLabel();

    if(themeToggleBtn){
      themeToggleBtn.addEventListener('click', ()=>{
        const eff = effectiveTheme();
        setThemePreference(eff === 'light' ? 'dark' : 'light');
      });

      themeToggleBtn.addEventListener('contextmenu', (e)=>{
        // Right click resets to system preference.
        e.preventDefault();
        setThemePreference(null);
      });
    }

    // Keep in sync with system changes when user follows system.
    if(mql){
      const handler = ()=>{
        if(appliedTheme() == null){
          updateThemeToggleLabel();
          renderer.requestRender();
        }
      };
      // addEventListener is preferred, but Safari still uses addListener.
      if(typeof mql.addEventListener === 'function') mql.addEventListener('change', handler);
      else if(typeof mql.addListener === 'function') mql.addListener(handler);
    }
  }

  function scheduleUrlSync(){
    if(_restoringFromUrl) return;
    clearTimeout(_urlSyncTimer);
    _urlSyncTimer = setTimeout(()=>{
      const p = new URLSearchParams();
      p.set('v', String(URL_STATE_VERSION));
      p.set('z', String(Math.round(renderer.view.scale)));
      p.set('x', String(Math.round(renderer.view.tx)));
      p.set('y', String(Math.round(renderer.view.ty)));
      if(state.geneQuery) p.set('g', state.geneQuery);
      if(state.selectedId != null) p.set('c', String(state.selectedId));
      if(state.umPerPixel > 0) p.set('u', String(state.umPerPixel));

      const nextHash = `#${p.toString()}`;
      if(nextHash !== location.hash){
        history.replaceState(null, '', nextHash);
      }
    }, 150);
  }

  function applyStateFromUrl(){
    const st = readStateFromUrl();
    if(!st) return;

    _restoringFromUrl = true;
    try{
      if(st.z != null){
        renderer.view.scale = clamp(Math.round(st.z), 90, 1200);
      }
      if(st.x != null || st.y != null){
        const rect = canvas.getBoundingClientRect();
        const w = Math.max(1, rect.width);
        const h = Math.max(1, rect.height);
        if(st.x != null) renderer.view.tx = clamp(Math.round(st.x), -5*w, 6*w);
        if(st.y != null) renderer.view.ty = clamp(Math.round(st.y), -5*h, 6*h);
      }

      if(st.g != null){
        const g = String(st.g).trim().toUpperCase();
        if(state.geneIndex.get(g) != null){
          geneInput.value = g;
          setGeneQuery(g);
        }
      }

      if(st.c != null){
        const id = Math.round(st.c);
        const c = (id >= 1 && id <= state.cells.length) ? state.cells[id-1] : null;
        if(c){
          state.selectedId = id;
          setSelected(c);
        }
      }

      if(st.u != null){
        setUmPerPixel(st.u, {syncUrl:false});
      }
    } finally {
      _restoringFromUrl = false;
    }
  }

  // ---------- Welcome overlay ----------
  function shouldShowWelcome(){
    if(!welcomeEl) return false;
    // Treat the built-in demo as “no user data loaded yet”.
    const isDemo = String(state.datasetName || '').toLowerCase().includes('synthetic');
    if(!isDemo) return false;
    try{
      return localStorage.getItem('spatialExplorer.welcomeDismissed') !== '1';
    } catch {
      return true;
    }
  }

  function setWelcomeVisible(on){
    if(!welcomeEl) return;
    welcomeEl.style.display = on ? 'grid' : 'none';
  }

  function updateWelcome(){
    setWelcomeVisible(shouldShowWelcome());
  }

  // ---------- Tooltip ----------
  function showTip(c, x, y){
    const xy = `(${c.x.toFixed(3)}, ${c.y.toFixed(3)})`;
    const idLabel = c.cell_id != null ? c.cell_id : String(c.id);
    tip.innerHTML = `<div><strong>${c.type}</strong> <span class="muted">• ${idLabel}</span></div>`
      + `<div class="muted">x,y ${xy} • ${zoneLabel(c.rNorm ?? 0)} region</div>`
      + (state.geneIdx != null && c.expr ? `<div class="muted">${state.genePanel[state.geneIdx]}: <strong style="color:var(--text)">${(c.expr[state.geneIdx] ?? 0).toFixed(2)}</strong></div>` : ``);
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
    tip.style.display = 'block';
  }
  function hideTip(){ tip.style.display = 'none'; }

  // ---------- Selection panel ----------
  function setSelected(c){
    if(!c){
      emptySel.style.display = 'block';
      selWrap.style.display = 'none';
      return;
    }
    emptySel.style.display = 'none';
    selWrap.style.display = 'block';
    selIdEl.textContent = String(c.cell_id ?? c.id);
    selTypeEl.textContent = c.type;
    selXYEl.textContent = `(${c.x.toFixed(3)}, ${c.y.toFixed(3)})`;
    selZoneEl.textContent = zoneLabel(c.rNorm ?? 0);

    if(!c.expr || state.genePanel.length === 0){
      barsEl.innerHTML = `<div class="note">No gene expression columns detected in this file.</div>`;
      return;
    }

    const pairs = state.genePanel.map((g,i)=>({g, v:c.expr[i] ?? 0}));
    pairs.sort((a,b)=>b.v-a.v);
    const top = pairs.slice(0,10);
    const maxV = Math.max(1e-6, top[0].v);

    barsEl.innerHTML = '';
    for(const {g,v} of top){
      const row = document.createElement('div');
      row.className = 'barRow';
      row.innerHTML = `
        <div class="barLabel" title="${g}">${g}</div>
        <div class="barTrack"><div class="barFill" style="width:${(v/maxV*100).toFixed(1)}%"></div></div>
        <div class="barVal">${v.toFixed(2)}</div>
      `;
      barsEl.appendChild(row);
    }
  }

  // ---------- Legend counts ----------
  function updateLegendCounts(){
    const totals = Object.fromEntries(state.cellTypes.map(t => [t.key, 0]));
    const visible = Object.fromEntries(state.cellTypes.map(t => [t.key, 0]));

    for(const c of state.cells){
      totals[c.type] = (totals[c.type] ?? 0) + 1;
      if(state.activeTypes.get(c.type)) visible[c.type] = (visible[c.type] ?? 0) + 1;
    }

    if(!updateLegendCounts._built){
      legendEl.innerHTML = '';
      for(const t of state.cellTypes){
        const row = document.createElement('div');
        row.className = 'legendRow';

        const left = document.createElement('div');
        left.className = 'legendLeft';

        const check = document.createElement('label');
        check.className = 'check';

        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = true;
        cb.dataset.type = t.key;
        cb.addEventListener('change', ()=>{
          state.activeTypes.set(t.key, cb.checked);
          state._activeTypesVersion = (state._activeTypesVersion || 0) + 1;
          if(state._geneRangeCache) state._geneRangeCache.clear();

          if(state.selectedId != null && state.cells[state.selectedId-1]?.type === t.key && !cb.checked){
            state.selectedId = null;
            setSelected(null);
          }
          if(state.hoveredId != null && state.cells[state.hoveredId-1]?.type === t.key && !cb.checked){
            state.hoveredId = null;
            hideTip();
          }
          renderer.requestRender();
          scheduleUrlSync();
        });

        const sw = document.createElement('span');
        sw.className = 'swatch';
        sw.style.background = t.color;

        const name = document.createElement('span');
        name.className = 'legendName';
        name.textContent = t.key;

        check.appendChild(cb);
        check.appendChild(sw);
        check.appendChild(name);
        left.appendChild(check);

        const meta = document.createElement('div');
        meta.className = 'legendMeta';
        meta.innerHTML = `<span class="count" data-type="${t.key}"></span>`;

        row.appendChild(left);
        row.appendChild(meta);
        legendEl.appendChild(row);
      }
      updateLegendCounts._built = true;
    }

    const countEls = legendEl.querySelectorAll('.count');
    for(const el of countEls){
      const k = el.getAttribute('data-type');
      el.textContent = `${visible[k] ?? 0} / ${totals[k] ?? 0}`;
    }

    const totalVis = Object.values(visible).reduce((a,b)=>a+b,0);
    const totalAll = state.cells.length;

    const r = renderer && renderer.perf ? renderer.perf.renderMsEma : null;
    const p = renderer && renderer.perf ? renderer.perf.pickMsEma : null;
    const perfTxt = (r != null || p != null)
      ? ` <span style="color:var(--muted)">• render ${fmtMs(r)} • pick ${fmtMs(p)}</span>`
      : '';

    visStatus.innerHTML = `Visible: <strong>${totalVis}</strong> / ${totalAll} cells${perfTxt}`;
  }

  // expose to renderer callback
  renderer._updateLegendCounts = updateLegendCounts;

  // ---------- Gene UI ----------
  function updateGeneDatalist(){
    geneList.innerHTML = '';
    const MAX = 5000;
    const n = Math.min(state.genePanel.length, MAX);
    for(let i=0;i<n;i++){
      const opt = document.createElement('option');
      opt.value = state.genePanel[i];
      geneList.appendChild(opt);
    }
  }

  function setStatus(ok, msg){
    geneHint.innerHTML = ok
      ? `<span style="color:rgba(34,197,94,.95)">Loaded.</span> ${msg}`
      : `<span style="color:rgba(251,113,133,.95)">Error.</span> ${msg}`;
  }

  function setGeneQuery(q){
    state.geneQuery = (q || '').trim().toUpperCase();
    if(state.geneQuery === ''){
      state.geneIdx = null;
      geneHint.innerHTML = 'Tip: load a CSV/TSV, then search a gene to color cells by expression.';
    } else {
      const idx = state.geneIndex.get(state.geneQuery);
      if(idx == null){
        state.geneIdx = null;
        const ex = state.genePanel.slice(0,10).join('</strong>, <strong>');
        geneHint.innerHTML = `No match for <strong>${state.geneQuery}</strong>. Example genes: <strong>${ex}</strong>${state.genePanel.length>10?'…':''}`;
      } else {
        state.geneIdx = idx;
        geneHint.innerHTML = `Coloring by <strong>${state.genePanel[idx]}</strong>. (Outlines still show cell type.)`;
      }
    }
    hideTip();
    renderer.requestRender();
    scheduleUrlSync();
  }

  // ---------- Gate UI ----------
  const GATE_SCHEMA_VERSION = state.gate.version;

  function gateAutoExprFromBuilder(){
    const parts = [];
    for(let i=0;i<state.gate.conditions.length;i++){
      const label = gateLabelForIndex(i);
      const join = String(state.gate.conditions[i].join || 'AND').toUpperCase();
      if(i === 0) parts.push(label);
      else parts.push(join, label);
    }
    return parts.join(' ');
  }

  function gateConditionSummary(cond){
    const g = String(cond.gene || '').trim().toUpperCase() || 'GENE';
    const cutoff = Number(cond.cutoff);
    const c = Number.isFinite(cutoff) ? cutoff : 0;
    const s = (cond.sense === 'neg') ? '−' : '+';
    return `${g}${s} (cutoff ${c})`;
  }

  function renderGateRows(){
    gateRowsEl.innerHTML = '';

    for(let i=0;i<state.gate.conditions.length;i++){
      const cond = state.gate.conditions[i];
      const label = gateLabelForIndex(i);

      const row = document.createElement('div');
      row.className = 'legendRow';
      row.style.alignItems = 'center';

      const joinSel = document.createElement('select');
      joinSel.style.cssText = 'background:var(--color-control-bg);color:var(--text);border:1px solid var(--border);border-radius:10px;padding:7px 8px;font-size:12px;';
      ['AND','OR'].forEach(v=>{
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = v;
        joinSel.appendChild(opt);
      });
      joinSel.value = String(cond.join || 'AND').toUpperCase();
      joinSel.disabled = (i === 0);

      const geneIn = document.createElement('input');
      geneIn.value = String(cond.gene || '');
      geneIn.placeholder = 'Gene (e.g., CD3E)';
      geneIn.setAttribute('list', 'genes');
      geneIn.spellcheck = false;
      geneIn.autocomplete = 'off';
      geneIn.style.cssText = 'flex:1;min-width:120px;background:rgba(0,0,0,0);border:1px solid var(--border);border-radius:10px;padding:7px 8px;color:var(--text);font-size:12px;outline:none;';

      const senseSel = document.createElement('select');
      senseSel.style.cssText = 'background:var(--color-control-bg);color:var(--text);border:1px solid var(--border);border-radius:10px;padding:7px 8px;font-size:12px;';
      [{v:'pos',t:'+'},{v:'neg',t:'-'}].forEach(o=>{
        const opt = document.createElement('option');
        opt.value = o.v;
        opt.textContent = o.t;
        senseSel.appendChild(opt);
      });
      senseSel.value = cond.sense === 'neg' ? 'neg' : 'pos';

      const cutoffIn = document.createElement('input');
      cutoffIn.type = 'number';
      cutoffIn.step = '0.1';
      cutoffIn.value = String(Number.isFinite(Number(cond.cutoff)) ? cond.cutoff : 0.5);
      cutoffIn.title = 'Expression cutoff';
      cutoffIn.style.cssText = 'width:74px;background:rgba(0,0,0,0);border:1px solid var(--border);border-radius:10px;padding:7px 8px;color:var(--text);font-size:12px;outline:none;';

      const lab = document.createElement('div');
      lab.style.cssText = 'min-width:22px;font-weight:650;color:var(--text);font-size:12px;';
      lab.textContent = label;
      lab.title = gateConditionSummary(cond);

      const rm = document.createElement('button');
      rm.textContent = '✕';
      rm.title = 'Remove condition';
      rm.style.padding = '6px 8px';

      const left = document.createElement('div');
      left.className = 'legendLeft';
      left.style.gap = '8px';
      left.appendChild(lab);
      left.appendChild(joinSel);
      left.appendChild(geneIn);
      left.appendChild(senseSel);
      left.appendChild(cutoffIn);

      const meta = document.createElement('div');
      meta.className = 'legendMeta';
      meta.style.gap = '8px';
      meta.appendChild(rm);

      row.appendChild(left);
      row.appendChild(meta);
      gateRowsEl.appendChild(row);

      const onChange = ()=>{
        cond.join = joinSel.value;
        cond.gene = geneIn.value;
        cond.sense = senseSel.value;
        cond.cutoff = Number(cutoffIn.value);
        if(!state.gate.advanced) gateExprEl.value = gateAutoExprFromBuilder();
        evaluateGateAndRender();
      };
      joinSel.addEventListener('change', onChange);
      geneIn.addEventListener('input', ()=>{ clearTimeout(geneIn._t); geneIn._t = setTimeout(onChange, 80); });
      senseSel.addEventListener('change', onChange);
      cutoffIn.addEventListener('input', ()=>{ clearTimeout(cutoffIn._t); cutoffIn._t = setTimeout(onChange, 80); });

      rm.addEventListener('click', ()=>{
        state.gate.conditions.splice(i, 1);
        if(!state.gate.advanced) gateExprEl.value = gateAutoExprFromBuilder();
        renderGateRows();
        evaluateGateAndRender();
      });
    }

    if(state.gate.conditions.length === 0){
      const empty = document.createElement('div');
      empty.className = 'note';
      empty.textContent = 'No conditions yet. Click “Add condition” to start.';
      gateRowsEl.appendChild(empty);
    }
  }

  function evaluateGateAndRender(){
    // keep model in sync
    state.gate.expr = gateExprEl.value;
    state.gate.advanced = !!gateAdvancedEl.checked;
    state.gate.enabled = !!gateEnabledEl.checked;

    const {mask, matchCount, error} = evaluateGate({
      cells: state.cells,
      geneIndex: state.geneIndex,
      gateEnabled: state.gate.enabled,
      gateConditions: state.gate.conditions,
      gateExpr: state.gate.expr,
    });

    state.gateMask = mask;
    state.gateMatchCount = matchCount;
    state.gateLastError = error;

    if(gateStatusEl){
      if(!state.gate.enabled){
        gateStatusEl.textContent = 'Gate off';
      } else if(state.gateMask && !state.gateLastError){
        gateStatusEl.innerHTML = `<strong>${state.gateMatchCount}</strong> / ${state.cells.length} match`;
      } else if(state.gateMask && state.gateLastError){
        gateStatusEl.innerHTML = `<strong>${state.gateMatchCount}</strong> / ${state.cells.length} match • <span style="color:rgba(251,113,133,.95)">${state.gateLastError}</span>`;
      } else {
        gateStatusEl.innerHTML = `<span style="color:rgba(251,113,133,.95)">${state.gateLastError || 'Gate error'}</span>`;
      }
    }

    renderer.requestRender();
  }

  function initGateUi(){
    if(!gateRowsEl) return;

    gateEnabledEl.checked = !!state.gate.enabled;
    gateAdvancedEl.checked = !!state.gate.advanced;

    // Expression field is only editable in Advanced mode.
    gateExprEl.readOnly = !state.gate.advanced;
    gateExprEl.style.opacity = state.gate.advanced ? '1' : '0.92';

    // In non-advanced mode, keep the expression derived from the builder.
    gateExprEl.value = state.gate.advanced
      ? (state.gate.expr || '')
      : (state.gate.conditions.length ? gateAutoExprFromBuilder() : '');

    renderGateRows();
    evaluateGateAndRender();

    gateAddBtn.addEventListener('click', ()=>{
      state.gate.conditions.push({gene:'', sense:'pos', cutoff:0.5, join:'AND'});
      if(!state.gate.advanced) gateExprEl.value = gateAutoExprFromBuilder();
      renderGateRows();
      evaluateGateAndRender();
    });

    gateClearBtn.addEventListener('click', ()=>{
      state.gate.conditions = [];
      if(!state.gate.advanced) gateExprEl.value = '';
      renderGateRows();
      evaluateGateAndRender();
    });

    gateEnabledEl.addEventListener('change', evaluateGateAndRender);

    gateAdvancedEl.addEventListener('change', ()=>{
      state.gate.advanced = gateAdvancedEl.checked;
      gateExprEl.readOnly = !state.gate.advanced;
      gateExprEl.style.opacity = state.gate.advanced ? '1' : '0.92';
      if(!state.gate.advanced){
        gateExprEl.value = gateAutoExprFromBuilder();
      }
      evaluateGateAndRender();
    });

    gateExprEl.addEventListener('input', ()=>{
      clearTimeout(gateExprEl._t);
      gateExprEl._t = setTimeout(evaluateGateAndRender, 80);
    });

    gateCopyBtn.addEventListener('click', async ()=>{
      const payload = {
        version: GATE_SCHEMA_VERSION,
        enabled: !!gateEnabledEl.checked,
        advanced: !!gateAdvancedEl.checked,
        expr: String(gateExprEl.value || ''),
        conditions: state.gate.conditions.map(c => ({gene: String(c.gene||''), sense: c.sense==='neg'?'neg':'pos', cutoff: Number(c.cutoff), join: String(c.join||'AND').toUpperCase()})),
      };
      const json = JSON.stringify(payload, null, 2);
      try{
        await navigator.clipboard.writeText(json);
        if(gateStatusEl) gateStatusEl.textContent = 'Copied gate JSON';
        setTimeout(()=>evaluateGateAndRender(), 700);
      } catch {
        prompt('Copy gate JSON:', json);
      }
    });

    gatePasteBtn.addEventListener('click', ()=>{
      const raw = prompt('Paste gate JSON:');
      if(!raw) return;
      try{
        const obj = JSON.parse(raw);
        if(!obj || obj.version !== GATE_SCHEMA_VERSION) throw new Error('Unsupported gate schema version.');
        state.gate.conditions = Array.isArray(obj.conditions) ? obj.conditions.map(c => ({
          gene: String(c.gene || ''),
          sense: (c.sense === 'neg') ? 'neg' : 'pos',
          cutoff: Number.isFinite(Number(c.cutoff)) ? Number(c.cutoff) : 0.5,
          join: (String(c.join || 'AND').toUpperCase() === 'OR') ? 'OR' : 'AND',
        })) : [];
        state.gate.enabled = !!obj.enabled;
        state.gate.advanced = !!obj.advanced;
        state.gate.expr = String(obj.expr || '');

        gateEnabledEl.checked = state.gate.enabled;
        gateAdvancedEl.checked = state.gate.advanced;
        gateExprEl.readOnly = !state.gate.advanced;
        gateExprEl.value = state.gate.advanced ? state.gate.expr : gateAutoExprFromBuilder();

        renderGateRows();
        evaluateGateAndRender();
      } catch(err){
        alert(String(err && err.message ? err.message : err));
      }
    });

    gateExprEl.readOnly = !gateAdvancedEl.checked;
    if(!gateAdvancedEl.checked){
      gateExprEl.value = gateAutoExprFromBuilder();
    }
  }

  // ---------- Dataset loading / apply ----------
  function applyDataset(ds){
    state.cells = ds.cells;
    state.cellTypes = ds.cellTypes;
    state.genePanel = ds.genePanel;
    state.geneIndex = ds.geneIndex;

    state.activeTypes = new Map(state.cellTypes.map(t => [t.key, true]));
    state.typeColorRgb = new Map(state.cellTypes.map(t => [t.key, hexToRgb(t.color)]));
    updateLegendCounts._built = false;

    // perf: rebuild spatial index + invalidate caches
    // Use quadtree for robust picking across clustered/non-uniform datasets.
    state.spatialIndex = buildQuadtreeIndex(state.cells, {maxItems: 48, maxDepth: 12});
    state._activeTypesVersion = (state._activeTypesVersion || 0) + 1;
    state._geneRangeCache = new Map();

    state.selectedId = null;
    state.hoveredId = null;
    setSelected(null);

    geneInput.value = '';
    state.geneIdx = null;
    state.geneQuery = '';

    updateGeneDatalist();

    state.datasetName = String(ds.filename || 'dataset');
    datasetLabel.textContent = `(loaded: ${ds.filename})`;
    datasetBadgeText.innerHTML = `<strong style="color:var(--text);font-weight:600">${state.cells.length}</strong> cells • ${state.cellTypes.length} types • ${state.genePanel.length} genes`;

    // Once the user loads a dataset, hide the welcome overlay.
    try{ localStorage.setItem('spatialExplorer.welcomeDismissed', '1'); } catch {}
    updateWelcome();

    renderer.resetViewToFit();
    hideTip();

    evaluateGateAndRender();
    scheduleUrlSync();

    const skipped = ds.badRows ? ` Skipped ${ds.badRows} malformed rows.` : '';
    setStatus(true, `Parsed <strong>${state.cells.length}</strong> cells and <strong>${state.genePanel.length}</strong> genes.${skipped}`);
  }

  async function loadFile(file){
    if(!file) return;
    const name = file.name || 'data';
    setStatus(true, `Loading <strong>${name}</strong>…`);
    const text = await file.text();
    const ds = buildLoadedDataset(text, name);
    applyDataset(ds);
  }

  // ---------- µm/px calibration ----------
  function setUmPerPixel(v, {syncUrl=true} = {}){
    const next = clamp(Number(v) || 0, 0, 1e6);
    state.umPerPixel = next;
    umPerPxEl.value = String(next);
    try{ localStorage.setItem('spatialExplorer.umPerPixel', String(next)); } catch {}
    renderer.requestRender();
    if(syncUrl) scheduleUrlSync();
  }

  // ---------- Exports ----------
  function downloadBlob(blob, filename){
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(()=>URL.revokeObjectURL(url), 2000);
  }

  function paintExportBackground(ctx, w, h){
    // Match the on-screen canvas CSS background (approx):
    // background: radial-gradient(900px 600px at 50% 45%, rgba(255,255,255,.04), rgba(0,0,0,0) 55%)
    // with a solid dark base.
    ctx.save();
    const root = getComputedStyle(document.documentElement);
    const base = (root.getPropertyValue('--canvas-base') || '#0a0a0a').trim();
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, w, h);

    const cx = w * 0.5;
    const cy = h * 0.45;

    // Scale the gradient size with the viewport, but keep a similar feel.
    const r = Math.max(1, Math.min(Math.max(w, h) * 0.95, 950));
    const root = getComputedStyle(document.documentElement);
    const glow0 = (root.getPropertyValue('--canvas-glow-0') || 'rgba(255,255,255,0.04)').trim();
    const glow1 = (root.getPropertyValue('--canvas-glow-1') || 'rgba(0,0,0,0)').trim();

    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    g.addColorStop(0.0, glow0);
    g.addColorStop(0.55, glow1);
    g.addColorStop(1.0, glow1);

    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
    ctx.restore();
  }

  function dataUrlToBlob(dataUrl){
    // Fallback for browsers/environments where canvas.toBlob is missing or returns null.
    // dataUrl: "data:image/png;base64,..."
    const m = /^data:([^;]+);base64,(.*)$/.exec(String(dataUrl || ''));
    if(!m) throw new Error('PNG export failed (invalid data URL).');
    const mime = m[1] || 'application/octet-stream';
    const b64 = m[2] || '';
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for(let i=0;i<bin.length;i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], {type: mime});
  }

  async function canvasToPngBlob(cnv){
    if(typeof cnv.toBlob === 'function'){
      const blob = await new Promise((resolve)=> cnv.toBlob(resolve, 'image/png'));
      if(blob) return blob;
      // Continue to fallback below.
    }
    const url = cnv.toDataURL('image/png');
    return dataUrlToBlob(url);
  }

  async function exportPng(){
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(1, rect.width);
    const h = Math.max(1, rect.height);

    const mult = clamp(Number(exportScaleSel && exportScaleSel.value ? exportScaleSel.value : 2) || 2, 1, 6);
    const dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
    const exportDpr = Math.min(8, dpr * mult);

    const out = document.createElement('canvas');
    out.width = Math.floor(w * exportDpr);
    out.height = Math.floor(h * exportDpr);

    // Export should be opaque and match the visual background.
    const ctx = out.getContext('2d', {alpha: false});
    ctx.setTransform(exportDpr, 0, 0, exportDpr, 0, 0);
    paintExportBackground(ctx, w, h);
    renderer.renderTo(ctx, w, h);

    const genePart = (state.geneIdx != null && state.genePanel[state.geneIdx]) ? sanitizeForFilename(state.genePanel[state.geneIdx]) : 'celltype';
    const dsPart = sanitizeForFilename(state.datasetName) || 'dataset';
    const name = `${dsPart}__${genePart}__${timestampForFilename()}.png`;

    const blob = await canvasToPngBlob(out);
    downloadBlob(blob, name);
  }

  function svgEscape(s){
    return String(s)
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }

  function svgFromCurrentView(w, h){
    const rPx = renderer.cellRadiusPx();
    const vis = renderer.visibleCells();

    let range = null;
    if(state.geneIdx != null) range = renderer.computeGeneRange(state.geneIdx);

    const parts = [];
    parts.push(`<?xml version="1.0" encoding="UTF-8"?>`);
    parts.push(`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" shape-rendering="geometricPrecision">`);

    // Tissue boundary
    {
      const steps = 200;
      let d = '';
      for(let i=0;i<=steps;i++){
        const a = i/steps * Math.PI*2;
        const r = 1.05;
        const p = renderer.worldToScreen(r*Math.cos(a), r*Math.sin(a));
        d += (i===0 ? 'M' : 'L') + p.x.toFixed(3) + ' ' + p.y.toFixed(3) + ' ';
      }
      d += 'Z';
      parts.push(`<path d="${d.trim()}" fill="rgba(255,255,255,.015)" stroke="rgba(255,255,255,.07)" stroke-width="1"/>`);
    }

    // Points
    parts.push(`<g opacity="0.85">`);
    for(const c of vis){
      const isSel = (c.id === state.selectedId);
      const isHover = (c.id === state.hoveredId);
      if(isSel || isHover) continue;

      const p = renderer.worldToScreen(c.x, c.y);
      let fill;
      if(state.geneIdx != null && c.expr){
        fill = renderer.geneColor(c.expr[state.geneIdx] ?? 0, range.min, range.max);
      } else {
        const rgb = state.typeColorRgb.get(c.type) || {r:200,g:200,b:200};
        fill = rgba(rgb, 0.92);
      }
      parts.push(`<circle cx="${p.x.toFixed(3)}" cy="${p.y.toFixed(3)}" r="${rPx.toFixed(3)}" fill="${fill}"/>`);
    }
    parts.push(`</g>`);

    if(state.geneIdx != null){
      parts.push(`<g opacity="0.65">`);
      for(const c of vis){
        const isSel = (c.id === state.selectedId);
        const isHover = (c.id === state.hoveredId);
        if(isSel || isHover) continue;
        const p = renderer.worldToScreen(c.x, c.y);
        const rgb = state.typeColorRgb.get(c.type) || {r:200,g:200,b:200};
        const stroke = rgba(rgb, 0.55);
        parts.push(`<circle cx="${p.x.toFixed(3)}" cy="${p.y.toFixed(3)}" r="${(rPx+0.8).toFixed(3)}" fill="none" stroke="${stroke}" stroke-width="1"/>`);
      }
      parts.push(`</g>`);
    }

    for(const id of [state.hoveredId, state.selectedId]){
      if(id == null) continue;
      const c = state.cells[id-1];
      if(!c || !state.activeTypes.get(c.type)) continue;

      const p = renderer.worldToScreen(c.x, c.y);
      const rgb = state.typeColorRgb.get(c.type) || {r:200,g:200,b:200};
      const fill = (state.geneIdx != null && c.expr)
        ? renderer.geneColor(c.expr[state.geneIdx] ?? 0, range.min, range.max)
        : rgba(rgb, 0.96);

      parts.push(`<circle cx="${p.x.toFixed(3)}" cy="${p.y.toFixed(3)}" r="${(rPx+1.4).toFixed(3)}" fill="${fill}" stroke="rgba(255,255,255,.85)" stroke-width="2"/>`);
    }

    {
      const fontFamily = (getComputedStyle(document.body).fontFamily || 'system-ui').split(',').map(s=>s.trim()).join(',');
      const gtxt = (state.geneIdx == null) ? 'Cell type' : `Gene: ${state.genePanel[state.geneIdx]} (expression)`;
      parts.push(`<text x="14" y="${(h-14).toFixed(3)}" font-size="12" font-family="${svgEscape(fontFamily)}" fill="rgba(255,255,255,.66)">${svgEscape(gtxt)}</text>`);
    }

    // Scale bar (bottom-right)
    {
      const bar = computeScaleBar({umPerPixel: state.umPerPixel, viewScale: renderer.view.scale, targetPx: 110});
      if(bar){
        const pad = 14;
        const barH = 6;
        const label = bar.label;
        const barPx = bar.barPx;

        // SVG has no easy text metrics; use a conservative heuristic.
        const estTextW = Math.max(0, label.length) * 7;
        const boxW = Math.max(barPx, estTextW) + 16;
        const boxH = 32;
        const bx = w - pad - boxW;
        const by = h - pad - boxH;

        const barX = w - pad - barPx;
        const barY = h - pad - 12;

        parts.push(`<g aria-label="scale bar">`);
        parts.push(`<rect x="${bx.toFixed(3)}" y="${by.toFixed(3)}" width="${boxW.toFixed(3)}" height="${boxH.toFixed(3)}" rx="10" ry="10" fill="rgba(16,18,20,.72)" stroke="rgba(255,255,255,.12)" stroke-width="1"/>`);
        parts.push(`<rect x="${barX.toFixed(3)}" y="${barY.toFixed(3)}" width="${barPx.toFixed(3)}" height="${barH.toFixed(3)}" fill="rgba(255,255,255,.85)"/>`);
        parts.push(`<rect x="${barX.toFixed(3)}" y="${barY.toFixed(3)}" width="${barPx.toFixed(3)}" height="1" fill="rgba(0,0,0,.35)"/>`);

        const fontFamily = (getComputedStyle(document.body).fontFamily || 'system-ui').split(',').map(s=>s.trim()).join(',');
        const textX = w - pad; // right aligned
        const textY = barY - 4;
        parts.push(`<text x="${textX.toFixed(3)}" y="${textY.toFixed(3)}" font-size="12" font-family="${svgEscape(fontFamily)}" fill="rgba(255,255,255,.82)" text-anchor="end">${svgEscape(label)}</text>`);
        parts.push(`</g>`);
      }
    }

    parts.push(`</svg>`);
    return parts.join('\n');
  }

  async function exportSvg(){
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(1, rect.width);
    const h = Math.max(1, rect.height);

    const svg = svgFromCurrentView(w, h);

    const genePart = (state.geneIdx != null && state.genePanel[state.geneIdx]) ? sanitizeForFilename(state.genePanel[state.geneIdx]) : 'celltype';
    const dsPart = sanitizeForFilename(state.datasetName) || 'dataset';
    const name = `${dsPart}__${genePart}__${timestampForFilename()}.svg`;

    const blob = new Blob([svg], {type: 'image/svg+xml;charset=utf-8'});
    downloadBlob(blob, name);
  }

  // ---------- Drag-drop overlay ----------
  function showDrop(on){
    dropEl.style.display = on ? 'grid' : 'none';
  }

  // ---------- Interaction wiring ----------
  function bind(){
    initTheme();

    // persisted calibration
    try{
      const saved = localStorage.getItem('spatialExplorer.umPerPixel');
      if(saved != null) state.umPerPixel = clamp(Number(saved) || 0, 0, 1e6);
    } catch {}
    umPerPxEl.value = String(state.umPerPixel);
    umPerPxEl.addEventListener('input', ()=> setUmPerPixel(umPerPxEl.value));

    let geneTimer = null;
    geneInput.addEventListener('input', ()=>{
      clearTimeout(geneTimer);
      geneTimer = setTimeout(()=>setGeneQuery(geneInput.value), 60);
    });

    if(welcomeUploadBtn){
      welcomeUploadBtn.addEventListener('click', ()=> fileInput.click());
    }
    if(welcomeDismissBtn){
      welcomeDismissBtn.addEventListener('click', ()=>{
        try{ localStorage.setItem('spatialExplorer.welcomeDismissed', '1'); } catch {}
        updateWelcome();
      });
    }

    loadBtn.addEventListener('click', ()=> fileInput.click());
    fileInput.addEventListener('change', async ()=>{
      const f = fileInput.files && fileInput.files[0];
      try{ await loadFile(f); }
      catch(err){
        console.error(err);
        setStatus(false, String(err && err.message ? err.message : err));
      } finally {
        fileInput.value = '';
      }
    });

    ['dragenter','dragover'].forEach(evt => {
      window.addEventListener(evt, (e)=>{
        e.preventDefault();
        showDrop(true);
      });
    });
    ['dragleave','drop'].forEach(evt => {
      window.addEventListener(evt, (e)=>{
        e.preventDefault();
        if(evt==='dragleave' && e.relatedTarget) return;
        showDrop(false);
      });
    });

    window.addEventListener('drop', async (e)=>{
      const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if(!file) return;
      try{ await loadFile(file); }
      catch(err){
        console.error(err);
        setStatus(false, String(err && err.message ? err.message : err));
      }
    });

    // Pan/zoom/select
    let dragging = false;
    let last = null;
    let downAt = null;

    canvas.addEventListener('pointerdown', (e)=>{
      canvas.setPointerCapture(e.pointerId);
      dragging = true;
      last = {x:e.clientX, y:e.clientY};
      downAt = {x:e.clientX, y:e.clientY, t: performance.now()};
    });

    canvas.addEventListener('pointermove', (e)=>{
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      if(dragging && last){
        const dx = e.clientX - last.x;
        const dy = e.clientY - last.y;
        renderer.view.tx += dx;
        renderer.view.ty += dy;
        last = {x:e.clientX, y:e.clientY};
        hideTip();
        if(state.hoveredId != null) state.hoveredId = null;
        renderer.requestRender();
        scheduleUrlSync();
        return;
      }

      const prev = state.hoveredId;
      const hit = renderer.findNearestCell(e.clientX, e.clientY);
      if(hit){
        if(prev !== hit.id){
          state.hoveredId = hit.id;
          renderer.requestRender();
        }
        showTip(hit, x, y);
      } else {
        if(prev != null){
          state.hoveredId = null;
          renderer.requestRender();
        }
        hideTip();
      }
    });

    canvas.addEventListener('pointerup', (e)=>{
      const wasDragging = dragging;
      dragging = false;
      last = null;

      if(wasDragging && downAt){
        const dx = e.clientX - downAt.x;
        const dy = e.clientY - downAt.y;
        const moved = Math.hypot(dx,dy);
        const dt = performance.now() - downAt.t;
        const isClick = moved < 6 && dt < 600;
        if(isClick){
          const hit = renderer.findNearestCell(e.clientX, e.clientY);
          if(hit){
            state.selectedId = hit.id;
            setSelected(hit);
            renderer.requestRender();
            scheduleUrlSync();
          }
        }
      }
      downAt = null;
    });

    canvas.addEventListener('pointerleave', ()=>{
      if(state.hoveredId != null){
        state.hoveredId = null;
        hideTip();
        renderer.requestRender();
      } else {
        hideTip();
      }
    });

    canvas.addEventListener('wheel', (e)=>{
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      const before = renderer.screenToWorld(mx,my);
      const zoom = Math.exp(-e.deltaY * 0.0012);
      const nextScale = clamp(renderer.view.scale * zoom, 90, 1200);
      renderer.view.scale = nextScale;

      renderer.view.tx = mx - before.x * renderer.view.scale;
      renderer.view.ty = my - before.y * renderer.view.scale;

      hideTip();
      renderer.requestRender();
      scheduleUrlSync();
    }, {passive:false});

    resetBtn.addEventListener('click', ()=>{
      renderer.resetViewToFit();
      hideTip();
      renderer.requestRender();
      scheduleUrlSync();
    });
    zinBtn.addEventListener('click', ()=>{
      const rect = canvas.getBoundingClientRect();
      const mx = rect.width/2, my = rect.height/2;
      const before = renderer.screenToWorld(mx,my);
      renderer.view.scale = clamp(renderer.view.scale*1.18, 90, 1200);
      renderer.view.tx = mx - before.x * renderer.view.scale;
      renderer.view.ty = my - before.y * renderer.view.scale;
      renderer.requestRender();
      scheduleUrlSync();
    });
    zoutBtn.addEventListener('click', ()=>{
      const rect = canvas.getBoundingClientRect();
      const mx = rect.width/2, my = rect.height/2;
      const before = renderer.screenToWorld(mx,my);
      renderer.view.scale = clamp(renderer.view.scale/1.18, 90, 1200);
      renderer.view.tx = mx - before.x * renderer.view.scale;
      renderer.view.ty = my - before.y * renderer.view.scale;
      renderer.requestRender();
      scheduleUrlSync();
    });

    // Export
    exportBtn.addEventListener('click', ()=>{
      exportPng().catch(err=>{
        console.error(err);
        setStatus(false, String(err && err.message ? err.message : err));
      });
    });

    exportSvgBtn.addEventListener('click', ()=>{
      exportSvg().catch(err=>{
        console.error(err);
        setStatus(false, String(err && err.message ? err.message : err));
      });
    });

    window.addEventListener('keydown', (e)=>{
      if(e.key === 'Escape'){
        state.selectedId = null;
        setSelected(null);
        geneInput.value = '';
        setGeneQuery('');
        renderer.requestRender();
        scheduleUrlSync();
      }
    });

    // Resize
    window.addEventListener('resize', ()=> renderer.resizeCanvas({initial:false}));

    // Gate
    initGateUi();

    // initial render bits
    updateGeneDatalist();
    setSelected(null);
    updateLegendCounts();
    updateWelcome();

    // Restore URL state after first layout.
    _restoringFromUrl = true;
    setGeneQuery('');
    _restoringFromUrl = false;
    applyStateFromUrl();

    renderer.requestRender();
    scheduleUrlSync();
  }

  return {
    bind,
    setGeneQuery,
    setSelected,
    updateGeneDatalist,
    updateLegendCounts,
    scheduleUrlSync,
    applyStateFromUrl,
    setUmPerPixel,
    evaluateGateAndRender,
    applyDataset,
    loadFile,
  };
}

export function collectDom(){
  const $ = (id)=> document.getElementById(id);
  return {
    canvas: $('c'),
    glCanvas: $('gl'),
    tip: $('tip'),
    dropEl: $('drop'),
    welcomeEl: $('welcome'),
    welcomeUploadBtn: $('welcomeUpload'),
    welcomeDismissBtn: $('welcomeDismiss'),
    legendEl: $('legend'),
    visStatus: $('visStatus'),
    datasetLabel: $('datasetLabel'),
    datasetBadgeText: $('datasetBadgeText'),

    geneInput: $('gene'),
    geneList: $('genes'),
    geneHint: $('geneHint'),

    loadBtn: $('load'),
    fileInput: $('file'),

    exportBtn: $('exportPng'),
    exportSvgBtn: $('exportSvg'),
    exportScaleSel: $('exportScale'),
    umPerPxEl: $('umPerPx'),

    emptySel: $('emptySel'),
    selWrap: $('sel'),
    selIdEl: $('selId'),
    selTypeEl: $('selType'),
    selXYEl: $('selXY'),
    selZoneEl: $('selZone'),
    barsEl: $('bars'),

    gateRowsEl: $('gateRows'),
    gateAddBtn: $('gateAdd'),
    gateClearBtn: $('gateClear'),
    gateEnabledEl: $('gateEnabled'),
    gateExprEl: $('gateExpr'),
    gateAdvancedEl: $('gateAdvanced'),
    gateStatusEl: $('gateStatus'),
    gateCopyBtn: $('gateCopy'),
    gatePasteBtn: $('gatePaste'),

    resetBtn: $('reset'),
    zinBtn: $('zin'),
    zoutBtn: $('zout'),
    themeToggleBtn: $('themeToggle'),
  };
}
