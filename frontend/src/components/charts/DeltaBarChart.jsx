import React, { useMemo } from 'react';
import { CHART, niceTicks, formatNumber } from './chartTheme';

/**
 * Diverging bars of percentage change around a zero line. Position carries
 * the sign; a reliable change is drawn in the accent colour and a change the
 * statistics cannot separate from noise recedes in gray. Every bar is also
 * labelled with its value and verdict, so nothing depends on colour alone.
 *
 * items: [{ key, label, change: number|null, reliable: boolean, verdictLabel }]
 */
export default function DeltaBarChart({ items, ariaLabel }) {
  const width = 560;
  const rowH = 30;
  const pad = { top: 8, right: 190, bottom: 24, left: 130 };
  const h = pad.top + pad.bottom + items.length * rowH;
  const innerW = width - pad.left - pad.right;
  const ticks = useMemo(() => {
    const vals = items.map((i) => i.change).filter((v) => v !== null && Number.isFinite(v));
    const m = Math.max(5, ...vals.map(Math.abs));
    return niceTicks(-m, m);
  }, [items]);
  const lo = ticks[0];
  const hi = ticks[ticks.length - 1];
  const x = (v) => pad.left + ((v - lo) / (hi - lo || 1)) * innerW;

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${h}`} className="w-full h-auto min-w-[480px]" role="img" aria-label={ariaLabel}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={pad.top} y2={h - pad.bottom} stroke={CHART.grid} />
            <text x={x(t)} y={h - 8} fontSize="10" fill={CHART.text} textAnchor="middle">{formatNumber(t, 0)}%</text>
          </g>
        ))}
        <line x1={x(0)} x2={x(0)} y1={pad.top} y2={h - pad.bottom} stroke={CHART.axis} strokeWidth="1.5" />
        {items.map((it, i) => {
          const y = pad.top + i * rowH + 7;
          const has = it.change !== null && Number.isFinite(it.change);
          const end = has ? x(it.change) : x(0);
          return (
            <g key={it.key}>
              <text x={pad.left - 8} y={y + 12} fontSize="11" fill={CHART.text} textAnchor="end">{it.label}</text>
              {has && (
                <rect x={Math.min(x(0), end)} y={y} width={Math.max(1, Math.abs(end - x(0)))} height="16" rx="4"
                  fill={it.reliable ? CHART.accent : CHART.context}>
                  <title>{`${it.label}: ${it.change > 0 ? '+' : ''}${formatNumber(it.change, 1)}% · ${it.verdictLabel}`}</title>
                </rect>
              )}
              <text x={pad.left + innerW + 8} y={y + 12} fontSize="10" fill={CHART.text}>
                <tspan fontWeight="600">{has ? `${it.change > 0 ? '+' : ''}${formatNumber(it.change, 1)}%` : '—'}</tspan>
                <tspan dx="6">{it.verdictLabel}</tspan>
              </text>
            </g>
          );
        })}
      </svg>
      </div>
  );
}
