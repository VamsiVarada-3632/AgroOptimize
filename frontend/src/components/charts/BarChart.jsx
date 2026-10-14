import React, { useMemo, useState } from 'react';
import { CHART, niceTicks, formatNumber } from './chartTheme';

/**
 * Single-hue bar chart (magnitude comparison) with optional per-bar
 * reference marks (e.g. the rainfall normal for each year), a highlighted
 * bar, hover tooltips and value labels on the highlighted bar only.
 *
 * data: [{ key, label, value, reference?, highlight?, detail? }]
 * orientation: 'vertical' (default) | 'horizontal' (better for long labels)
 */
export default function BarChart({
  data, unit = '', digits = 0, orientation = 'vertical', referenceLabel, height, ariaLabel,
}) {
  const [hover, setHover] = useState(null);
  const horizontal = orientation === 'horizontal';
  const width = 560;
  const h = height || (horizontal ? Math.max(120, data.length * 30 + 40) : 220);
  const pad = horizontal ? { top: 8, right: 64, bottom: 24, left: 128 } : { top: 16, right: 16, bottom: 34, left: 52 };
  const innerW = width - pad.left - pad.right;
  const innerH = h - pad.top - pad.bottom;

  const ticks = useMemo(() => {
    const vals = data.flatMap((d) => [d.value, d.reference]).filter((v) => v !== null && v !== undefined && Number.isFinite(v));
    return niceTicks(Math.min(0, ...vals), Math.max(...vals, 0));
  }, [data]);
  const lo = ticks[0];
  const hi = ticks[ticks.length - 1];
  const scale = (v) => ((v - lo) / (hi - lo || 1)) * (horizontal ? innerW : innerH);
  const band = (horizontal ? innerH : innerW) / Math.max(1, data.length);
  const thickness = Math.max(6, Math.min(36, band - 8));   // leaves a visible gap between bars

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${width} ${h}`} className="w-full h-auto" role="img" aria-label={ariaLabel}>
        {ticks.map((t) => (horizontal ? (
          <g key={t}>
            <line x1={pad.left + scale(t)} x2={pad.left + scale(t)} y1={pad.top} y2={pad.top + innerH} stroke={CHART.grid} />
            <text x={pad.left + scale(t)} y={h - 8} fontSize="10" fill={CHART.text} textAnchor="middle">{formatNumber(t, digits)}</text>
          </g>
        ) : (
          <g key={t}>
            <line x1={pad.left} x2={pad.left + innerW} y1={pad.top + innerH - scale(t)} y2={pad.top + innerH - scale(t)} stroke={CHART.grid} />
            <text x={pad.left - 8} y={pad.top + innerH - scale(t) + 3} fontSize="10" fill={CHART.text} textAnchor="end">{formatNumber(t, digits)}</text>
          </g>
        )))}
        {data.map((d, i) => {
          const center = (horizontal ? pad.top : pad.left) + band * i + band / 2;
          const len = Math.max(0, scale(d.value ?? 0) - scale(0));
          const fill = d.highlight || hover === i ? CHART.accent : d.highlight === false ? CHART.context : CHART.accent;
          const opacity = hover === null || hover === i ? 1 : 0.55;
          const bar = horizontal
            ? <rect x={pad.left + scale(0)} y={center - thickness / 2} width={len} height={thickness} rx="4" fill={fill} opacity={opacity} />
            : <rect x={center - thickness / 2} y={pad.top + innerH - scale(0) - len} width={thickness} height={len} rx="4" fill={fill} opacity={opacity} />;
          const ref = d.reference === null || d.reference === undefined ? null : horizontal
            ? <line x1={pad.left + scale(d.reference)} x2={pad.left + scale(d.reference)} y1={center - thickness / 2 - 3} y2={center + thickness / 2 + 3} stroke={CHART.reference} strokeWidth="2" />
            : <line x1={center - thickness / 2 - 3} x2={center + thickness / 2 + 3} y1={pad.top + innerH - scale(d.reference)} y2={pad.top + innerH - scale(d.reference)} stroke={CHART.reference} strokeWidth="2" />;
          return (
            <g key={d.key} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              {/* invisible hit target larger than the bar */}
              {horizontal
                ? <rect x={pad.left} y={center - band / 2} width={innerW} height={band} fill="transparent" />
                : <rect x={center - band / 2} y={pad.top} width={band} height={innerH} fill="transparent" />}
              {bar}
              {ref}
              {horizontal
                ? <text x={pad.left - 8} y={center + 3} fontSize="10" fill={CHART.text} textAnchor="end">{d.label}</text>
                : <text x={center} y={h - 18} fontSize="10" fill={CHART.text} textAnchor="middle">{d.label}</text>}
              {(d.highlight || hover === i) && (horizontal
                ? <text x={pad.left + scale(0) + len + 6} y={center + 3} fontSize="10" fontWeight="600" fill={CHART.text}>{formatNumber(d.value, digits)}{unit}</text>
                : <text x={center} y={pad.top + innerH - scale(0) - len - 5} fontSize="10" fontWeight="600" fill={CHART.text} textAnchor="middle">{formatNumber(d.value, digits)}{unit}</text>)}
              <title>{`${d.label}: ${formatNumber(d.value, digits)}${unit}${d.reference !== undefined && d.reference !== null ? ` (${referenceLabel || 'reference'} ${formatNumber(d.reference, digits)}${unit})` : ''}${d.detail ? ` – ${d.detail}` : ''}`}</title>
            </g>
          );
        })}
      </svg>
      {referenceLabel && data.some((d) => d.reference !== undefined && d.reference !== null) && (
        <div className="flex gap-4 text-xs text-on-surface-variant mt-1">
          <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded-sm" style={{ background: CHART.accent }}></span>Observed</span>
          <span className="flex items-center gap-1.5"><span className="inline-block w-4 border-t-2" style={{ borderColor: CHART.reference }}></span>{referenceLabel}</span>
        </div>
      )}
    </div>
  );
}
