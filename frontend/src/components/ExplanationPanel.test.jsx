import React from 'react';
import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import reasoning from '../__fixtures__/fuzzy-reasoning-salem.json';
import { FuzzyRulesSection } from './ExplanationPanel';

describe('FuzzyRulesSection', () => {
  it('ranks rules and shows status, share, limiting condition and importance', () => {
    const html = renderToString(<FuzzyRulesSection reasoning={reasoning} />);
    const { inference } = reasoning;
    expect(html).toContain(`${inference.summary.decisive} decisive, ${inference.summary.masked} masked`);
    const order = inference.ranking.map((n) => html.indexOf(`#<!-- -->${n}<`));
    expect(order.every((pos, i) => pos > 0 && (i === 0 || pos > order[i - 1]))).toBe(true);
    expect(html).toContain('Decisive');
    expect(html).toContain('Masked');
    expect(html).toContain('by #<!-- -->2');
    expect(html).toContain('Canal irrigation advantage under deficit');
    expect(html).toContain('66.2%');
    expect(html).toContain('rainfall_dev is deficit (0.2927)');
  });

  it('falls back to the plain list without inference', () => {
    const html = renderToString(<FuzzyRulesSection reasoning={{ ...reasoning, inference: undefined }} />);
    expect(html).toContain(`Fuzzy rules that fired (<!-- -->${reasoning.fired_rules.length}`);
    expect(html).not.toContain('Importance');
    for (const r of reasoning.fired_rules) expect(html).toContain(`#<!-- -->${r.rule}<`);
  });
});
