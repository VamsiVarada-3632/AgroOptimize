import React, { useEffect, useMemo, useState } from 'react';
import { api, describeApiError } from '../../services/api';
import BarChart from '../charts/BarChart';
import ChartCard from '../charts/ChartCard';
import GroupedBarChart from '../charts/GroupedBarChart';
import ProfileSelector from './ProfileSelector';
import {
  BALANCED_PERCENT, contributionRows, cropMixText, profileComparisonRows, rankChangeRows,
  signedRankChange, toFractions, validateCustomPercent, weightDifferenceRows, weightRows,
} from '../../utils/topsisView';

const perHa = (plan, key) => {
  const area = (plan.area_ha || []).reduce((a, b) => a + b, 0) || 1;
  return plan[key] / area;
};

/** Weight distribution of one ranking (horizontal bars, percent). */
export function WeightChart({ weights, title = 'Weight distribution' }) {
  const rows = weightRows(weights);
  return (
    <ChartCard title={title} subtitle="Share of the TOPSIS weight on each criterion."
      table={{ columns: [{ key: 'label', label: 'Criterion' }, { key: 'direction', label: 'Better when', format: (v) => (v === 'benefit' ? 'higher' : 'lower') },
        { key: 'percent', label: 'Weight', format: (v) => `${v.toFixed(1)}%` }], rows }}>
      <BarChart orientation="horizontal" unit="%" digits={1} ariaLabel={title}
        data={rows.map((r) => ({ key: r.key, label: r.label, value: r.percent, highlight: true }))} />
    </ChartCard>
  );
}

/** Weight -> contribution -> score of one plan. */
export function ContributionCard({ plan, idealBest }) {
  const rows = contributionRows(plan);
  return (
    <ChartCard
      title={`How plan #${plan.rank} scored ${plan.closeness.toFixed(4)}`}
      subtitle="Weighted value of each criterion (bar) against the best value in the set (mark). Closeness = distance to the worst ÷ (distance to the best + distance to the worst)."
      table={{ columns: [
        { key: 'label', label: 'Criterion' }, { key: 'weight', label: 'Weight' }, { key: 'value', label: 'Value' },
        { key: 'goodness', label: 'Normalised (0–1)' }, { key: 'weighted', label: 'Weighted' }, { key: 'gap', label: 'Share of gap to best' }], rows }}
    >
      <BarChart orientation="horizontal" digits={3} referenceLabel="Best in set" valueLabel="Weighted value" ariaLabel={`Contributions of plan ${plan.rank}`}
        data={plan.criteria.map((r) => ({
          key: r.criterion, label: r.label, value: r.weighted, reference: idealBest?.[r.criterion], highlight: true,
          detail: `weight ${(r.weight * 100).toFixed(1)}% × normalised ${r.goodness.toFixed(2)}; ${r.share_of_distance_to_ideal_pct.toFixed(0)}% of the gap to the best plan`,
        }))} />
      <p className="text-xs text-on-surface-variant mt-2">
        Distance to the best plan {plan.distance_to_ideal.toFixed(4)}, to the worst {plan.distance_to_anti_ideal.toFixed(4)}.
      </p>
    </ChartCard>
  );
}

/** Profiles side by side: best plan, rank changes and weight differences. */
export function ProfileComparison({ comparison }) {
  const rows = profileComparisonRows(comparison);
  const changes = rankChangeRows(comparison);
  const others = rows.filter((r) => !r.isReference);
  const [other, setOther] = useState(others[0]?.profile);
  const weightCats = weightDifferenceRows(comparison);
  const refLabel = rows.find((r) => r.isReference)?.label;
  const otherLabel = rows.find((r) => r.profile === other)?.label;

  return (
    <div className="space-y-4">
      <section className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4">
        <h4 className="font-headline-md text-[16px] font-bold text-on-surface">Best plan under each profile</h4>
        <p className="text-xs text-on-surface-variant mt-0.5 mb-3">
          Same {comparison.plans_compared} Pareto-optimal plans, ranked with each profile's weights. {comparison.distinct_best_plans} different
          plan{comparison.distinct_best_plans === 1 ? '' : 's'} come out on top.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-on-surface-variant border-b border-outline-variant/40">
                <th scope="col" className="py-1.5 pr-3 font-semibold">Profile</th>
                <th scope="col" className="py-1.5 pr-3 font-semibold">Best plan</th>
                <th scope="col" className="py-1.5 pr-3 font-semibold">TOPSIS score</th>
                <th scope="col" className="py-1.5 pr-3 font-semibold">Its rank under {refLabel}</th>
                <th scope="col" className="py-1.5 pr-3 font-semibold">{refLabel}'s #1 ranks</th>
                <th scope="col" className="py-1.5 pr-3 font-semibold" title="Kendall's tau between this profile's ranking and the selected one (1 = same order)">Agreement τ</th>
                <th scope="col" className="py-1.5 pr-3 font-semibold">Top-{comparison.top_n} overlap</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.profile} className={`border-b border-outline-variant/20 ${r.isReference ? 'font-semibold' : ''}`}>
                  <td className="py-1.5 pr-3">{r.label}{r.isReference ? ' (selected)' : ''}</td>
                  <td className="py-1.5 pr-3">{r.bestPlan}</td>
                  <td className="py-1.5 pr-3">{r.bestScore.toFixed(4)}</td>
                  <td className="py-1.5 pr-3">#{r.bestRankUnderReference}</td>
                  <td className="py-1.5 pr-3">#{r.referenceTopRank}</td>
                  <td className="py-1.5 pr-3">{r.tau === null || r.tau === undefined ? '–' : r.tau.toFixed(2)}</td>
                  <td className="py-1.5 pr-3">{r.overlap}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4">
        <h4 className="font-headline-md text-[16px] font-bold text-on-surface">Ranking changes</h4>
        <p className="text-xs text-on-surface-variant mt-0.5 mb-3">Where the selected profile's top {comparison.top_n} plans rank under the other profiles (↑ better, ↓ worse).</p>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-on-surface-variant border-b border-outline-variant/40">
                <th scope="col" className="py-1.5 pr-3 font-semibold">Plan</th>
                {rows.map((r) => <th key={r.profile} scope="col" className="py-1.5 pr-3 font-semibold">{r.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {changes.map((c) => (
                <tr key={c.plan} className="border-b border-outline-variant/20">
                  <td className="py-1.5 pr-3">{c.plan}</td>
                  {c.ranks.map((r) => (
                    <td key={r.profile} className="py-1.5 pr-3">
                      #{r.rank} <span className="text-on-surface-variant">{r.profile === comparison.reference ? '' : signedRankChange(r.change)}</span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {others.length > 0 && (
        <ChartCard
          title="Weight differences"
          subtitle={`${refLabel} (gray) against ${otherLabel} (green), percent of the total weight.`}
          actions={(
            <select aria-label="Profile to compare weights with" value={other} onChange={(e) => setOther(e.target.value)}
              className="text-xs border border-outline-variant rounded-full px-2 py-1 bg-surface-bright cursor-pointer">
              {others.map((r) => <option key={r.profile} value={r.profile}>{r.label}</option>)}
            </select>
          )}
          table={{ columns: [{ key: 'label', label: 'Criterion' },
            ...rows.map((r) => ({ key: r.profile, label: r.label, format: (_, row) => `${row.byProfile[r.profile].toFixed(1)}%` }))],
          rows: weightCats }}
        >
          <div className="max-w-2xl">
            <GroupedBarChart unit="%" digits={1} ariaLabel="Weight differences between profiles"
              series={[{ label: refLabel }, { label: otherLabel }]}
              categories={weightCats.map((c) => ({ key: c.key, label: c.label, values: [c.reference, c.byProfile[other] ?? 0] }))} />
          </div>
        </ChartCard>
      )}
    </div>
  );
}

/**
 * Dynamic TOPSIS panel for a saved run: switch profile (re-ranks the saved
 * Pareto front on the backend; NSGA-II is not re-run), see the weights,
 * the top plans with their TOPSIS scores, why #1 beats #2, and how the
 * five profiles compare.
 */
export default function TopsisPanel({ runId, initialProfile = 'balanced', initialCustomPercent }) {
  const [profile, setProfile] = useState(initialProfile);
  const [customPercent, setCustomPercent] = useState(initialCustomPercent || { ...BALANCED_PERCENT });
  const [applied, setApplied] = useState({ profile: initialProfile, customPercent: initialCustomPercent });
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('ranking');

  useEffect(() => {
    if (!runId) return undefined;
    let cancelled = false;
    setLoading(true);
    setError('');
    api.rerankResult(runId, {
      profile: applied.profile,
      customWeights: applied.profile === 'custom' ? toFractions(applied.customPercent) : undefined,
    })
      .then((res) => { if (!cancelled) setData(res); })
      .catch((err) => { if (!cancelled) setError(describeApiError(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [runId, applied]);

  const customCheck = validateCustomPercent(customPercent);
  const dirty = profile !== applied.profile || (profile === 'custom' && JSON.stringify(customPercent) !== JSON.stringify(applied.customPercent));
  const canApply = dirty && (profile !== 'custom' || customCheck.valid);
  const explanation = data?.explanation;
  const top = useMemo(() => (data?.plans || []).slice(0, 5), [data]);

  return (
    <section className="space-y-4" aria-label="TOPSIS ranking">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="font-headline-md text-headline-md text-on-surface font-bold">TOPSIS ranking</h3>
          <p className="text-xs text-on-surface-variant">
            Changing the profile re-ranks this run's {data?.plans_ranked ?? ''} Pareto-optimal plans with TOPSIS. The plans themselves, the
            fuzzy assessment and the optimiser's objectives stay exactly the same.
          </p>
        </div>
      </div>

      <ProfileSelector compact profile={profile} onProfileChange={setProfile} customPercent={customPercent} onCustomChange={setCustomPercent} />
      <div className="flex gap-2">
        <button type="button" disabled={!canApply || loading} onClick={() => setApplied({ profile, customPercent })}
          className="bg-primary text-on-primary text-sm font-bold px-4 py-2 rounded-lg disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed">
          {loading ? 'Ranking…' : 'Re-rank plans'}
        </button>
      </div>

      {error && (
        <div className="text-sm bg-error-container/40 text-on-error-container px-4 py-3 rounded-lg" role="alert">{error}</div>
      )}

      {data && (
        <>
          <div className="flex items-center justify-between flex-wrap gap-2">
            <p className="text-sm text-on-surface">
              <span className="font-semibold">Selected profile:</span> {data.topsis.label}
              {data.ranked_over === 'returned_plans' && (
                <span className="text-xs text-on-surface-variant"> · ranked over the {data.plans_ranked} plans this older run saved</span>
              )}
            </p>
            <div className="flex gap-1" role="tablist">
              {[['ranking', 'Ranking'], ['reasoning', 'Reasoning'], ['compare', 'Compare profiles']].map(([k, label]) => (
                <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                  className={`text-xs font-semibold rounded-full px-3 py-1 border cursor-pointer ${tab === k ? 'bg-primary text-on-primary border-primary' : 'border-outline-variant text-on-surface-variant hover:bg-surface-container-low'}`}>
                  {label}
                </button>
              ))}
            </div>
          </div>

          {tab === 'ranking' && (
            <div className="grid gap-4 lg:grid-cols-2">
              <WeightChart weights={data.topsis.weights} />
              <section className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4">
                <h4 className="font-headline-md text-[16px] font-bold text-on-surface mb-3">Top plans by TOPSIS score</h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-on-surface-variant border-b border-outline-variant/40">
                        <th scope="col" className="py-1.5 pr-2 font-semibold">#</th>
                        <th scope="col" className="py-1.5 pr-2 font-semibold">Crops</th>
                        <th scope="col" className="py-1.5 pr-2 font-semibold">TOPSIS score</th>
                        <th scope="col" className="py-1.5 pr-2 font-semibold">Yield t/ha</th>
                        <th scope="col" className="py-1.5 pr-2 font-semibold">Cost ₹/ha</th>
                      </tr>
                    </thead>
                    <tbody>
                      {top.map((p) => (
                        <tr key={p.rank} className="border-b border-outline-variant/20">
                          <td className="py-1.5 pr-2 font-semibold">{p.rank}</td>
                          <td className="py-1.5 pr-2">{cropMixText(p.crop_names.map((c, i) => ({ crop: c, share_pct: p.allocation_percent[i] })).filter((c) => c.share_pct >= 1).sort((a, b) => b.share_pct - a.share_pct).slice(0, 3))}</td>
                          <td className="py-1.5 pr-2">
                            <span className="inline-flex items-center gap-2">
                              <span className="inline-block h-2 rounded-full bg-primary" style={{ width: `${Math.max(4, p.composite_score * 60)}px` }} aria-hidden="true"></span>
                              {p.composite_score.toFixed(4)}
                            </span>
                          </td>
                          <td className="py-1.5 pr-2">{perHa(p, 'yield_tonnes').toFixed(2)}</td>
                          <td className="py-1.5 pr-2">{Math.round(perHa(p, 'cost_rs')).toLocaleString('en-IN')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
          )}

          {tab === 'reasoning' && explanation && (
            <div className="grid gap-4 lg:grid-cols-2 items-start">
              <section className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4">
                <h4 className="font-headline-md text-[16px] font-bold text-on-surface mb-2">Why the plans are in this order</h4>
                <ul className="space-y-1.5 text-sm text-on-surface">
                  {explanation.pairs.slice(0, 4).map((p) => <li key={`${p.rank_a}-${p.rank_b}`}>{p.summary}</li>)}
                </ul>
                <p className="text-xs text-on-surface-variant mt-2">
                  The numbers in brackets are each criterion's weighted advantage: weight × the difference in normalised (0–1) value.
                </p>
              </section>
              {explanation.plans[0] && <ContributionCard plan={explanation.plans[0]} idealBest={explanation.ideal_best} />}
            </div>
          )}

          {tab === 'compare' && data.comparison && <ProfileComparison key={data.comparison.reference} comparison={data.comparison} />}
          {tab === 'compare' && !data.comparison && <p className="text-sm text-on-surface-variant">No comparison for this run.</p>}
        </>
      )}
      {!data && loading && <p className="text-sm text-on-surface-variant">Ranking plans…</p>}
    </section>
  );
}
