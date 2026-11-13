import React from 'react';
import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import reasoning from '../__fixtures__/fuzzy-reasoning-salem.json';
import cropEvidence from '../__fixtures__/crop-evidence-salem.json';
import { CropEvidenceSection, FuzzyRulesSection } from './ExplanationPanel';
import { OFFICIAL_DATA_NA } from '../services/officialData';

describe('FuzzyRulesSection', () => {
  it('ranks rules and shows status, share, limiting condition and importance', () => {
    const html = renderToString(<FuzzyRulesSection reasoning={reasoning} />);
    const { inference } = reasoning;
    expect(html).toContain(`${inference.summary.decisive} decisive, ${inference.summary.masked} masked`);
    const order = inference.ranking.map((n) => html.indexOf(`#<!-- -->${n}<`));
    expect(order.every((pos, i) => pos > 0 && (i === 0 || pos > order[i - 1]))).toBe(true);
    expect(html).toContain('Decisive');
    expect(html).toContain('Masked');
    const masked = inference.rules.find((r) => r.status === 'masked' && r.masked_by.length);
    expect(html).toContain(`by #<!-- -->${masked.masked_by[0]}`);
    const named = inference.rules.find((r) => r.status !== 'not fired' && r.scenario);
    expect(html).toContain(named.scenario);
    const decisive = inference.rules.find((r) => r.status === 'decisive' && r.contribution_pct.yield_conf !== undefined);
    expect(html).toContain(`${decisive.contribution_pct.yield_conf}%`);
    const lc = decisive.limiting_condition;
    expect(html).toContain(`${lc.variable} is ${lc.term} (${lc.membership})`);
  });

  it('falls back to the plain list without inference', () => {
    const html = renderToString(<FuzzyRulesSection reasoning={{ ...reasoning, inference: undefined }} />);
    expect(html).toContain(`Fuzzy rules that fired (<!-- -->${reasoning.fired_rules.length}`);
    expect(html).not.toContain('Importance');
    for (const r of reasoning.fired_rules) expect(html).toContain(`#<!-- -->${r.rule}<`);
  });
});

describe('CropEvidenceSection', () => {
  it('shows every crop and every criterion with status, evidence and official source', () => {
    const html = renderToString(<CropEvidenceSection cropEvidence={cropEvidence} />)
      .replace(/<!-- -->/g, '').replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, '&');
    expect(html).toContain('Why this crop was selected');
    for (const crop of cropEvidence) {
      expect(html).toContain(crop.crop);
      for (const c of crop.criteria) {
        expect(html).toContain(c.statement.slice(0, 40));
        for (const src of c.sources) expect(html).toContain(src.dataset);
      }
    }
    for (const label of ['Rainfall', 'Soil', 'Water', 'Budget', 'Fertilizer', 'MSP', 'Market Price', 'Yield', 'Duration', 'Risks']) {
      expect(html).toContain(label);
    }
    expect(html).not.toMatch(/undefined|NaN|null/);
  });

  it('says official data is not available when there is no evidence', () => {
    expect(renderToString(<CropEvidenceSection cropEvidence={[]} />)).toContain(OFFICIAL_DATA_NA);
  });
});
