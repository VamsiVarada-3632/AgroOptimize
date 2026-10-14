import React from 'react';
import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import LineChart from './LineChart';
import BarChart from './BarChart';
import ChartCard from './ChartCard';
import { CHART, niceTicks } from './chartTheme';

const count = (html, needle) => html.split(needle).length - 1;

describe('niceTicks', () => {
  it('covers the range with round steps', () => {
    const t = niceTicks(3, 97);
    expect(t[0]).toBeLessThanOrEqual(3);
    expect(t[t.length - 1]).toBeGreaterThanOrEqual(97);
    expect(new Set(t.slice(1).map((v, i) => +(v - t[i]).toFixed(6))).size).toBe(1);
  });

  it('handles a flat range and bad input', () => {
    expect(niceTicks(5, 5).length).toBeGreaterThan(1);
    expect(niceTicks(NaN, 1)).toEqual([0, 1]);
  });
});

describe('LineChart', () => {
  const series = [
    { id: 'a', label: 'Alpha', emphasis: true, points: [{ x: 2020, y: 1 }, { x: 2021, y: 2 }, { x: 2022, y: 3 }] },
    { id: 'b', label: 'Beta', emphasis: false, points: [{ x: 2020, y: 2 }, { x: 2021, y: 2 }, { x: 2022, y: 1 }] },
  ];

  it('draws one path per series with emphasis colours and a legend', () => {
    const html = renderToString(<LineChart series={series} xValues={[2020, 2021, 2022]} ariaLabel="test" />);
    expect(count(html, '<path')).toBe(2);
    expect(html).toContain(`stroke="${CHART.accent}"`);
    expect(html).toContain(`stroke="${CHART.context}"`);
    expect(html).toContain('Alpha');           // direct label + legend
    expect(html).toContain('role="img"');
  });

  it('single series has no legend and draws the reference line', () => {
    const html = renderToString(
      <LineChart series={[series[0]]} xValues={[2020, 2021, 2022]} reference={{ value: 2.5, label: 'Limit' }} />,
    );
    expect(html).toContain('stroke-dasharray');
    expect(html).toContain('Limit');
    expect(html).not.toContain('Others');
  });

  it('minSpan keeps tiny changes from filling the whole axis', () => {
    const flat = [{ id: 't', label: 'Temp', emphasis: true, points: [{ x: 1, y: 28.92 }, { x: 2, y: 29.0 }] }];
    const zoomed = renderToString(<LineChart series={flat} xValues={[1, 2]} digits={2} />);
    const spanned = renderToString(<LineChart series={flat} xValues={[1, 2]} digits={2} minSpan={2} />);
    expect(zoomed).toContain('>28.92<');          // axis hugs the data
    expect(spanned).not.toContain('>28.92<');     // axis widened to ≥ 2 units
    expect(spanned).toMatch(/>28<|>28.5<|>27.5</);
  });

  it('skips missing points without breaking the path', () => {
    const gap = [{ id: 'g', label: 'Gap', emphasis: true, points: [{ x: 1, y: 1 }, { x: 3, y: 3 }] }];
    const html = renderToString(<LineChart series={gap} xValues={[1, 2, 3]} />);
    expect(html).not.toMatch(/NaN/);
  });
});

describe('BarChart', () => {
  const data = [
    { key: 'x', label: 'X', value: 10, reference: 12 },
    { key: 'y', label: 'Y', value: 20, reference: 18, highlight: true },
  ];

  it('renders one rounded bar per datum with reference marks and tooltips', () => {
    const html = renderToString(<BarChart data={data} referenceLabel="Normal" unit=" mm" />);
    expect(count(html, 'rx="4"')).toBe(2);
    expect(count(html, '<title>')).toBe(2);
    expect(html).toContain('Normal');
    expect(html).toContain('20 mm');        // value label on the highlighted bar only
    expect(html).not.toContain('>10 mm<');
  });

  it('supports horizontal orientation', () => {
    const html = renderToString(<BarChart data={data} orientation="horizontal" />);
    expect(count(html, 'rx="4"')).toBe(2);
    expect(html).not.toMatch(/NaN/);
  });
});

describe('ChartCard', () => {
  it('offers a table view toggle when table data is given', () => {
    const html = renderToString(
      <ChartCard title="T" table={{ columns: [{ key: 'a', label: 'A' }], rows: [{ a: 1 }] }}><span>chart</span></ChartCard>,
    );
    expect(html).toContain('Show table');
    expect(html).toContain('chart');
  });
});
