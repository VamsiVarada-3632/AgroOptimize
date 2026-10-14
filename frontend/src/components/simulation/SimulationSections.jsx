import React from 'react';
import ChartCard from '../charts/ChartCard';
import GroupedBarChart from '../charts/GroupedBarChart';
import DeltaBarChart from '../charts/DeltaBarChart';
import RadarChart from '../charts/RadarChart';
import { NA, SectionHeader } from '../district/DistrictSections';
import {
  OBJECTIVE_LABELS, VERDICTS, confidenceCategories, contributionCategories, cropShareCategories, deltaItems,
  formatMetric, formatPct, impactMetrics, indexedCategories, prettyStatus, radarData,
} from '../../utils/simulationView';

/*
 * Scenario Simulation result sections. Each renders one part of the
 * POST /api/simulations/run payload; nothing is computed here.
 */

const SERIES = [{ label: 'Original' }, { label: 'Simulated' }];

function Card({ children, className = '' }) {
  return <section className={`bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4 ${className}`}>{children}</section>;
}

function Statements({ items, empty }) {
  if (!items?.length) return <p className="text-sm text-on-surface-variant">{empty}</p>;
  return (
    <ul className="space-y-2">
      {items.map((i) => (
        <li key={i.id} className="p-3 rounded-lg bg-surface-container-low text-sm">
          <p className="font-semibold text-on-surface">{i.title}</p>
          <p className="text-on-surface-variant mt-0.5">{i.detail}</p>
          <p className="text-[11px] text-outline mt-1">Source: {i.source}</p>
        </li>
      ))}
    </ul>
  );
}

export function VerdictBadge({ verdict }) {
  const v = VERDICTS[verdict] || VERDICTS.not_available;
  const tone = verdict === 'improved' ? 'bg-primary-fixed text-on-primary-fixed'
    : verdict === 'worsened' ? 'bg-error-container text-on-error-container'
      : 'bg-surface-container-high text-on-surface-variant';
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${tone}`}>
      <span className="material-symbols-outlined text-[14px]" aria-hidden="true">{v.icon}</span>{v.label}
    </span>
  );
}

function SimpleTable({ columns, rows, caption }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="text-left text-xs text-on-surface-variant border-b border-outline-variant/40">
            {columns.map((c) => <th key={c.key} scope="col" className="py-2 pr-3 font-semibold">{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.key ?? i} className={`border-b border-outline-variant/20 ${r.highlight ? 'bg-primary-fixed/30' : ''}`}>
              {columns.map((c) => <td key={c.key} className="py-2 pr-3 align-top">{c.format ? c.format(r[c.key], r) : (r[c.key] ?? '—')}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ConditionsSection({ result }) {
  return (
    <div>
      <SectionHeader icon="tune" title="Original and modified conditions" subtitle="Where each condition enters the optimisation pipeline." />
      <Card>
        <SimpleTable caption="Conditions" columns={[
          { key: 'label', label: 'Condition', format: (v, r) => <span className={r.changed ? 'font-bold text-primary' : ''}>{v}</span> },
          { key: 'baseline', label: 'Original' },
          { key: 'scenario', label: 'Scenario', format: (v, r) => <span className={r.changed ? 'font-bold' : ''}>{v}</span> },
          { key: 'enters', label: 'Enters at' },
          { key: 'detail', label: 'Detail', format: (v) => <span className="text-xs text-on-surface-variant">{v}</span> },
        ]} rows={result.conditions.map((c) => ({ ...c, key: c.id, highlight: c.changed }))} />
      </Card>
    </div>
  );
}

function PlanCard({ title, side, ranking, confidence, emphasis }) {
  return (
    <Card className={emphasis ? 'border-primary/60' : ''}>
      <div className="flex items-center justify-between mb-2">
        <h4 className="font-bold text-on-surface">{title}</h4>
        <span className="text-xs text-on-surface-variant">{ranking.recommendation}</span>
      </div>
      <ul className="space-y-1.5 mb-3">
        {side.crop_mix.map((c) => (
          <li key={c.crop} className="text-sm">
            <div className="flex justify-between"><span>{c.crop}</span><span className="font-semibold">{c.share_pct.toFixed(1)}%</span></div>
            <div className="h-1.5 rounded-full bg-surface-container-high mt-0.5">
              <div className="h-1.5 rounded-full" style={{ width: `${c.share_pct}%`, background: emphasis ? '#1f6b3a' : '#8f998e' }}></div>
            </div>
          </li>
        ))}
      </ul>
      <dl className="grid grid-cols-3 gap-2 text-xs">
        <div><dt className="text-on-surface-variant">TOPSIS closeness</dt><dd className="font-bold text-sm">{ranking.closeness.toFixed(3)}</dd></div>
        <div><dt className="text-on-surface-variant">Confidence</dt><dd className="font-bold text-sm">{confidence}%</dd></div>
        <div><dt className="text-on-surface-variant">Pareto plans</dt><dd className="font-bold text-sm">{ranking.pareto_plans}</dd></div>
      </dl>
      <p className="text-[11px] text-on-surface-variant mt-2">{ranking.trade_off}</p>
    </Card>
  );
}

export function RecommendationSection({ result }) {
  const { baseline, scenario, comparison } = result;
  return (
    <div>
      <SectionHeader icon="compare_arrows" title="Recommendation comparison"
        subtitle="Recommended plans from the first optimiser seed – the same run Run Optimization shows." />
      {!scenario.available ? (
        <Card><p className="text-sm text-on-error-container font-semibold">{scenario.reason}</p></Card>
      ) : (
        <div className="space-y-4">
          <div className="grid md:grid-cols-2 gap-4">
            <PlanCard title="Original recommendation" side={baseline} ranking={comparison.ranking.baseline} confidence={comparison.confidence.baseline_pct} />
            <PlanCard title="Simulated recommendation" side={scenario} ranking={comparison.ranking.scenario} confidence={comparison.confidence.scenario_pct} emphasis />
          </div>
          <ChartCard title="Crop plan" subtitle="Land share of each crop in the two recommended plans"
            table={{ columns: [{ key: 'crop', label: 'Crop' }, { key: 'baseline_share_pct', label: 'Original %' },
              { key: 'scenario_share_pct', label: 'Simulated %' }, { key: 'change_pp', label: 'Change (pp)' },
              { key: 'mean', label: `Mean over ${result.meta.runs_per_side} runs`, format: (_, r) => r.ensemble
                ? `${r.ensemble.baseline_mean_pct}% → ${r.ensemble.scenario_mean_pct}% (p ${r.ensemble.p_value ?? '—'})` : '—' }],
              rows: comparison.crop_shares }}>
            <GroupedBarChart categories={cropShareCategories(result)} series={SERIES} unit="%" digits={0} ariaLabel="Crop shares, original vs simulated" />
          </ChartCard>
          <ChartCard title="Confidence comparison" subtitle="Explanation-engine confidence components (0–100)"
            table={{ columns: [{ key: 'label', label: 'Component' }, { key: 'baseline', label: 'Original' }, { key: 'scenario', label: 'Simulated' }],
              rows: comparison.confidence.components }}>
            <GroupedBarChart categories={confidenceCategories(result)} series={SERIES} digits={0} min={0} ariaLabel="Confidence components" />
          </ChartCard>
        </div>
      )}
    </div>
  );
}

export function ImpactSection({ result }) {
  const impact = result.impact;
  if (!impact) return null;
  const metrics = impactMetrics(result);
  const perHa = impact.basis === 'per_ha';
  const objectiveMetrics = (perHa ? impact.per_ha : impact.totals);
  return (
    <div>
      <SectionHeader icon="monitoring" title="Impact summary" subtitle={impact.basis_note} />
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 mb-4">
        {metrics.map((m) => (
          <div key={m.id} className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4">
            <p className="text-xs text-on-surface-variant font-semibold uppercase tracking-wide">{OBJECTIVE_LABELS[m.id] || m.label}</p>
            <div className="flex flex-wrap items-center gap-2 mt-1">
              <p className="text-2xl font-bold text-on-surface">{formatPct(m.change_pct)}</p>
              <VerdictBadge verdict={m.verdict} />
            </div>
            <p className="text-xs text-on-surface-variant mt-1">{m.baselineText} → {m.scenarioText}</p>
            {m.p_value !== undefined && m.p_value !== null && <p className="text-[11px] text-outline mt-0.5">paired t-test p = {m.p_value}</p>}
          </div>
        ))}
      </div>
      <div className="space-y-4">
        <ChartCard title="Difference by metric" subtitle="Gray bars: within the optimiser's run-to-run variation"
          table={{ columns: [{ key: 'label', label: 'Metric' }, { key: 'change', label: 'Change', format: formatPct },
            { key: 'verdictLabel', label: 'Verdict' }], rows: deltaItems(result) }}>
          <DeltaBarChart items={deltaItems(result)} ariaLabel="Percentage change per metric" />
        </ChartCard>
        <ChartCard title="Yield, cost, water and environmental comparison"
          subtitle={`Indexed to the original mean = 100 · means of ${result.meta.runs_per_side} runs per side · whiskers show the range across runs`}
          table={{ columns: [{ key: 'label', label: 'Metric' }, { key: 'b', label: 'Original mean' }, { key: 'br', label: 'Original range' },
            { key: 's', label: 'Simulated mean' }, { key: 'sr', label: 'Simulated range' }, { key: 'rec', label: 'Recommended plans' }],
            rows: objectiveMetrics.map((m) => ({
              label: OBJECTIVE_LABELS[m.id], b: formatMetric(m.id, m.baseline, perHa), s: formatMetric(m.id, m.scenario, perHa),
              br: `${formatMetric(m.id, m.baseline_range?.[0], perHa)} – ${formatMetric(m.id, m.baseline_range?.[1], perHa)}`,
              sr: `${formatMetric(m.id, m.scenario_range?.[0], perHa)} – ${formatMetric(m.id, m.scenario_range?.[1], perHa)}`,
              rec: `${formatMetric(m.id, m.recommended?.baseline, perHa)} → ${formatMetric(m.id, m.recommended?.scenario, perHa)}`,
            })) }}>
          <GroupedBarChart categories={indexedCategories(result)} series={SERIES} digits={0} min={0}
            ariaLabel="Objectives indexed to the original mean" />
        </ChartCard>
      </div>
      <p className="text-xs text-on-surface-variant mt-3">{impact.method} {impact.profit.note}</p>
    </div>
  );
}

export function DecisionImpactSection({ result }) {
  return (
    <div>
      <SectionHeader icon="psychology" title="Decision impact" subtitle="Generated from the two runs' inputs and outputs." />
      <Statements items={result.decision_impact} empty="No impact statements." />
    </div>
  );
}

export function TradeOffSection({ result }) {
  const t = result.trade_offs;
  const col = (title, icon, list, render) => (
    <Card>
      <h4 className="font-bold text-sm flex items-center gap-1.5 mb-2">
        <span className="material-symbols-outlined text-[18px] text-primary" aria-hidden="true">{icon}</span>{title}
      </h4>
      {list.length ? <ul className="text-sm space-y-1">{list.map((m) => <li key={m.id ?? m}>{render(m)}</li>)}</ul>
        : <p className="text-sm text-on-surface-variant">None</p>}
    </Card>
  );
  return (
    <div>
      <SectionHeader icon="balance" title="Trade-off analysis" subtitle="What improved, what became worse and which constraints tightened." />
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        {col('Improved', 'trending_up', t.improved, (m) => `${m.label} ${formatPct(m.change_pct)}`)}
        {col('Worsened', 'trending_down', t.worsened, (m) => `${m.label} ${formatPct(m.change_pct)}`)}
        {col('Within search variation', 'blur_on', t.not_significant, (m) => `${m.label} ${formatPct(m.change_pct)}`)}
        {col('Harder constraints', 'lock', t.harder_constraints, (m) => m)}
      </div>
      <Card>
        <SimpleTable caption="Constraints" columns={[
          { key: 'label', label: 'Constraint' }, { key: 'baseline_status', label: 'Original', format: prettyStatus },
          { key: 'scenario_status', label: 'Scenario', format: prettyStatus },
          { key: 'became_harder', label: 'Harder?', format: (v) => (v ? <span className="font-bold text-on-error-container">Yes</span> : 'No') },
          { key: 'scenario_detail', label: 'Detail', format: (v) => <span className="text-xs text-on-surface-variant">{v || '—'}</span> },
        ]} rows={result.constraints.map((c) => ({ ...c, key: c.id, highlight: c.became_harder }))} />
      </Card>
    </div>
  );
}

export function OptimizationSection({ result }) {
  const opt = result.optimization;
  const radar = radarData(result);
  const contrib = contributionCategories(result);
  const fz = result.fuzzy_changes;
  const w = opt.weights;
  return (
    <div>
      <SectionHeader icon="hub" title="Optimization difference" subtitle={opt.seed_note} />
      <div className="grid lg:grid-cols-2 gap-4 mb-4">
        <Card>
          <h4 className="font-bold text-sm mb-2">TOPSIS weights</h4>
          <SimpleTable caption="TOPSIS weights" columns={[
            { key: 'label', label: 'Objective' }, { key: 'b', label: 'Original', format: (v) => v.toFixed(3) },
            { key: 's', label: 'Scenario', format: (v) => v.toFixed(3) },
          ]} rows={['yield', 'cost', 'water', 'env'].map((o) => ({ key: o, label: OBJECTIVE_LABELS[o], b: w.baseline[o], s: w.scenario[o],
            highlight: o === w.scenario_dominant }))} />
          <p className="text-xs text-on-surface-variant mt-2">
            Dominant weight: {OBJECTIVE_LABELS[w.baseline_dominant]} → {OBJECTIVE_LABELS[w.scenario_dominant]}.
            {opt.front_identical ? ' The Pareto front is identical on both sides; only the TOPSIS selection differs.'
              : ` Pareto plans found: ${opt.pareto.baseline.size} → ${opt.pareto.scenario.size}.`}
          </p>
        </Card>
        {radar && (
          <ChartCard title="Objective profile" subtitle={opt.common_scale.note}
            table={{ columns: [{ key: 'label', label: 'Objective' }, { key: 'b', label: 'Original' }, { key: 's', label: 'Simulated' }],
              rows: radar.axes.map((a) => ({ label: a.label, b: radar.series[0].values[a.key], s: radar.series[1].values[a.key] })) }}>
            <RadarChart axes={radar.axes} series={radar.series} ariaLabel="Objective profile radar" />
          </ChartCard>
        )}
      </div>
      {contrib.length > 0 && (
        <div className="mb-4">
          <ChartCard title="Objective contribution" subtitle="TOPSIS weight × goodness (0–1 within each plan's own Pareto set) for each recommended plan"
            table={{ columns: [{ key: 'label', label: 'Objective' }, { key: 'b', label: 'Original' }, { key: 's', label: 'Simulated' }],
              rows: contrib.map((c) => ({ label: c.label, b: c.values[0], s: c.values[1] })) }}>
            <GroupedBarChart categories={contrib} series={SERIES} digits={2} min={0} ariaLabel="Objective contributions" />
          </ChartCard>
        </div>
      )}
      {opt.decomposition && (
        <Card className="mb-4">
          <h4 className="font-bold text-sm mb-1">Why the plan changed: new conditions vs re-optimisation</h4>
          <p className="text-xs text-on-surface-variant mb-2">{opt.decomposition.note}</p>
          <SimpleTable caption="Decomposition" columns={[
            { key: 'label', label: 'Objective' },
            { key: 'condition_effect_pct', label: 'Same plan, new conditions', format: formatPct },
            { key: 'reoptimisation_effect_pct', label: 'Re-optimising', format: (v, r) => <span className="inline-flex flex-wrap items-center gap-2">{formatPct(v)}<VerdictBadge verdict={r.reoptimisation_effect_verdict} /></span> },
          ]} rows={opt.decomposition.rows.map((r) => ({ ...r, key: r.objective }))} />
        </Card>
      )}
      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <h4 className="font-bold text-sm mb-2">Fuzzy inputs and outputs</h4>
          <SimpleTable caption="Fuzzy inputs" columns={[
            { key: 'id', label: 'Input', format: (v) => ({ rainfall_dev: 'Rainfall deviation %', water_storage: 'Water storage %', soil_fert: 'Soil fertility index' })[v] },
            { key: 'baseline', label: 'Original', format: (v, r) => `${v} (${r.baseline_set})` },
            { key: 'scenario', label: 'Scenario', format: (v, r) => `${v} (${r.scenario_set})` },
          ]} rows={fz.inputs} />
          <SimpleTable caption="Fuzzy outputs" columns={[
            { key: 'label', label: 'Output' }, { key: 'baseline', label: 'Original' }, { key: 'scenario', label: 'Scenario' },
            { key: 'verdict', label: '', format: (v) => <VerdictBadge verdict={v} /> },
          ]} rows={fz.outputs} />
        </Card>
        <Card>
          <h4 className="font-bold text-sm mb-2">Fuzzy rules that changed ({fz.rules_changed.length})</h4>
          {fz.rules_changed.length ? (
            <SimpleTable caption="Rules changed" columns={[
              { key: 'rule', label: '#' }, { key: 'if', label: 'If', format: (v) => <span className="text-xs">{v}</span> },
              { key: 'then', label: 'Then', format: (v) => <span className="text-xs">{v}</span> },
              { key: 'strength', label: 'Strength', format: (_, r) => `${r.baseline_strength} → ${r.scenario_strength}` },
              { key: 'status', label: 'Status' },
            ]} rows={fz.rules_changed.map((r) => ({ ...r, key: r.rule }))} />
          ) : <p className="text-sm text-on-surface-variant">No rule's firing strength changed by 0.05 or more.</p>}
        </Card>
      </div>
    </div>
  );
}

export function CropEffectsSection({ result }) {
  const pct = (o) => (o.change_pct === null || o.change_pct === undefined ? '—' : formatPct(o.change_pct));
  return (
    <div>
      <SectionHeader icon="grass" title="Crop suitability changes"
        subtitle="Each crop grown alone at baseline inputs, per hectare, under each side's conditions (no search involved)." />
      <Card>
        <SimpleTable caption="Crop effects" columns={[
          { key: 'crop', label: 'Crop', format: (v, r) => <span className="font-semibold">{v}<span className="block text-[11px] text-on-surface-variant font-normal">Rain dependency {r.rainfall_dependency}</span></span> },
          { key: 'confidence', label: 'Fuzzy confidence', format: (o) => `${o.baseline.toFixed(3)} → ${o.scenario.toFixed(3)} (${pct(o)})` },
          { key: 'yield', label: 'Yield/ha', format: pct },
          { key: 'cost', label: 'Cost/ha', format: pct },
          { key: 'water', label: 'Irrigation/ha', format: pct },
          { key: 'share', label: 'Mean land share', format: (_, r) => (
            <span>{r.baseline_share_pct}% → {r.scenario_share_pct}%{r.share_shift_reliable ? ' ✓' : ''}</span>) },
        ]} rows={result.crop_effects.map((e) => ({ ...e, key: e.crop, highlight: e.share_shift_reliable }))} />
        <p className="text-[11px] text-on-surface-variant mt-2">✓ = share change of 5 pp or more with p &lt; {result.meta.significance_p} across {result.meta.runs_per_side} runs.</p>
      </Card>
    </div>
  );
}

export function HistoricalSection({ result }) {
  const h = result.historical;
  if (!h.available) {
    return (<div><SectionHeader icon="history_edu" title="Historical comparison" /><Card><p className="text-sm italic text-on-surface-variant">{NA}</p></Card></div>);
  }
  const rows = (h.scenario || h.baseline || []).map((r) => ({ ...r, key: r.crop }));
  return (
    <div>
      <SectionHeader icon="history_edu" title="Historical comparison"
        subtitle={`Simulated plan against the district's observed cropping pattern (${h.years.join(', ')}).`} />
      <div className="grid lg:grid-cols-3 gap-4">
        <Card>
          <p className="text-xs text-on-surface-variant font-semibold uppercase tracking-wide">Alignment with history</p>
          <p className="text-2xl font-bold mt-1">{h.alignment_pct.baseline}% → {h.alignment_pct.scenario ?? '—'}%</p>
          <p className="text-xs text-on-surface-variant mt-2">{h.method}</p>
        </Card>
        <Card className="lg:col-span-2">
          <SimpleTable caption="Historical comparison" columns={[
            { key: 'crop', label: 'Crop' }, { key: 'plan_share_pct', label: 'Simulated share', format: (v) => `${v}%` },
            { key: 'historical_share_pct', label: 'Historical share', format: (v) => `${v}%` },
            { key: 'expected_yield_t_ha', label: 'Expected yield (t/ha)', format: (v) => v ?? NA },
            { key: 'historical_yield_t_ha', label: 'Historical yield (t/ha)', format: (v, r) => (v === null ? NA : `${v.toFixed(2)} (${r.historical_yield_trend})`) },
          ]} rows={rows} />
        </Card>
      </div>
    </div>
  );
}
