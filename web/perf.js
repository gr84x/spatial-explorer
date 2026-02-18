// perf.js — tiny helpers (ES module)

/**
 * High-resolution timestamp (ms).
 * Falls back to Date.now() in non-browser environments.
 */
export function now(){
  return (typeof performance !== 'undefined' && performance && performance.now)
    ? performance.now()
    : Date.now();
}

/**
 * Exponential moving average.
 *
 * @param {number | null} prev - Previous EMA value.
 * @param {number} next - New observation.
 * @param {number} [a=0.15] - Smoothing factor in (0, 1].
 */
export function ema(prev, next, a=0.15){
  if(prev == null) return next;
  return prev + a*(next - prev);
}

/**
 * Format a duration in milliseconds with a sensible precision.
 *
 * @param {number} x
 * @returns {string}
 */
export function fmtMs(x){
  if(x == null || !Number.isFinite(x)) return '';
  if(x < 1) return x.toFixed(2) + 'ms';
  if(x < 10) return x.toFixed(1) + 'ms';
  return Math.round(x) + 'ms';
}
