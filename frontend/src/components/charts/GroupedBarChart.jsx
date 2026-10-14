import React, { useMemo, useState } from 'react';
import { CHART, niceTicks, formatNumber } from './chartTheme';

/**
 * Horizontal grouped bars comparing two series per category (e.g. original
 * vs simulated), with optional min–max whiskers per bar.
 *
 * categories: [{ key, label, values: [a, b], ranges?: [[lo, hi] | null, [lo, hi] | null] }]
 * series: [{ label }, { label }] – the second series is emphasised (accent),
 *   the first recedes in gray; both are always named in the legend.
 */
export default function GroupedBarChart({ categories, series, unit = '', digits = 0, ariaLabel, min }) {
  const [hover, setHover] = useState(null);
  const width = 560;
  const bar = 12;
  const gap = 2;                                   // surface gap between the two bars
  const group = bar * 2 + gap + 14;
  const pad = { top: 8, right: 72, bottom: 24, left: 176 };
  const h = pad.top + pad.bottom + Math.max(1, categories.length) * group;
  const innerW = width - pad.left - pad.right;

  const ticks = useMemo(() => {
    const vals = categories.flatMap((c) => [...c.values, ...(c.ranges || []).flat()])
      .filter((v) => v !== null && v !== undefined && Number.isFinite(v));
    return niceTicks(min ?? Math.min(0, ...vals), Math.max(0, ...vals));
  }, [categories, min]);
  const lo = ticks[0];
  const hi = ticks[ticks.length - 1];
  const x = (v) => pad.left + ((v - lo) / (hi - lo || 1)) * innerW;
  const colors = [CHART.context, CHART.accent];

  return (
    <div className="relative">
      <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${h}`} className="w-full h-auto min-w-[480px]" role="img" aria-label={ariaLabel}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={pad.top} y2={h - pad.bottom} stroke={CHART.grid} />
              <text x={x(t)} y={h - 8} fontSize="10" fill={CHART.text} textAnchor="middle">{formatNumber(t, digits)}</text>
            </g>
          ))}
          <line x1={x(Math.max(lo, 0))} x2={x(Math.max(lo, 0))} y1={pad.top} y2={h - pad.bottom} stroke={CHART.axis} />
          {categories.map((c, ci) => {
            const y0 = pad.top + ci * group + 6;
            return (
              <g key={c.key}>
                <text x={pad.left - 8} y={y0 + bar + 2} fontSize="11" fill={CHART.text} textAnchor="end">{c.label}</text>
                {c.values.map((v, si) => {
                  if (v === null || v === undefined || !Number.isFinite(v)) return null;
                  const y = y0 + si * (bar + gap);
                  const base = x(Math.max(lo, 0));
                  const end = x(v);
                  const range = c.ranges?.[si];
                  const active = hover && hover.ci === ci && hover.si === si;
                  return (
                    <g key={si} onMouseEnter={() => setHover({ ci, si })} onMouseLeave={() => setHover(null)}>
                      <rect x={Math.min(base, end)} y={y} width={Math.max(1, Math.abs(end - base))} height={bar} rx="4"
                        fill={colors[si]} opacity={hover && !active ? 0.55 : 1}>
                        <title>{`${c.label} · ${series[si].label}: ${formatNumber(v, digits)}${unit}`
                          + (range ? ` (runs ${formatNumber(range[0], digits)}–${formatNumber(range[1], digits)}${unit})` : '')}</title>
                      </rect>
                      {range && (
                        <g stroke={CHART.text} strokeWidth="1.2">
                          <line x1={x(range[0])} x2={x(range[1])} y1={y + bar / 2} y2={y + bar / 2} />
                          <line x1={x(range[0])} x2={x(range[0])} y1={y + 2} y2={y + bar - 2} />
                          <line x1={x(range[1])} x2={x(range[1])} y1={y + 2} y2={y + bar - 2} />
                        </g>
                      )}
                      {si === 1 && (
                        <text x={Math.max(end, range ? x(range[1]) : end) + 6} y={y + bar - 2} fontSize="10" fontWeight="600" fill={CHART.text}>
                          {formatNumber(v, digits)}{unit}
                        </text>
                      )}
                    </g>
                  );
                })}
              </g>
            );
          })}
      </svg>
      </div>
      <div className="flex flex-wrap gap-4 mt-1 text-xs text-on-surface-variant">
        {series.map((s, i) => (
          <span key={s.label} className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ background: colors[i] }}></span>{s.label}
          </span>
        ))}
        {categories.some((c) => c.ranges) && (
          <span className="flex items-center gap-1.5"><span className="inline-block w-4 border-t border-on-surface-variant"></span>Range across optimiser runs</span>
        )}
      </div>
    </div>
  );
}
