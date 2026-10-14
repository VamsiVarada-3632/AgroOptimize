import React, { useMemo, useState } from 'react';
import { CHART, niceTicks, formatNumber } from './chartTheme';

/**
 * Multi-series line chart with emphasis styling, a hover crosshair and
 * tooltip, and an optional horizontal reference line.
 *
 * series: [{ id, label, points: [{ x, y }], emphasis?: boolean }]
 *   Emphasised series are drawn in the accent colour and direct-labelled at
 *   their last point; the rest recede in gray. With two or more series a
 *   legend is shown.
 * xValues: ordered x values (numbers or strings) shared by all series.
 * minSpan: smallest y-range to draw, so tiny changes are not stretched into
 *   dramatic-looking swings (e.g. 2 °C for temperature).
 */
export default function LineChart({
  series, xValues, formatX = (x) => x, unit = '', digits = 1, yLabel, reference, height = 220, ariaLabel, minSpan = 0,
}) {
  const [hoverIdx, setHoverIdx] = useState(null);
  const width = 560;
  const pad = { top: 16, right: 84, bottom: 30, left: 52 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;

  const { ticks, yMin, yMax } = useMemo(() => {
    const ys = series.flatMap((s) => s.points.map((p) => p.y)).filter((v) => v !== null && Number.isFinite(v));
    if (reference) ys.push(reference.value);
    let lo = Math.min(...ys);
    let hi = Math.max(...ys);
    if (hi - lo < minSpan) {
      const mid = (hi + lo) / 2;
      lo = mid - minSpan / 2;
      hi = mid + minSpan / 2;
    }
    const t = niceTicks(lo, hi);
    return { ticks: t, yMin: t[0], yMax: t[t.length - 1] };
  }, [series, reference, minSpan]);

  const xPos = (i) => pad.left + (xValues.length <= 1 ? innerW / 2 : (i / (xValues.length - 1)) * innerW);
  const yPos = (v) => pad.top + innerH - ((v - yMin) / (yMax - yMin || 1)) * innerH;
  const ordered = [...series].sort((a, b) => Number(Boolean(a.emphasis)) - Number(Boolean(b.emphasis)));
  const pathFor = (s) => {
    let d = '';
    xValues.forEach((x, i) => {
      const p = s.points.find((pt) => pt.x === x);
      if (!p || p.y === null || !Number.isFinite(p.y)) return;
      d += `${d ? 'L' : 'M'}${xPos(i).toFixed(1)},${yPos(p.y).toFixed(1)} `;
    });
    return d.trim();
  };

  const onMove = (ev) => {
    const rect = ev.currentTarget.getBoundingClientRect();
    const x = ((ev.clientX - rect.left) / rect.width) * width;
    let best = 0;
    xValues.forEach((_, i) => { if (Math.abs(xPos(i) - x) < Math.abs(xPos(best) - x)) best = i; });
    setHoverIdx(best);
  };

  const hoverX = hoverIdx !== null ? xValues[hoverIdx] : null;
  const hoverRows = hoverX === null ? [] : series
    .map((s) => ({ s, p: s.points.find((pt) => pt.x === hoverX) }))
    .filter((r) => r.p && r.p.y !== null)
    .sort((a, b) => b.p.y - a.p.y);

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto" role="img" aria-label={ariaLabel}
        onMouseMove={onMove} onMouseLeave={() => setHoverIdx(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={pad.left + innerW} y1={yPos(t)} y2={yPos(t)} stroke={CHART.grid} strokeWidth="1" />
            <text x={pad.left - 8} y={yPos(t) + 3} fontSize="10" fill={CHART.text} textAnchor="end">{formatNumber(t, digits)}</text>
          </g>
        ))}
        {xValues.map((x, i) => (
          <text key={String(x)} x={xPos(i)} y={height - 10} fontSize="10" fill={CHART.text} textAnchor="middle">{formatX(x)}</text>
        ))}
        {yLabel && (
          <text x={12} y={pad.top + innerH / 2} fontSize="10" fill={CHART.text} textAnchor="middle"
            transform={`rotate(-90 12 ${pad.top + innerH / 2})`}>{yLabel}</text>
        )}
        {reference && (
          <g>
            <line x1={pad.left} x2={pad.left + innerW} y1={yPos(reference.value)} y2={yPos(reference.value)}
              stroke={CHART.reference} strokeWidth="1.5" strokeDasharray="5 4" />
            <text x={pad.left + innerW + 4} y={yPos(reference.value) + 3} fontSize="10" fill={CHART.text}>{reference.label}</text>
          </g>
        )}
        {ordered.map((s) => (
          <path key={s.id} d={pathFor(s)} fill="none" stroke={s.emphasis ? CHART.accent : CHART.context}
            strokeWidth={s.emphasis ? 2.5 : 1.5} strokeLinejoin="round" strokeLinecap="round" />
        ))}
        {ordered.filter((s) => s.emphasis).map((s) => {
          const last = [...xValues].reverse().map((x) => s.points.find((p) => p.x === x)).find((p) => p && p.y !== null);
          if (!last) return null;
          const i = xValues.indexOf(last.x);
          return (
            <text key={`label-${s.id}`} x={xPos(i) + 6} y={yPos(last.y) + 3} fontSize="10" fontWeight="600" fill={CHART.text}>{s.label}</text>
          );
        })}
        {hoverIdx !== null && (
          <g>
            <line x1={xPos(hoverIdx)} x2={xPos(hoverIdx)} y1={pad.top} y2={pad.top + innerH} stroke={CHART.axis} strokeWidth="1" />
            {hoverRows.map(({ s, p }) => (
              <circle key={s.id} cx={xPos(hoverIdx)} cy={yPos(p.y)} r="4"
                fill={s.emphasis ? CHART.accent : CHART.context} stroke={CHART.surface} strokeWidth="2" />
            ))}
          </g>
        )}
      </svg>
      {hoverIdx !== null && hoverRows.length > 0 && (
        <div className="absolute top-2 pointer-events-none bg-inverse-surface text-inverse-on-surface text-xs rounded-lg px-3 py-2 shadow-lg z-10"
          style={{ left: `${(xPos(hoverIdx) / width) * 100 > 60 ? 4 : 62}%` }}>
          <p className="font-bold mb-1">{formatX(hoverX)}</p>
          {hoverRows.map(({ s, p }) => (
            <p key={s.id} className="flex justify-between gap-4">
              <span>{s.label}</span><span className="font-semibold">{formatNumber(p.y, digits)}{unit}</span>
            </p>
          ))}
        </div>
      )}
      {series.length >= 2 && (
        <div className="flex flex-wrap gap-4 mt-1 text-xs text-on-surface-variant">
          {series.filter((s) => s.emphasis).map((s) => (
            <span key={s.id} className="flex items-center gap-1.5">
              <span className="inline-block w-5 h-[3px] rounded" style={{ background: CHART.accent }}></span>{s.label}
            </span>
          ))}
          {series.some((s) => !s.emphasis) && (
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-5 h-[2px] rounded" style={{ background: CHART.context }}></span>
              {series.filter((s) => !s.emphasis).length === 1 ? series.find((s) => !s.emphasis).label : 'Others'}
            </span>
          )}
          {reference && (
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-5 border-t-2 border-dashed" style={{ borderColor: CHART.reference }}></span>{reference.label}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
