import React, { useEffect, useState } from 'react';
import { api, DISTRICTS, PREFERENCES, SEASONS, describeApiError } from '../services/api';
import { downloadFile, slug } from '../utils/download';
import {
  FERTILIZER_OPTIONS, MARKET_OPTIONS, PRIORITY_LABELS, RAINFALL_OPTIONS, WATER_OPTIONS,
  buildRequest, defaultForm, formFromInputs, priorityLevel, simulationTitle,
} from '../utils/simulationView';
import {
  ConditionsSection, CropEffectsSection, DecisionImpactSection, HistoricalSection, ImpactSection,
  OptimizationSection, RecommendationSection, TradeOffSection,
} from '../components/simulation/SimulationSections';

const field = 'w-full h-11 px-3 rounded-lg border border-outline-variant bg-surface-bright text-on-surface outline-none focus:border-primary focus:ring-1 focus:ring-primary';
const labelCls = 'block text-xs text-on-surface-variant mb-1 font-semibold';

function Segmented({ label, value, options, onChange, format = (o) => o.label }) {
  return (
    <fieldset>
      <legend className={labelCls}>{label}</legend>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => {
          const v = typeof o === 'object' ? o.value : o;
          const active = v === value;
          return (
            <button type="button" key={v} onClick={() => onChange(v)} aria-pressed={active}
              className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold border cursor-pointer transition-colors ${active
                ? 'bg-primary text-on-primary border-primary' : 'bg-surface-bright text-on-surface border-outline-variant hover:border-primary'}`}>
              {format(o)}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

/**
 * Scenario Simulation & Decision Impact Analysis. The form builds a
 * baseline and a modified scenario; POST /api/simulations/run optimises both
 * through the full pipeline and returns the analysis this page renders.
 */
export default function SimulationView({ userLocation, landSizeHa = 5, onNavigate }) {
  const [form, setForm] = useState(() => defaultForm(DISTRICTS.includes(userLocation) ? userLocation : DISTRICTS[0], landSizeHa));
  const [years, setYears] = useState([]);
  const [run, setRun] = useState({ loading: false, error: '', result: null, saved: null });
  const [saved, setSaved] = useState({ loading: true, items: [], error: '' });
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  useEffect(() => {
    let cancelled = false;
    api.getCatalog().then((c) => { if (!cancelled) setYears(c.years || []); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const refreshSaved = () => {
    api.listSimulations()
      .then((items) => setSaved({ loading: false, items, error: '' }))
      .catch((err) => setSaved({ loading: false, items: [], error: describeApiError(err) }));
  };
  useEffect(refreshSaved, []);

  const onRun = async (e) => {
    e.preventDefault();
    setRun({ loading: true, error: '', result: null, saved: null });
    try {
      const { base, scenario } = buildRequest(form);
      const result = await api.runSimulation(base, scenario);
      setRun({ loading: false, error: '', result, saved: null });
      setName(simulationTitle(result));
    } catch (err) {
      setRun({ loading: false, error: describeApiError(err), result: null, saved: null });
    }
  };

  const onSave = async () => {
    if (!run.result?.token) return;
    setSaving(true);
    try {
      const summary = await api.saveSimulation(run.result.token, name.trim());
      setRun((r) => ({ ...r, saved: summary }));
      refreshSaved();
    } catch (err) {
      setRun((r) => ({ ...r, error: describeApiError(err) }));
    } finally {
      setSaving(false);
    }
  };

  const onOpen = async (id) => {
    setRun({ loading: true, error: '', result: null, saved: null });
    try {
      const record = await api.getSimulation(id);
      setForm(formFromInputs(record.inputs, form.location));
      setName(record.name || '');
      setRun({ loading: false, error: '', result: record.result, saved: record });
    } catch (err) {
      setRun({ loading: false, error: describeApiError(err), result: null, saved: null });
    }
  };

  const onDelete = async (id) => {
    try {
      await api.deleteSimulation(id);
      refreshSaved();
    } catch (err) {
      setSaved((s) => ({ ...s, error: describeApiError(err) }));
    }
  };

  const fileBase = run.result
    ? `agrooptimize-simulation-${slug(run.result.inputs.base.location)}-${slug(run.result.inputs.base.season)}` : '';

  // The report builder pulls in react-dom/server, so it is loaded only when
  // a report is actually exported.
  const onExportReport = async () => {
    const { simulationReportHtml } = await import('../utils/simulationReport');
    downloadFile(`${fileBase}-report.html`,
      simulationReportHtml(run.result, { name: run.saved?.name || name, savedAt: run.saved?.saved_at }), 'text/html;charset=utf-8');
  };

  const result = run.result;


  return (
    <div className="animate-[fadeIn_0.2s_ease-out] space-y-6">
      <header>
        <h2 className="font-headline-lg text-headline-lg-mobile md:text-headline-lg text-primary font-bold">Scenario Simulation</h2>
        <p className="text-on-surface-variant mt-1 max-w-3xl">
          Change rainfall, water, input costs, prices, land, budget or priorities and see how the optimised recommendation responds.
          Both the original and the modified conditions run through the full pipeline – preprocessing, fuzzy logic, NSGA-II and TOPSIS.
        </p>
      </header>

      <div className="grid xl:grid-cols-[360px_1fr] gap-6 items-start">
        <aside className="space-y-4 xl:sticky xl:top-4">
          <form onSubmit={onRun} className="bg-surface-container-lowest rounded-xl border border-outline-variant/20 shadow-soft p-5 space-y-4">
            <h3 className="font-bold text-on-surface flex items-center gap-2">
              <span className="material-symbols-outlined text-primary" aria-hidden="true">agriculture</span>Original conditions
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <label className="col-span-2"><span className={labelCls}>District</span>
                <select value={form.location} onChange={(e) => set({ location: e.target.value })} className={`${field} cursor-pointer`}>
                  {DISTRICTS.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </label>
              <label><span className={labelCls}>Season</span>
                <select value={form.season} onChange={(e) => set({ season: e.target.value })} className={`${field} cursor-pointer`}>
                  {SEASONS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
              <label><span className={labelCls}>Year</span>
                <select value={form.year} onChange={(e) => set({ year: e.target.value })} className={`${field} cursor-pointer`}>
                  <option value="">Latest available</option>
                  {years.map((y) => <option key={y} value={y}>{y}</option>)}
                </select>
              </label>
              <label><span className={labelCls}>Land (ha)</span>
                <input type="number" min="0.5" step="0.5" required value={form.total_land_ha}
                  onChange={(e) => set({ total_land_ha: e.target.value })} className={field} />
              </label>
              <label><span className={labelCls}>Budget (₹)</span>
                <input type="number" min="1" placeholder="No limit" value={form.budget_rs}
                  onChange={(e) => set({ budget_rs: e.target.value })} className={field} />
              </label>
              <label className="col-span-2"><span className={labelCls}>Optimization preference</span>
                <select value={form.preference} onChange={(e) => set({ preference: e.target.value })} className={`${field} cursor-pointer`}>
                  {PREFERENCES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </label>
            </div>

            <h3 className="font-bold text-on-surface flex items-center gap-2 pt-2 border-t border-outline-variant/30">
              <span className="material-symbols-outlined text-primary" aria-hidden="true">science</span>Scenario
            </h3>
            <Segmented label="Rainfall" value={form.rainfall_change_pct} options={RAINFALL_OPTIONS}
              onChange={(v) => set({ rainfall_change_pct: v })} format={(o) => (o === 0 ? 'Current' : `${o > 0 ? '+' : ''}${o}%`)} />
            <Segmented label="Water availability" value={form.water_availability} options={WATER_OPTIONS}
              onChange={(v) => set({ water_availability: v })} />
            <Segmented label="Fertiliser cost" value={form.fertilizer_cost_change_pct} options={FERTILIZER_OPTIONS}
              onChange={(v) => set({ fertilizer_cost_change_pct: v })} format={(o) => (o === 0 ? 'Current' : `${o > 0 ? '+' : ''}${o}%`)} />
            <Segmented label="Market price" value={form.market_price} options={MARKET_OPTIONS} onChange={(v) => set({ market_price: v })} />
            <div className="grid grid-cols-2 gap-3">
              <label><span className={labelCls}>Scenario land (ha)</span>
                <input type="number" min="0.5" step="0.5" placeholder="Same" value={form.scenario_land_ha}
                  onChange={(e) => set({ scenario_land_ha: e.target.value })} className={field} />
              </label>
              <label><span className={labelCls}>Scenario budget (₹)</span>
                <input type="number" min="1" placeholder="Same" value={form.scenario_budget_rs}
                  onChange={(e) => set({ scenario_budget_rs: e.target.value })} className={field} />
              </label>
            </div>

            <div className="pt-2 border-t border-outline-variant/30">
              <label className="flex items-center gap-2 text-sm font-semibold cursor-pointer">
                <input type="checkbox" checked={form.use_priorities} onChange={(e) => set({ use_priorities: e.target.checked })}
                  className="w-4 h-4 accent-[#1f6b3a]" />
                Set custom priorities
              </label>
              <p className="text-[11px] text-on-surface-variant mt-1">Replaces the preference's TOPSIS weights; weights are the sliders scaled to sum to 1.</p>
              {form.use_priorities && (
                <div className="space-y-3 mt-3">
                  {Object.keys(PRIORITY_LABELS).map((k) => (
                    <label key={k} className="block">
                      <span className="flex justify-between text-xs font-semibold text-on-surface-variant">
                        <span>{PRIORITY_LABELS[k]}</span><span>{priorityLevel(form.priorities[k])} · {form.priorities[k]}</span>
                      </span>
                      <input type="range" min="0" max="100" step="5" value={form.priorities[k]} className="w-full accent-[#1f6b3a]"
                        onChange={(e) => set({ priorities: { ...form.priorities, [k]: Number(e.target.value) } })} />
                    </label>
                  ))}
                </div>
              )}
            </div>

            <button type="submit" disabled={run.loading}
              className="w-full bg-primary text-on-primary font-bold py-3 rounded-lg hover:opacity-90 transition-opacity shadow-sm cursor-pointer disabled:opacity-50 flex items-center justify-center gap-2">
              <span className="material-symbols-outlined" aria-hidden="true">play_arrow</span>
              {run.loading ? 'Running…' : 'Run simulation'}
            </button>
          </form>

          <section className="bg-surface-container-lowest rounded-xl border border-outline-variant/20 p-5">
            <h3 className="font-bold text-on-surface flex items-center gap-2 mb-2">
              <span className="material-symbols-outlined text-primary" aria-hidden="true">bookmarks</span>Saved scenarios
            </h3>
            {saved.loading && <div className="h-12 bg-surface-container-high rounded-lg animate-pulse"></div>}
            {saved.error && <p className="text-xs text-on-error-container">{saved.error}</p>}
            {!saved.loading && !saved.items.length && !saved.error && <p className="text-sm text-on-surface-variant">No saved scenarios yet.</p>}
            <ul className="space-y-2">
              {saved.items.map((s) => (
                <li key={s.simulation_id} className="flex items-start gap-2 p-2 rounded-lg hover:bg-surface-container-low">
                  <button onClick={() => onOpen(s.simulation_id)} className="flex-1 text-left cursor-pointer">
                    <p className="text-sm font-semibold text-on-surface">{s.name}</p>
                    <p className="text-[11px] text-on-surface-variant">{s.location} · {s.season} · {new Date(s.saved_at).toLocaleString()}</p>
                  </button>
                  <button onClick={() => onDelete(s.simulation_id)} aria-label={`Delete ${s.name}`}
                    className="p-1 text-on-surface-variant hover:text-error cursor-pointer">
                    <span className="material-symbols-outlined text-[18px]" aria-hidden="true">delete</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </aside>

        <div className="space-y-8 min-w-0">
          {!result && !run.loading && !run.error && (
            <div className="text-center py-20 bg-surface-container-lowest rounded-xl border border-dashed border-outline-variant/40">
              <span className="material-symbols-outlined text-5xl text-outline" aria-hidden="true">science</span>
              <p className="text-on-surface-variant mt-2 max-w-md mx-auto">
                Set the original conditions and a scenario, then run the simulation. With no changes, the scenario reproduces the original recommendation exactly.
              </p>
            </div>
          )}

          {run.loading && (
            <div className="space-y-4" aria-busy="true">
              <div className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-5 flex items-center gap-3">
                <span className="material-symbols-outlined animate-spin text-primary" aria-hidden="true">progress_activity</span>
                <p className="text-sm text-on-surface-variant">
                  Optimising the original and the modified conditions with the same five seeds (preprocessing → fuzzy → NSGA-II → TOPSIS → explanation). This takes a few seconds.
                </p>
              </div>
              <div className="h-40 bg-surface-container-high rounded-xl animate-pulse"></div>
              <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">{[0, 1, 2].map((i) => <div key={i} className="h-24 bg-surface-container-high rounded-xl animate-pulse"></div>)}</div>
            </div>
          )}

          {run.error && (
            <div className="bg-error-container/40 text-on-error-container px-4 py-3 rounded-lg flex items-center gap-2 text-sm" role="alert">
              <span className="material-symbols-outlined" aria-hidden="true">error</span>{run.error}
            </div>
          )}

          {result && (
            <>
              <section className="bg-primary text-on-primary rounded-xl p-6 shadow-ambient">
                <p className="text-xs uppercase tracking-wide font-semibold opacity-80">
                  Scenario summary · {result.inputs.base.location} {result.inputs.base.season} · data year {result.summary.year}
                  {result.summary.data_year_estimated ? ' (estimated)' : ''}
                </p>
                <ul className="mt-2 space-y-1 leading-relaxed">
                  {result.summary.sentences.map((s) => <li key={s}>{s}</li>)}
                </ul>
                <p className="text-xs opacity-80 mt-3">
                  {result.meta.runs_per_side} optimiser runs per side · {result.meta.seconds}s · computed live
                </p>
              </section>

              <nav aria-label="Simulation actions" className="flex flex-wrap items-center gap-2">
                {run.saved ? (
                  <span className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary-fixed text-on-primary-fixed text-sm font-semibold">
                    <span className="material-symbols-outlined text-[18px]" aria-hidden="true">bookmark_added</span>Saved as “{run.saved.name}”
                  </span>
                ) : (
                  <>
                    <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} aria-label="Scenario name"
                      className="h-10 px-3 rounded-full border border-outline-variant bg-surface-bright text-sm min-w-0 flex-1 sm:flex-none sm:w-72" />
                    <button onClick={onSave} disabled={saving || !result.token}
                      className="flex items-center gap-2 px-4 py-2 rounded-full bg-primary text-on-primary text-sm font-semibold cursor-pointer disabled:opacity-50">
                      <span className="material-symbols-outlined text-[18px]" aria-hidden="true">bookmark_add</span>{saving ? 'Saving…' : 'Save scenario'}
                    </button>
                  </>
                )}
                <button onClick={onExportReport}
                  className="flex items-center gap-2 px-4 py-2 rounded-full border border-outline-variant bg-surface-container-lowest text-sm font-semibold hover:border-primary hover:text-primary cursor-pointer">
                  <span className="material-symbols-outlined text-[18px]" aria-hidden="true">description</span>Export report
                </button>
                <button onClick={() => downloadFile(`${fileBase}.json`, JSON.stringify(result, null, 2), 'application/json')}
                  className="flex items-center gap-2 px-4 py-2 rounded-full border border-outline-variant bg-surface-container-lowest text-sm font-semibold hover:border-primary hover:text-primary cursor-pointer">
                  <span className="material-symbols-outlined text-[18px]" aria-hidden="true">data_object</span>Export JSON
                </button>
                <button onClick={() => onNavigate('district-intelligence')}
                  className="flex items-center gap-2 px-4 py-2 rounded-full border border-outline-variant bg-surface-container-lowest text-sm font-semibold hover:border-primary hover:text-primary cursor-pointer">
                  <span className="material-symbols-outlined text-[18px]" aria-hidden="true">travel_explore</span>District profile
                </button>
              </nav>

              <RecommendationSection result={result} />
              <ImpactSection result={result} />
              <DecisionImpactSection result={result} />
              <TradeOffSection result={result} />
              <OptimizationSection result={result} />
              <CropEffectsSection result={result} />
              <HistoricalSection result={result} />
              <ConditionsSection result={result} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
