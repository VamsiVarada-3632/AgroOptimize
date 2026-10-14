/**
 * Shared chart colours and helpers.
 *
 * Charts use emphasis rather than many categorical hues: the selected series
 * is drawn in the accent green and the others recede in gray. The pair was
 * checked with the data-viz palette validator against the white card surface
 * (#ffffff): colour-vision-deficiency separation ΔE 18.8, normal-vision ΔE
 * 22.1. The gray is 2.95:1 against the surface, just under 3:1, so every
 * chart card also offers a table view.
 */
export const CHART = {
  accent: '#1f6b3a',      // primary-container token
  accentSoft: '#a7f4b6',  // primary-fixed token (fills behind the accent)
  context: '#8f998e',     // de-emphasised series
  reference: '#795900',   // reference lines (normals, thresholds) – secondary token
  grid: '#e4e2e2',        // surface-container-highest token
  axis: '#707a6f',        // outline token
  text: '#404940',        // on-surface-variant token
  surface: '#ffffff',
};

/** "Nice" axis ticks for a [min, max] range. */
export function niceTicks(min, max, count = 5) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  if (min === max) {
    const pad = Math.abs(min) * 0.1 || 1;
    min -= pad;
    max += pad;
  }
  const span = max - min;
  const step0 = span / Math.max(1, count);
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) || step0;
  const start = Math.floor(min / step) * step;
  const ticks = [];
  for (let v = start; v <= max + step * 0.5; v += step) ticks.push(Number(v.toFixed(10)));
  return ticks;
}

export function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return '–';
  return Number(value).toLocaleString('en-IN', { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}
