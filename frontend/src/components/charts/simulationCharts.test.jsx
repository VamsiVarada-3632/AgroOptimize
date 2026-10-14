import React from 'react';
import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import GroupedBarChart from './GroupedBarChart';
import DeltaBarChart from './DeltaBarChart';
import RadarChart from './RadarChart';
import { CHART } from './chartTheme';

const count = (html, needle) => html.split(needle).length - 1;
const SERIES = [{ label: 'Original' }, { label: 'Simulated' }];

describe('GroupedBarChart', () => {
  it('draws two bars per category, names both series and shows ranges', () => {
    const html = renderToString(<GroupedBarChart series={SERIES} unit="%"
      categories={[{ key: 'a', label: 'A', values: [10, 20], ranges: [[8, 12], [15, 25]] }, { key: 'b', label: 'B', values: [5, 0] }]} />);
    expect(count(html, 'rx="4"')).toBe(4);
    expect(html).toContain(`fill="${CHART.context}"`);
    expect(html).toContain(`fill="${CHART.accent}"`);
    expect(html).toContain('Original');
    expect(html).toContain('Simulated');
    expect(html).toContain('Range across optimiser runs');
    expect(html).not.toMatch(/NaN/);
  });

  it('skips missing values', () => {
    const html = renderToString(<GroupedBarChart series={SERIES} categories={[{ key: 'a', label: 'A', values: [null, 3] }]} />);
    expect(count(html, 'rx="4"')).toBe(1);
  });
});

describe('DeltaBarChart', () => {
  const items = [
    { key: 'y', label: 'Yield', change: -12.5, reliable: true, verdictLabel: 'Worsened' },
    { key: 'w', label: 'Water', change: 3.2, reliable: false, verdictLabel: 'Within search variation' },
    { key: 'p', label: 'Profit', change: null, reliable: false, verdictLabel: 'Data not available' },
  ];

  it('labels every bar with value and verdict, accent only for reliable changes', () => {
    const html = renderToString(<DeltaBarChart items={items} />);
    expect(count(html, 'rx="4"')).toBe(2);
    expect(html).toContain('-12.5%');
    expect(html).toContain('+3.2%');
    expect(html).toContain('Within search variation');
    expect(count(html, `fill="${CHART.accent}"`)).toBe(1);
    expect(html).not.toMatch(/NaN/);
  });
});

describe('RadarChart', () => {
  it('draws one polygon per series plus rings, with a legend', () => {
    const axes = [{ key: 'a', label: 'A' }, { key: 'b', label: 'B' }, { key: 'c', label: 'C' }];
    const html = renderToString(<RadarChart axes={axes} series={[
      { label: 'Original plan', values: { a: 0.2, b: 0.5, c: 1 } }, { label: 'Simulated plan', values: { a: 0.8, b: 0.1, c: 0 } }]} />);
    expect(count(html, '<polygon')).toBe(4 + 2);
    expect(count(html, '<circle')).toBe(6);
    expect(html).toContain('Simulated plan');
    expect(html).not.toMatch(/NaN/);
  });
});
