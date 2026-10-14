import React from 'react';
import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import drought from '../../__fixtures__/simulation-drought.json';
import infeasible from '../../__fixtures__/simulation-infeasible.json';
import {
  ConditionsSection, CropEffectsSection, DecisionImpactSection, HistoricalSection, ImpactSection,
  OptimizationSection, RecommendationSection, TradeOffSection, VerdictBadge,
} from './SimulationSections';
import SimulationView from '../../views/SimulationView';
import { simulationReportHtml } from '../../utils/simulationReport';

const render = (el) => renderToString(el);

describe('simulation sections with a real result', () => {
  it('compares the two recommendations', () => {
    const html = render(<RecommendationSection result={drought} />);
    expect(html).toContain('Original recommendation');
    expect(html).toContain('Simulated recommendation');
    for (const c of drought.scenario.crop_mix) expect(html).toContain(c.crop);
    expect(html).toContain('Confidence comparison');
  });

  it('shows impact cards with verdicts and p-values', () => {
    const html = render(<ImpactSection result={drought} />);
    expect(html).toContain('Impact summary');
    expect(html).toContain('paired t-test p');
    expect(html).toContain('Difference by metric');
    expect(html).toContain(drought.impact.method.slice(0, 40));
  });

  it('renders every generated statement', () => {
    const html = render(<DecisionImpactSection result={drought} />);
    for (const item of drought.decision_impact) expect(html).toContain(item.title.replace(/'/g, '&#x27;'));
  });

  it('renders trade-offs, optimisation difference, crop effects, history and conditions', () => {
    expect(render(<TradeOffSection result={drought} />)).toContain('Harder constraints');
    const opt = render(<OptimizationSection result={drought} />);
    expect(opt).toContain('Objective profile');
    expect(opt).toContain('Fuzzy rules that changed');
    expect(opt).toContain('Same plan, new conditions');
    const crops = render(<CropEffectsSection result={drought} />);
    for (const e of drought.crop_effects) expect(crops).toContain(e.crop);
    expect(render(<HistoricalSection result={drought} />)).toContain('Alignment with history');
    const cond = render(<ConditionsSection result={drought} />);
    expect(cond).toContain('Enters at');
    expect(cond).toContain('Fuzzy water-storage input');
  });

  it('labels verdicts with text and an icon, not colour alone', () => {
    const html = render(<VerdictBadge verdict="not_significant" />);
    expect(html).toContain('Within search variation');
    expect(html).toContain('material-symbols-outlined');
  });
});

describe('infeasible scenario', () => {
  it('explains why instead of showing impact', () => {
    expect(render(<RecommendationSection result={infeasible} />)).toContain(infeasible.scenario.reason.slice(0, 40));
    expect(render(<ImpactSection result={infeasible} />)).toBe('');
    expect(render(<TradeOffSection result={infeasible} />)).toContain('Feasible plans');
    expect(render(<OptimizationSection result={infeasible} />)).not.toContain('Objective profile');
  });

  it('shows Data not available when there is no history', () => {
    const html = render(<HistoricalSection result={{ ...drought, historical: { available: false } }} />);
    expect(html).toContain('Data not available');
  });
});

describe('report and page', () => {
  it('exports a self-contained report with charts', () => {
    const html = simulationReportHtml(drought, { name: 'Drought <test>' });
    expect(html.startsWith('<!doctype html>')).toBe(true);
    for (const heading of ['Original and modified conditions', 'Optimization results', 'Impact analysis', 'Decision impact',
      'Trade-offs', 'Optimization difference', 'Historical comparison', 'Recommendation explanation', 'Scenario summary']) {
      expect(html).toContain(heading);
    }
    expect((html.match(/<svg/g) || []).length).toBeGreaterThanOrEqual(3);
    expect(html).toContain('Drought &lt;test&gt;');
    expect(html).not.toContain('<test>');
  });

  it('exports a report for an infeasible scenario', () => {
    const html = simulationReportHtml(infeasible);
    expect(html).toContain(infeasible.scenario.reason.slice(0, 30));
    expect(html).not.toContain('Impact analysis');
  });

  it('renders the empty page with the form', () => {
    const html = render(<SimulationView userLocation="Salem" onNavigate={() => {}} />);
    expect(html).toContain('Scenario Simulation');
    expect(html).toContain('Run simulation');
    expect(html).toContain('Water availability');
    expect(html).toContain('Saved scenarios');
  });
});
