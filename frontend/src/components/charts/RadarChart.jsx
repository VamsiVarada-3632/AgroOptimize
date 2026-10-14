import React from 'react';
import { CHART, formatNumber } from './chartTheme';

/**
 * Radar of 0–1 scores on shared axes for two series (e.g. original and
 * simulated plan on a common objective scale). The first series is drawn in
 * gray, the second in the accent colour; both are named in the legend and
 * every vertex has a tooltip with its value.
 *
 * axes: [{ key, label }]; series: [{ label, values: { [key]: number } }]
 */
export default function RadarChart({ axes, series, ariaLabel, size = 300 }) {
  const width = size + 140;                  // horizontal room for axis labels
  const c = size / 2;
  const cx = width / 2;
  const r = c - 40;
  const angle = (i) => (Math.PI * 2 * i) / axes.length - Math.PI / 2;
  const point = (i, v) => [cx + Math.cos(angle(i)) * r * v, c + Math.sin(angle(i)) * r * v];
  const colors = [CHART.context, CHART.accent];

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${size}`} className="w-full h-auto max-w-[440px] mx-auto" role="img" aria-label={ariaLabel}>
        {[0.25, 0.5, 0.75, 1].map((ring) => (
          <polygon key={ring} points={axes.map((_, i) => point(i, ring).join(',')).join(' ')} fill="none" stroke={CHART.grid} />
        ))}
        {axes.map((a, i) => {
          const [x, y] = point(i, 1);
          const [lx, ly] = point(i, 1.12);
          return (
            <g key={a.key}>
              <line x1={cx} y1={c} x2={x} y2={y} stroke={CHART.grid} />
              <text x={lx} y={ly + 3} fontSize="13" fill={CHART.text} textAnchor={Math.abs(lx - cx) < 4 ? 'middle' : lx > cx ? 'start' : 'end'}>{a.label}</text>
            </g>
          );
        })}
        {series.map((s, si) => (
          <g key={s.label}>
            <polygon points={axes.map((a, i) => point(i, s.values[a.key] ?? 0).join(',')).join(' ')}
              fill={colors[si]} fillOpacity={si === 1 ? 0.18 : 0.08} stroke={colors[si]} strokeWidth={si === 1 ? 2 : 1.5} />
            {axes.map((a, i) => {
              const [x, y] = point(i, s.values[a.key] ?? 0);
              return (
                <circle key={a.key} cx={x} cy={y} r="4" fill={colors[si]} stroke={CHART.surface} strokeWidth="2">
                  <title>{`${s.label} · ${a.label}: ${formatNumber(s.values[a.key], 2)}`}</title>
                </circle>
              );
            })}
          </g>
        ))}
      </svg>
      <div className="flex justify-center flex-wrap gap-4 mt-1 text-xs text-on-surface-variant">
        {series.map((s, i) => (
          <span key={s.label} className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ background: colors[i] }}></span>{s.label}
          </span>
        ))}
      </div>
    </div>
  );
}
