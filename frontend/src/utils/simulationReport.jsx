import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import GroupedBarChart from '../components/charts/GroupedBarChart';
import DeltaBarChart from '../components/charts/DeltaBarChart';
import RadarChart from '../components/charts/RadarChart';
import {
  changedConditions, contributionCategories, cropShareCategories, deltaItems, formatPct, impactMetrics,
  radarData, simulationTitle,
} from './simulationView';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

function table(headers, rows) {
  return `<table><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${
    rows.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
}

const items = (list) => `<ul>${(list || []).map((i) => `<li><strong>${esc(i.title)}.</strong> ${esc(i.detail)} <em>(${esc(i.source)})</em></li>`).join('')}</ul>`;

/**
 * Self-contained HTML report of one simulation: conditions, results, impact,
 * trade-offs, explanation and summary, with the page's charts embedded as
 * static SVG. Opens in any browser and prints to PDF.
 */
export function simulationReportHtml(result, { name, savedAt } = {}) {
  const b = result.inputs.base;
  const svg = (el) => renderToStaticMarkup(el);
  const cropCats = cropShareCategories(result);
  const radar = radarData(result);
  const contrib = contributionCategories(result);
  const metrics = impactMetrics(result);
  const scen = result.scenario;
  const base = result.baseline;

  const sections = [
    `<h1>${esc(name || 'Scenario simulation report')}</h1>
     <p class="meta">${esc(simulationTitle(result))} · data year ${esc(result.summary.year)}${result.summary.data_year_estimated ? ' (estimated)' : ''}
     · ${esc(savedAt ? new Date(savedAt).toLocaleString() : new Date().toLocaleString())}</p>
     <div class="summary">${esc(result.summary.text)}</div>`,
    `<h2>Original and modified conditions</h2>${table(['Condition', 'Original', 'Scenario', 'Enters the pipeline at', 'Detail'],
      result.conditions.map((c) => [c.label + (c.changed ? ' *' : ''), c.baseline, c.scenario, c.enters, c.detail]))}
     <p class="note">* changed in this scenario. District ${esc(b.location)}, season ${esc(b.season)}.</p>`,
    `<h2>Optimization results</h2>${scen.available ? `
      ${table(['', 'Original recommendation', 'Simulated recommendation'], [
        ['Crop plan', base.crop_mix.map((c) => `${c.crop} ${c.share_pct.toFixed(1)}%`).join(', '),
          scen.crop_mix.map((c) => `${c.crop} ${c.share_pct.toFixed(1)}%`).join(', ')],
        ['TOPSIS closeness', result.comparison.ranking.baseline.closeness, result.comparison.ranking.scenario.closeness],
        ['Recommendation', result.comparison.ranking.baseline.recommendation, result.comparison.ranking.scenario.recommendation],
        ['Confidence', `${result.comparison.confidence.baseline_pct}%`, `${result.comparison.confidence.scenario_pct}%`],
      ])}
      <figure>${svg(<GroupedBarChart categories={cropCats} series={[{ label: 'Original' }, { label: 'Simulated' }]} unit="%" ariaLabel="Crop shares" />)}
      <figcaption>Land share of each crop in the two recommended plans.</figcaption></figure>`
      : `<p>${esc(scen.reason)}</p>`}`,
    result.impact ? `<h2>Impact analysis</h2><p class="note">${esc(result.impact.method)} ${esc(result.impact.basis_note)}</p>
      ${table(['Metric', 'Original', 'Simulated', 'Change', 'Verdict', 'p'], metrics.map((m) =>
        [m.label, m.baselineText, m.scenarioText, formatPct(m.change_pct), m.verdictInfo.label, m.p_value ?? '—']))}
      <figure>${svg(<DeltaBarChart items={deltaItems(result)} ariaLabel="Change by metric" />)}
      <figcaption>Change of each metric; gray bars are within the optimiser's run-to-run variation.</figcaption></figure>` : '',
    `<h2>Decision impact</h2>${items(result.decision_impact)}`,
    `<h2>Trade-offs</h2>${table(['Improved', 'Worsened', 'No change', 'Within search variation'], [[
      result.trade_offs.improved.map((m) => `${m.label} ${formatPct(m.change_pct)}`).join(', ') || '—',
      result.trade_offs.worsened.map((m) => `${m.label} ${formatPct(m.change_pct)}`).join(', ') || '—',
      result.trade_offs.unchanged.map((m) => m.label).join(', ') || '—',
      result.trade_offs.not_significant.map((m) => m.label).join(', ') || '—',
    ]])}
     <h3>Constraints</h3>${table(['Constraint', 'Original', 'Scenario', 'Harder'], result.constraints.map((c) =>
      [c.label, c.baseline_status ?? '—', c.scenario_status ?? '—', c.became_harder ? 'Yes' : 'No']))}`,
    `<h2>Optimization difference</h2>
     ${radar ? `<figure>${svg(<RadarChart axes={radar.axes} series={radar.series} ariaLabel="Objective profile" />)}
       <figcaption>${esc(result.optimization.common_scale.note)}</figcaption></figure>` : ''}
     ${contrib.length ? `<figure>${svg(<GroupedBarChart categories={contrib} series={[{ label: 'Original' }, { label: 'Simulated' }]} ariaLabel="Objective contributions" />)}
       <figcaption>TOPSIS weight × goodness per objective for each recommended plan.</figcaption></figure>` : ''}
     ${result.optimization.decomposition ? table(['Objective', 'Original plan', 'Original plan, new conditions', 'Simulated plan', 'Condition effect', 'Re-optimisation effect'],
      result.optimization.decomposition.rows.map((r) => [r.label, r.baseline_plan, r.baseline_plan_in_scenario, r.scenario_plan,
        formatPct(r.condition_effect_pct), formatPct(r.reoptimisation_effect_pct)])) : ''}
     <h3>Fuzzy rules that changed</h3>${result.fuzzy_changes.rules_changed.length ? table(['Rule', 'If', 'Then', 'Original', 'Scenario', 'Status'],
      result.fuzzy_changes.rules_changed.map((r) => [r.rule, r.if, r.then, r.baseline_strength, r.scenario_strength, r.status])) : '<p>None.</p>'}`,
    result.historical.available ? `<h2>Historical comparison</h2><p class="note">${esc(result.historical.method)}</p>
      ${table(['Crop', 'Simulated share', 'Historical share', 'Expected yield (t/ha)', 'Historical yield (t/ha)'],
        (result.historical.scenario || []).map((r) => [r.crop, `${r.plan_share_pct}%`, `${r.historical_share_pct}%`,
          r.expected_yield_t_ha ?? '—', r.historical_yield_t_ha ?? '—']))}
      <p>Alignment with the district's observed cropping pattern: ${esc(result.historical.alignment_pct.baseline)}% → ${esc(result.historical.alignment_pct.scenario ?? '—')}%.</p>` : '',
    scen.available ? `<h2>Recommendation explanation (simulated plan)</h2>${items(scen.explanation.reasons)}
      <h3>Risks</h3>${items(scen.explanation.risks)}` : '',
    `<h2>Scenario summary</h2>${result.summary.sentences.map((s) => `<p>${esc(s)}</p>`).join('')}
     <p class="note">Changed: ${esc(changedConditions(result).map((c) => c.label).join(', ') || 'nothing')}.
     ${esc(result.optimization.seed_note)} Prices are the dataset's unvalidated price column; profit is not an optimiser objective.</p>`,
  ];

  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(name || 'Scenario simulation report')}</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#1a1c1c;background:#fff;max-width:900px;margin:0 auto;padding:24px 16px;line-height:1.5}
h1{color:#00522a;margin-bottom:4px}h2{color:#00522a;border-bottom:1px solid #e4e2e2;padding-bottom:4px;margin-top:32px}
.meta,.note,figcaption{color:#404940;font-size:13px}.summary{background:#f2f4f1;border-left:4px solid #1f6b3a;padding:12px 16px;border-radius:6px}
table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}th,td{border-bottom:1px solid #e4e2e2;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#f6f6f6}figure{margin:16px 0}svg{max-width:100%;height:auto}li{margin-bottom:6px}
@media print{body{padding:0}h2{break-after:avoid}figure,table{break-inside:avoid}}
</style></head><body>${sections.join('\n')}</body></html>`;
}
