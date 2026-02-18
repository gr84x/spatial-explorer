// scale_bar.js — Scale bar math + formatting (ES module)

/**
 * Convert an arbitrary target length into a "nice" rounded step.
 * Uses a 1-2-5-10 sequence scaled by powers of 10.
 */
export function niceStep(x){
  const v = Math.abs(Number(x));
  if(!Number.isFinite(v) || v <= 0) return 0;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const m = v / p;
  let n = 1;
  if(m <= 1) n = 1;
  else if(m <= 2) n = 2;
  else if(m <= 5) n = 5;
  else n = 10;
  return n * p;
}

/**
 * Format a microns value using µm or mm depending on scale.
 *
 * @param {number} um
 * @returns {string}
 */
export function formatLengthUm(um){
  const v = Number(um);
  if(!Number.isFinite(v)) return '';
  if(v >= 1000) return `${(v/1000).toFixed(v >= 10000 ? 0 : 1)} mm`;
  if(v >= 10) return `${Math.round(v)} µm`;
  return `${v.toFixed(1)} µm`;
}

/**
 * Compute a scale bar given calibration and current zoom.
 *
 * @param {object} args
 * @param {number} args.umPerPixel - microns per source pixel (world unit)
 * @param {number} args.viewScale - screen px per world px
 * @param {number} [args.targetPx=110] - desired scale bar length in screen px
 * @returns {null | {barUm:number, barPx:number, label:string}}
 */
export function computeScaleBar({umPerPixel, viewScale, targetPx=110}){
  const upp = Number(umPerPixel);
  const vs = Number(viewScale);
  if(!(upp > 0) || !(vs > 0)) return null;

  const umPerScreenPx = upp / vs;
  if(!(umPerScreenPx > 0)) return null;

  const targetUm = Number(targetPx) * umPerScreenPx;
  const barUm = niceStep(targetUm);
  if(!(barUm > 0)) return null;

  const barPx = barUm / umPerScreenPx;
  if(!(barPx > 0) || !Number.isFinite(barPx)) return null;

  return { barUm, barPx, label: formatLengthUm(barUm) };
}
