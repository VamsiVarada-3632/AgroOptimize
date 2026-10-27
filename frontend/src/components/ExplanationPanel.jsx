import React, { useEffect, useState } from 'react';
import { describeApiError } from '../services/api';

/**
 * Renders an explanation returned by the backend explanation service
 * (GET /api/results/{run_id}/explanation or /api/comparison/{district}/explanation).
 *
 * This component only lays the JSON out. Every sentence shown comes from the
 * backend, which builds it from computed values; hovering an item shows the
 * evidence and source behind it.
 */

const SOURCE_LABELS = {
  fuzzy: 'Fuzzy model',
  nsga2: 'NSGA-II',
  topsis: 'TOPSIS',
  'nsga2+topsis': 'NSGA-II + TOPSIS',
  dataset: 'Dataset',
  'dataset + fuzzy': 'Dataset + fuzzy',
  'dataset + nsga2': 'Dataset + NSGA-II',
  constraint: 'Constraint',
  constraints: 'Constraints',
  'nsga2 constraint': 'NSGA-II constraint',
  'nsga2 repair': 'NSGA-II repair',
  request: 'Your inputs',
  'run metadata': 'Run record',
  'model limitation': 'Model limitation',
};

const STATUS_STYLES = {
  satisfied: { label: 'Satisfied', cls: 'bg-primary-fixed/40 text-on-primary-fixed', icon: 'check_circle' },
  moderate: { label: 'Moderate', cls: 'bg-secondary-fixed/50 text-on-secondary-fixed', icon: 'error' },
  risk: { label: 'At risk', cls: 'bg-error-container text-on-error-container', icon: 'warning' },
  violated: { label: 'Violated', cls: 'bg-error-container text-on-error-container', icon: 'cancel' },
  unknown: { label: 'Not recorded', cls: 'bg-surface-container-high text-on-surface-variant', icon: 'help' },
  not_applicable: { label: 'No limit set', cls: 'bg-surface-container-high text-on-surface-variant', icon: 'remove' },
};

const SEVERITY_STYLES = {
  high: 'bg-error-container text-on-error-container',
  medium: 'bg-secondary-fixed/50 text-on-secondary-fixed',
  low: 'bg-surface-container-high text-on-surface-variant',
};

function evidenceTooltip(item) {
  const source = SOURCE_LABELS[item.source] || item.source;
  const evidence = item.evidence && Object.keys(item.evidence).length ? `\nEvidence: ${JSON.stringify(item.evidence)}` : '';
  return `Source: ${source}${evidence}`;
}

function SourceBadge({ source }) {
  return (
    <span className="flex-shrink-0 text-[10px] uppercase tracking-wide font-semibold px-1.5 py-0.5 rounded bg-surface-container-high text-on-surface-variant">
      {SOURCE_LABELS[source] || source}
    </span>
  );
}

function Section({ icon, title, subtitle, children }) {
  return (
    <section className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4">
      <h4 className="font-headline-md text-[17px] font-bold text-on-surface flex items-center gap-2">
        <span className="material-symbols-outlined text-primary text-[20px]" aria-hidden="true">{icon}</span>
        {title}
      </h4>
      {subtitle && <p className="text-xs text-on-surface-variant mt-0.5">{subtitle}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function ItemList({ items, empty, badge }) {
  if (!items?.length) return <p className="text-sm text-on-surface-variant">{empty}</p>;
  return (
    <ul className="space-y-2">
      {items.map((item) => (
        <li key={item.id} title={evidenceTooltip(item)} className="p-3 rounded-lg bg-surface-container-low border border-outline-variant/20">
          <div className="flex items-start justify-between gap-2">
            <p className="font-semibold text-sm text-on-surface">{item.title}</p>
            <div className="flex items-center gap-1.5">
              {badge?.(item)}
              <SourceBadge source={item.source} />
            </div>
          </div>
          <p className="text-sm text-on-surface-variant mt-1 leading-relaxed">{item.detail}</p>
        </li>
      ))}
    </ul>
  );
}

function Bar({ value, max = 1, tone = 'bg-primary' }) {
  const pct = Math.max(0, Math.min(100, (value / (max || 1)) * 100));
  return (
    <div className="w-full h-2 bg-surface-variant rounded-full overflow-hidden" aria-hidden="true">
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }}></div>
    </div>
  );
}

function SummaryCard({ summary, confidence }) {
  const tone =
    summary.recommendation === 'Highly recommended' ? 'bg-primary text-on-primary'
      : summary.recommendation === 'Recommended' ? 'bg-primary-container text-on-primary'
        : 'bg-secondary-fixed text-on-secondary-fixed';
  return (
    <section className="rounded-xl border border-outline-variant/30 p-4 bg-surface-container-lowest">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs text-on-surface-variant uppercase tracking-wide font-semibold">
            {summary.location} · {summary.season} {summary.year}{summary.data_year_estimated ? ' (estimated data)' : ''} · preference “{summary.preference}”
          </p>
          <p className="font-headline-md text-headline-md font-bold text-on-surface mt-1">
            Rank #{summary.rank} of {summary.plans_compared} plans
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`px-3 py-1 rounded-full text-sm font-bold ${tone}`} title={summary.recommendation_rule}>{summary.recommendation}</span>
          <div className="text-right" title={confidence.method}>
            <p className="text-2xl font-bold text-primary leading-none">{summary.confidence_pct}%</p>
            <p className="text-[11px] text-on-surface-variant">confidence</p>
          </div>
        </div>
      </div>
      <div className="mt-4 space-y-2">
        {summary.crop_mix.map((c) => (
          <div key={c.crop} className="flex items-center gap-3 text-sm">
            <span className="w-28 truncate font-semibold">{c.crop}</span>
            <Bar value={c.share_pct} max={100} />
            <span className="w-28 text-right text-on-surface-variant">{c.share_pct.toFixed(1)}% · {c.area_ha.toFixed(2)} ha</span>
          </div>
        ))}
      </div>
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 text-sm">
        <div><dt className="text-on-surface-variant text-xs">Yield</dt><dd className="font-bold">{summary.per_ha.yield.toFixed(2)} t/ha</dd></div>
        <div><dt className="text-on-surface-variant text-xs">Cost</dt><dd className="font-bold">₹{Math.round(summary.per_ha.cost).toLocaleString()}/ha</dd></div>
        <div><dt className="text-on-surface-variant text-xs">Irrigation</dt><dd className="font-bold">{summary.per_ha.water.toFixed(2)} ML/ha</dd></div>
        <div><dt className="text-on-surface-variant text-xs">Env. impact</dt><dd className="font-bold">{summary.per_ha.env.toFixed(2)}/ha</dd></div>
      </dl>
    </section>
  );
}

function ObjectivesSection({ objectives }) {
  return (
    <Section icon="balance" title="How the objectives were balanced"
      subtitle="Goodness = position within this set of plans (1 = best). Gap share = how much each objective keeps the plan from the TOPSIS ideal.">
      <div className="space-y-3">
        {objectives.objectives.map((o) => (
          <div key={o.objective}>
            <div className="flex flex-wrap justify-between items-center gap-2 text-sm">
              <span className="font-semibold flex items-center gap-2">
                {o.label}
                {objectives.strongest === o.objective && <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary-fixed/50 font-bold">STRONGEST</span>}
                {objectives.compromise === o.objective && <span className="text-[10px] px-1.5 py-0.5 rounded bg-secondary-fixed/60 font-bold">MAIN COMPROMISE</span>}
              </span>
              <span className="text-on-surface-variant text-xs">
                {o.value_per_ha} {o.unit} · better than {o.better_than_pct_of_plans}% · weight {o.weight} · gap share {o.share_of_gap_to_ideal_pct}%
              </span>
            </div>
            <Bar value={o.goodness} />
          </div>
        ))}
      </div>
    </Section>
  );
}

function ConfidenceSection({ confidence }) {
  return (
    <Section icon="verified" title={`Confidence: ${confidence.overall_pct}%`} subtitle={confidence.method}>
      <div className="space-y-3">
        {confidence.components.map((c) => (
          <div key={c.id} title={c.detail}>
            <div className="flex justify-between text-sm">
              <span className="font-semibold">{c.label}</span>
              <span className="text-on-surface-variant">{c.score === null ? 'not available' : `${c.score}%`}</span>
            </div>
            {c.score !== null && <Bar value={c.score} max={100} tone={c.score >= 70 ? 'bg-primary' : c.score >= 40 ? 'bg-secondary' : 'bg-error'} />}
            <p className="text-xs text-on-surface-variant mt-1">{c.detail}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}

function HistoricalSection({ history }) {
  const rain = history.rainfall;
  return (
    <Section icon="history_edu" title="Historical context" subtitle={`Observed years: ${history.observed_years.join(', ') || 'none'}`}>
      <ul className="space-y-2 text-sm">
        {history.crops.map((c) => (
          <li key={c.crop} className="p-3 rounded-lg bg-surface-container-low" title={JSON.stringify(c)}>{c.detail}</li>
        ))}
      </ul>
      {rain.seasonal_total_mm_mean !== null && (
        <p className="text-xs text-on-surface-variant mt-3">
          Season rainfall: {rain.this_year_total_mm} mm this year ({rain.this_year_deviation_pct}% vs normal) against an observed mean of{' '}
          {rain.seasonal_total_mm_mean} mm (variation coefficient {rain.seasonal_total_mm_cv}).
        </p>
      )}
    </Section>
  );
}

function TimelineSection({ timeline }) {
  return (
    <Section icon="timeline" title="How this recommendation was produced">
      <ol className="relative pl-6 border-l-2 border-surface-variant space-y-4">
        {timeline.map((step) => (
          <li key={step.id} className="relative" title={evidenceTooltip(step)}>
            <span className="absolute -left-[31px] top-1 w-4 h-4 rounded-full bg-primary border-4 border-surface-container-lowest" aria-hidden="true"></span>
            <p className="text-sm font-semibold">{step.title}</p>
            <p className="text-sm text-on-surface-variant">{step.detail}</p>
          </li>
        ))}
      </ol>
    </Section>
  );
}

export function TopsisSection({ topsis }) {
  const p = topsis.plan;
  return (
    <Section icon="leaderboard" title={`TOPSIS score: ${p.closeness.toFixed(4)} (rank #${p.rank} of ${topsis.plans_ranked})`}
      subtitle={`Profile: ${topsis.label}. Weight → weighted value → share of the distance to the best plan.`}>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-on-surface-variant border-b border-outline-variant/40">
              <th scope="col" className="py-1.5 pr-3 font-semibold">Criterion</th>
              <th scope="col" className="py-1.5 pr-3 font-semibold">Weight</th>
              <th scope="col" className="py-1.5 pr-3 font-semibold">Normalised</th>
              <th scope="col" className="py-1.5 pr-3 font-semibold">Contribution</th>
              <th scope="col" className="py-1.5 pr-3 font-semibold">Share of gap to best</th>
            </tr>
          </thead>
          <tbody>
            {p.criteria.map((r) => (
              <tr key={r.criterion} className="border-b border-outline-variant/20">
                <td className="py-1.5 pr-3">{r.label}</td>
                <td className="py-1.5 pr-3">{(r.weight * 100).toFixed(1)}%</td>
                <td className="py-1.5 pr-3">{r.goodness.toFixed(2)}</td>
                <td className="py-1.5 pr-3">{r.weighted.toFixed(3)}</td>
                <td className="py-1.5 pr-3">{r.share_of_distance_to_ideal_pct.toFixed(0)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="mt-3 space-y-1 text-xs text-on-surface-variant list-disc pl-5">
        {topsis.versus_previous && <li>{topsis.versus_previous.summary}</li>}
        {topsis.versus_next && <li>{topsis.versus_next.summary}</li>}
        {topsis.rank_by_profile && (
          <li>Rank under each profile: {Object.entries(topsis.rank_by_profile).map(([k, v]) => `${PROFILE_LABELS[k] || k} #${v}`).join(', ')}.</li>
        )}
      </ul>
    </Section>
  );
}

const PROFILE_LABELS = { balanced: 'Balanced', profit: 'Profit', water: 'Water saving', sustainability: 'Sustainability', low_cost: 'Low cost' };

export function ExplanationPanel({ explanation }) {
  const e = explanation;
  return (
    <div className="space-y-4">
      <SummaryCard summary={e.summary} confidence={e.confidence} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Section icon="thumb_up" title="Why this plan was recommended">
          <ItemList items={e.reasons} empty="No individual strengths stand out beyond its TOPSIS rank." />
        </Section>
        <ObjectivesSection objectives={e.objectives} />
      </div>

      <Section icon="compare_arrows" title="Trade-offs accepted" subtitle="Each line compares this plan with the best plan in the set for one objective.">
        <ItemList items={e.trade_offs.items} empty="This plan is already the best in the set on every objective." />
        {e.trade_offs.marginal_rates.length > 0 && (
          <ul className="mt-3 space-y-1 text-xs text-on-surface-variant list-disc pl-5">
            {e.trade_offs.marginal_rates.map((r) => <li key={r.objective}>{r.detail}</li>)}
          </ul>
        )}
      </Section>

      <Section icon="rule" title="Constraint checks">
        <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {e.constraints.items.map((c) => {
            const st = STATUS_STYLES[c.status] || STATUS_STYLES.unknown;
            return (
              <li key={c.id} title={evidenceTooltip(c)} className="p-3 rounded-lg bg-surface-container-low">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-sm">{c.title}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-semibold flex items-center gap-1 ${st.cls}`}>
                    <span className="material-symbols-outlined text-[14px]" aria-hidden="true">{st.icon}</span>{st.label}
                  </span>
                </div>
                <p className="text-xs text-on-surface-variant mt-1">{c.detail}</p>
              </li>
            );
          })}
        </ul>
      </Section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Section icon="trending_up" title="Expected benefits" subtitle="Compared with the median plan in the same set.">
          <ItemList items={e.benefits} empty="No objective beats the set median." />
        </Section>
        <Section icon="report" title="Risks to watch">
          <ItemList items={e.risks} empty="No risks were detected from the available data."
            badge={(item) => <span className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${SEVERITY_STYLES[item.severity]}`}>{item.severity}</span>} />
        </Section>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ConfidenceSection confidence={e.confidence} />
        <HistoricalSection history={e.historical_context} />
      </div>

      <Section icon="lightbulb" title="Insights">
        <ItemList items={e.insights} empty="No insights available." />
      </Section>

      {e.alternatives.length > 0 && (
        <Section icon="alt_route" title="Compared with the next-best plan">
          <ItemList items={e.alternatives} empty="" />
        </Section>
      )}

      {e.topsis?.available && <TopsisSection topsis={e.topsis} />}

      <TimelineSection timeline={e.timeline} />

      <FuzzyRulesSection reasoning={e.fuzzy_reasoning} />

      {e.economics.available && (
        <details className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4">
          <summary className="cursor-pointer font-semibold text-sm">Indicative economics (unvalidated prices)</summary>
          <p className="text-xs text-on-surface-variant mt-2">{e.economics.caveat}</p>
          <p className="text-sm mt-2">
            Revenue ₹{Math.round(e.economics.indicative_revenue_rs).toLocaleString()} · input cost ₹{Math.round(e.economics.cost_rs).toLocaleString()} ·
            indicative margin ₹{Math.round(e.economics.indicative_profit_rs).toLocaleString()}
          </p>
        </details>
      )}

      <p className="text-[11px] text-on-surface-variant">
        Consistency check: yield and irrigation recomputed per crop match the optimiser's totals
        ({Object.values(e.consistency_checks).every((c) => c.consistent) ? 'all consistent' : 'MISMATCH – please report'}).
        Hover any item to see the numbers and the pipeline stage behind it.
      </p>
    </div>
  );
}

const OBJECTIVE_LABELS = { yield: 'Yield', cost: 'Cost', water: 'Irrigation water', env: 'Environmental impact' };

/**
 * Side-by-side view of several explanations (e.g. Plans A/B/C). Every cell
 * is read straight from each plan's explanation JSON.
 */
export function ExplanationComparison({ explanations }) {
  const keys = Object.keys(explanations);
  const row = (label, render) => (
    <tr className="border-t border-outline-variant/30 align-top">
      <th scope="row" className="py-2 pr-3 text-left text-xs text-on-surface-variant font-semibold w-40">{label}</th>
      {keys.map((k) => <td key={k} className="py-2 px-2 text-sm">{render(explanations[k])}</td>)}
    </tr>
  );
  const count = (e, sev) => e.risks.filter((r) => r.severity === sev).length;
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr>
            <th className="w-40"></th>
            {keys.map((k) => (
              <th key={k} className="py-2 px-2 text-left font-headline-md text-primary">{explanations[k].subject.name || `Plan ${k}`}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {row('Recommendation', (e) => <span className="font-semibold">{e.summary.recommendation}</span>)}
          {row('Confidence', (e) => <span className="font-bold text-primary">{e.summary.confidence_pct}%</span>)}
          {row('Chosen by', (e) => `#${e.summary.rank} under “${e.summary.preference}” (closeness ${e.summary.closeness})`)}
          {row('Crop mix', (e) => e.summary.crop_mix.map((c) => `${c.crop} ${c.share_pct.toFixed(0)}%`).join(', '))}
          {row('Yield / cost', (e) => `${e.summary.per_ha.yield.toFixed(2)} t/ha · ₹${Math.round(e.summary.per_ha.cost).toLocaleString()}/ha`)}
          {row('Water / impact', (e) => `${e.summary.per_ha.water.toFixed(2)} ML/ha · ${e.summary.per_ha.env.toFixed(2)}/ha`)}
          {row('Strongest objective', (e) => OBJECTIVE_LABELS[e.objectives.strongest])}
          {row('Main compromise', (e) => OBJECTIVE_LABELS[e.objectives.compromise])}
          {row('Top reasons', (e) => <ul className="list-disc pl-4">{e.reasons.slice(0, 3).map((r) => <li key={r.id}>{r.title}</li>)}</ul>)}
          {row('Risks (high / medium / low)', (e) => `${count(e, 'high')} / ${count(e, 'medium')} / ${count(e, 'low')}`)}
          {row('Top risk', (e) => e.risks[0]?.title || 'None detected')}
          {row('Weakest confidence factor', (e) => {
            const c = e.confidence.components.find((x) => x.id === e.confidence.weakest_component);
            return c ? `${c.label} (${c.score}%)` : '--';
          })}
          {row('Rank under each preference', (e) => {
            const ranks = e.insights.find((i) => i.id === 'preference-ranks')?.evidence.rank_by_preference || {};
            return Object.entries(ranks).map(([p, r]) => `${p} #${r}`).join(', ');
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Modal that loads and shows an explanation. `load` is a function returning
 * a Promise of the explanation JSON (e.g. () => api.getResultExplanation(id));
 * `render` optionally replaces the default ExplanationPanel view.
 */
export function ExplanationModal({ title, load, onClose, render }) {
  const [state, setState] = useState({ loading: true, data: null, error: '' });

  useEffect(() => {
    let cancelled = false;
    load()
      .then((data) => { if (!cancelled) setState({ loading: false, data, error: '' }); })
      .catch((err) => { if (!cancelled) setState({ loading: false, data: null, error: describeApiError(err) }); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onKey = (ev) => { if (ev.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-stretch sm:items-center justify-center bg-inverse-surface/40 backdrop-blur-sm sm:p-4 animate-[fadeIn_0.2s_ease-out]"
      role="dialog" aria-modal="true" aria-label={title} onClick={onClose}>
      <div className="bg-surface w-full max-w-5xl sm:rounded-xl shadow-ambient flex flex-col max-h-screen sm:max-h-[92vh]" onClick={(ev) => ev.stopPropagation()}>
        <div className="flex justify-between items-center px-5 py-4 border-b border-outline-variant/30">
          <h3 className="font-headline-md text-headline-md text-primary font-bold">{title}</h3>
          <button onClick={onClose} aria-label="Close explanation" className="cursor-pointer p-1 text-on-surface hover:text-primary">
            <span className="material-symbols-outlined" aria-hidden="true">close</span>
          </button>
        </div>
        <div className="overflow-y-auto p-5">
          {state.loading && (
            <div className="space-y-3" aria-busy="true">
              {[0, 1, 2].map((i) => <div key={i} className="h-24 bg-surface-container-high rounded-xl animate-pulse"></div>)}
            </div>
          )}
          {state.error && (
            <p className="text-sm bg-error-container/40 text-on-error-container px-4 py-3 rounded-lg">{state.error}</p>
          )}
          {state.data && (render ? render(state.data) : <ExplanationPanel explanation={state.data} />)}
        </div>
      </div>
    </div>
  );
}

export default ExplanationPanel;

const RULE_STATUS = {
  decisive: 'Decisive',
  masked: 'Masked',
};

/**
 * Fired fuzzy rules. With `reasoning.inference` (rule attribution from the
 * backend) rules are ranked by leave-one-out importance and show whether
 * they set an output term's cut (decisive), were outweighed by a stronger
 * rule for the same term (masked), and their share of each output.
 * Older payloads without `inference` fall back to the plain list.
 */
export function FuzzyRulesSection({ reasoning }) {
  const inference = reasoning?.inference;
  const fired = reasoning?.fired_rules || [];
  const byRule = inference ? Object.fromEntries(inference.rules.map((r) => [r.rule, r])) : {};
  const rows = inference ? inference.ranking.map((n) => byRule[n]) : fired;
  const pct = (v) => (v === undefined ? '–' : `${v}%`);
  return (
    <details className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4">
      <summary className="cursor-pointer font-semibold text-sm">
        Fuzzy rules that fired ({fired.length}){inference ? ` · ${inference.summary.decisive} decisive, ${inference.summary.masked} masked` : ''}
      </summary>
      {inference && (
        <p className="text-[11px] text-on-surface-variant mt-2">
          Yield confidence {inference.outputs.yield_conf.value} ({inference.outputs.yield_conf.term}, membership {inference.outputs.yield_conf.term_membership}) ·
          irrigation risk {inference.outputs.irrigation_risk.value} ({inference.outputs.irrigation_risk.term}, membership {inference.outputs.irrigation_risk.term_membership}).
          Ranked by how much each rule changes the outputs when removed. {inference.method}
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-xs mt-3">
          <thead>
            <tr className="text-left text-on-surface-variant">
              <th className="py-1 pr-2">Rule</th><th className="py-1 pr-2">If</th><th className="py-1 pr-2">Then</th><th className="py-1 pr-2">Strength</th>
              {inference && <><th className="py-1 pr-2">Status</th><th className="py-1 pr-2">Share of yield / risk</th><th className="py-1 pr-2">Limited by</th><th className="py-1">Importance</th></>}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.rule} className="border-t border-outline-variant/30 align-top">
                <td className="py-1 pr-2">#{r.rule}{r.scenario && <span className="block text-on-surface-variant">{r.scenario}</span>}</td>
                <td className="py-1 pr-2">{r.if}</td><td className="py-1 pr-2">{r.then}</td><td className="py-1 pr-2">{r.strength}</td>
                {inference && (
                  <>
                    <td className="py-1 pr-2">
                      {RULE_STATUS[r.status]}
                      {r.status === 'masked' && r.masked_by.length > 0 && <span className="block text-on-surface-variant">by #{r.masked_by.join(', #')}</span>}
                      {r.tied_with.length > 0 && <span className="block text-on-surface-variant">tied with #{r.tied_with.join(', #')}</span>}
                    </td>
                    <td className="py-1 pr-2">{pct(r.contribution_pct.yield_conf)} / {pct(r.contribution_pct.irrigation_risk)}</td>
                    <td className="py-1 pr-2">{r.limiting_condition ? `${r.limiting_condition.variable} is ${r.limiting_condition.term} (${r.limiting_condition.membership})` : '–'}</td>
                    <td className="py-1">{r.importance}</td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
