// perf.js — tiny helpers (ES module)

export function now(){ return performance && performance.now ? performance.now() : Date.now(); }

export function ema(prev, next, a=0.15){
  if(prev == null) return next;
  return prev + a*(next - prev);
}

export function fmtMs(x){
  if(x == null || !Number.isFinite(x)) return '';
  if(x < 1) return x.toFixed(2) + 'ms';
  if(x < 10) return x.toFixed(1) + 'ms';
  return Math.round(x) + 'ms';
}
