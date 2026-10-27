import React from 'react';
import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import rerank from '../../__fixtures__/topsis-rerank-salem.json';
import topsisExplanation from '../../__fixtures__/topsis-explanation-salem.json';
import ProfileSelector from './ProfileSelector';
import { ContributionCard, ProfileComparison, WeightChart } from './TopsisPanel';
import { TopsisSection } from '../ExplanationPanel';
import { BALANCED_PERCENT } from '../../utils/topsisView';

const noop = () => {};

describe('ProfileSelector', () => {
  it('lists every profile and marks the selected one', () => {
    const html = renderToString(<ProfileSelector profile="water" onProfileChange={noop} customPercent={BALANCED_PERCENT} onCustomChange={noop} />);
    for (const label of ['Balanced', 'Profit priority', 'Water saving', 'Sustainability', 'Low cost', 'Custom']) expect(html).toContain(label);
    expect(html).toContain('checked="" value="water"');
    expect(html).not.toContain('Custom weights');
  });

  it('shows the weight builder for custom, with the running total', () => {
    const html = renderToString(<ProfileSelector profile="custom" onProfileChange={noop} customPercent={{ yield: 60, water: 20 }} onCustomChange={noop} />);
    expect(html).toContain('Custom weights');
    expect(html).toContain('Rainfall exposure');
    expect(html).toContain('Total <!-- -->80.0<!-- -->%');
    expect(html).toContain('must add up to 100%');
  });

  it('confirms a valid custom total', () => {
    const html = renderToString(<ProfileSelector profile="custom" onProfileChange={noop} customPercent={BALANCED_PERCENT} onCustomChange={noop} />);
    expect(html).toContain('Total <!-- -->100.0<!-- -->%');
    expect(html).toContain('✓');
  });
});

describe('TOPSIS panel parts', () => {
  it('charts the weight distribution', () => {
    const html = renderToString(<WeightChart weights={rerank.topsis.weights} />);
    expect(html).toContain('Weight distribution');
    expect(html).toContain('Income');
    expect(html).not.toContain('Rainfall exposure');   // zero weight under Profit
  });

  it('shows weight, contribution and score of the top plan', () => {
    const plan = rerank.explanation.plans[0];
    const html = renderToString(<ContributionCard plan={plan} idealBest={rerank.explanation.ideal_best} />);
    expect(html).toContain(`How plan #${plan.rank} scored ${plan.closeness.toFixed(4)}`);
    expect(html).toContain('Weighted value');
    expect(html).toContain('Best in set');
  });

  it('compares the profiles', () => {
    const html = renderToString(<ProfileComparison comparison={rerank.comparison} />);
    expect(html).toContain('Best plan under each profile');
    expect(html).toContain('Profit priority<!-- --> (selected)');
    expect(html).toContain('Ranking changes');
    expect(html).toContain('Weight differences');
  });
});

describe('Explanation TOPSIS section', () => {
  it('shows score, weights, contributions and the neighbouring plans', () => {
    const html = renderToString(<TopsisSection topsis={topsisExplanation} />);
    const p = topsisExplanation.plan;
    expect(html).toContain(`TOPSIS score: ${p.closeness.toFixed(4)} (rank #${p.rank} of ${topsisExplanation.plans_ranked})`);
    expect(html).toContain('Profile: Profit priority');
    for (const c of p.criteria) expect(html).toContain(c.label);
    expect(html).toContain(topsisExplanation.versus_next.summary);
    expect(html).toContain('Rank under each profile: <!-- -->Balanced #');
  });
});
