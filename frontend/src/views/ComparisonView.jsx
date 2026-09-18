import React, { useState, useMemo, useEffect } from 'react';
import { api } from '../services/api';
import DataSourceNotice from '../components/DataSourceNotice';

const PLAN_COLORS = ['bg-primary-fixed text-on-primary-fixed', 'bg-secondary-fixed text-on-secondary-fixed', 'bg-tertiary-fixed text-on-tertiary-fixed'];

// Adapts GET /api/comparison/{district}'s `plans` object (backend field
// names: yield_val, cost, radar_scores.cost_eff, etc.) onto the shape this
// view renders. Returns null if the response is missing/incomplete --
// there is no synthetic fallback data anymore.
function adaptComparisonPlans(apiPlans) {
  const out = {};
  for (const key of ['A', 'B', 'C']) {
    const p = apiPlans?.[key];
    if (!p) continue;
    const topCrop = p.allocations?.[0]?.crop || p.crops?.split(',')[0]?.trim() || 'the primary crop';
    out[key] = {
      name: p.name,
      crops: p.crops,
      yieldVal: p.yield_val,
      cost: p.cost,
      impact: `${Math.max(1, Math.round(p.radar_scores.land / 5))}/20`,
      water: p.water === 'High usage' ? 'High' : p.water,
      recommended: p.recommended,
      allocations: (p.allocations || []).map((a, i) => ({
        crop: a.crop,
        letter: a.crop.charAt(0).toUpperCase(),
        color: PLAN_COLORS[i % PLAN_COLORS.length],
        plots: a.plots,
        pct: a.pct,
        ha: a.ha,
      })),
      // The optimizer doesn't model a day-by-day irrigation calendar, so
      // this stays a generic 2-step template -- but it's keyed off this
      // plan's real top crop rather than fabricated crop-specific detail.
      schedule: [
        { time: 'Week 1-2 (Upcoming)', desc: `Land preparation & ${topCrop} sowing`, details: 'Based on this plan’s optimized crop mix', active: true },
        { time: 'Week 3-4', desc: 'First irrigation & fertilizer application', details: 'Per this plan’s irrigation/fertilizer multipliers', active: false },
      ],
      radarScores: {
        yield: p.radar_scores.yield,
        costEff: p.radar_scores.cost_eff,
        water: p.radar_scores.water,
        land: p.radar_scores.land,
        risk: p.radar_scores.risk,
        market: p.radar_scores.market,
      },
    };
  }
  return Object.keys(out).length === 3 ? out : null;
}

export default function ComparisonView({ activePlanId = 'A', onSelectPlan, userLocation, onNavigate }) {
  const [selectedPlanId, setSelectedPlanId] = useState(activePlanId);
  const [adjustWeightsOpen, setAdjustWeightsOpen] = useState(false);

  const [apiComparison, setApiComparison] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fetchFailed, setFetchFailed] = useState(false);

  const [weights, setWeights] = useState({ yield: 50, cost: 50, water: 50 });

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.getComparison(userLocation)
      .then((data) => {
        if (cancelled) return;
        setApiComparison(data);
        setFetchFailed(false);
      })
      .catch(() => {
        if (cancelled) return;
        setApiComparison(null);
        setFetchFailed(true);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [userLocation]);

  const plans = useMemo(() => adaptComparisonPlans(apiComparison?.plans), [apiComparison]);
  const hasData = plans !== null;
  const selectedPlan = hasData ? (plans[selectedPlanId] || plans.A) : null;

  const recommendedPlanId = useMemo(() => {
    if (!hasData) return null;
    const scores = Object.keys(plans).map((id) => {
      const plan = plans[id];
      const score =
        (weights.yield / 100) * plan.radarScores.yield +
        (weights.cost / 100) * plan.radarScores.costEff +
        (weights.water / 100) * plan.radarScores.water;
      return { id, score };
    });
    return scores.sort((a, b) => b.score - a.score)[0].id;
  }, [weights, plans, hasData]);

  const getRadarPolygonPoints = (scores) => {
    const points = [];
    const keys = ['yield', 'costEff', 'water', 'land', 'risk', 'market'];
    const angles = [0, Math.PI / 3, 2 * Math.PI / 3, Math.PI, 4 * Math.PI / 3, 5 * Math.PI / 3];

    keys.forEach((key, idx) => {
      const score = scores[key];
      const r = score;
      const angle = angles[idx] - Math.PI / 2;
      const x = Math.round(r * Math.cos(angle));
      const y = Math.round(r * Math.sin(angle));
      points.push(`${x},${y}`);
    });
    return points.join(' ');
  };

  return (
    <div className="flex flex-col gap-6 animate-[fadeIn_0.2s_ease-out]">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="font-headline-lg text-headline-lg-mobile md:text-headline-lg text-on-background font-bold">Optimization Plans</h2>
          <p className="text-on-surface-variant mt-1 flex items-center gap-2 flex-wrap">
            Review and select the most balanced plan for the upcoming season
            {apiComparison?.total_land_ha ? ` (sized for ${apiComparison.total_land_ha} ha).` : '.'}
          </p>
        </div>
        <div className="flex gap-3 w-full md:w-auto">
          <button
            onClick={() => setAdjustWeightsOpen(true)}
            disabled={!hasData}
            className="flex-1 md:flex-none flex items-center justify-center gap-2 border border-outline text-on-surface px-6 py-3 rounded-full font-label-md text-label-md hover:bg-surface-container-high transition-colors min-h-[48px] cursor-pointer font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <span className="material-symbols-outlined">tune</span>
            Adjust Weights
          </button>
          <button
            onClick={() => alert("Downloading multi-objective reports...")}
            disabled={!hasData}
            className="flex-1 md:flex-none flex items-center justify-center gap-2 bg-primary text-on-primary px-6 py-3 rounded-full font-label-md text-label-md hover:opacity-90 transition-opacity shadow-ambient min-h-[48px] cursor-pointer font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <span className="material-symbols-outlined">download</span>
            Export Report
          </button>
        </div>
      </div>

      {onNavigate && (
        <DataSourceNotice
          location={userLocation}
          variant="live"
          onRunOptimization={() => onNavigate('run-optimization')}
        />
      )}

      {loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="h-80 bg-surface-container-lowest rounded-xl border border-outline-variant/30 animate-pulse lg:col-span-1"></div>
          <div className="h-80 bg-surface-container-lowest rounded-xl border border-outline-variant/30 animate-pulse lg:col-span-2"></div>
        </div>
      ) : !hasData ? (
        <div className="text-center py-20 bg-surface-container-lowest rounded-xl border border-dashed border-outline-variant/30">
          <span className="material-symbols-outlined text-5xl text-outline mb-2">compare</span>
          <p className="font-body-lg text-on-surface-variant">
            {fetchFailed ? "Couldn't reach the backend. Confirm uvicorn is running on port 8000." : 'No comparison data available for this district yet.'}
          </p>
        </div>
      ) : (
      <>
      {/* Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Radar Chart Card */}
        <div className="bg-surface-container-lowest rounded-xl p-6 shadow-ambient lg:col-span-1 flex flex-col border border-outline-variant/30">
          <h3 className="font-headline-md text-headline-md font-bold mb-1">Performance Overview</h3>
          <p className="text-on-surface-variant font-label-sm text-label-sm mb-6">Multi-objective balance analysis of optimization plans.</p>

          <div className="flex-grow flex items-center justify-center min-h-[250px] relative">
            <svg viewBox="-120 -120 240 240" className="w-full h-full max-w-[240px] max-h-[240px] overflow-visible">
              <polygon fill="none" points="0,-100 86.6,-50 86.6,50 0,100 -86.6,50 -86.6,-50" stroke="#e4e2e2" strokeWidth="1"></polygon>
              <polygon fill="none" points="0,-75 64.95,-37.5 64.95,37.5 0,75 -64.95,37.5 -64.95,-37.5" stroke="#e4e2e2" strokeWidth="1"></polygon>
              <polygon fill="none" points="0,-50 43.3,-25 43.3,25 0,50 -43.3,25 -43.3,-25" stroke="#e4e2e2" strokeWidth="1"></polygon>

              <line stroke="#bfc9bd" strokeWidth="1" x1="0" y1="0" x2="0" y2="-100"></line>
              <line stroke="#bfc9bd" strokeWidth="1" x1="0" y1="0" x2="86.6" y2="-50"></line>
              <line stroke="#bfc9bd" strokeWidth="1" x1="0" y1="0" x2="86.6" y2="50"></line>
              <line stroke="#bfc9bd" strokeWidth="1" x1="0" y1="0" x2="0" y2="100"></line>
              <line stroke="#bfc9bd" strokeWidth="1" x1="0" y1="0" x2="-86.6" y2="50"></line>
              <line stroke="#bfc9bd" strokeWidth="1" x1="0" y1="0" x2="-86.6" y2="-50"></line>

              <text fill="#404940" fontSize="9" textAnchor="middle" x="0" y="-108" className="font-semibold">Yield</text>
              <text fill="#404940" fontSize="9" textAnchor="start" x="92" y="-52" className="font-semibold">Cost Eff.</text>
              <text fill="#404940" fontSize="9" textAnchor="start" x="92" y="55" className="font-semibold">Water</text>
              <text fill="#404940" fontSize="9" textAnchor="middle" x="0" y="112" className="font-semibold">Land</text>
              <text fill="#404940" fontSize="9" textAnchor="end" x="-92" y="55" className="font-semibold">Risk</text>
              <text fill="#404940" fontSize="9" textAnchor="end" x="-92" y="-52" className="font-semibold">Market</text>

              <polygon
                fill="rgba(31, 107, 58, 0.4)"
                stroke="#1f6b3a"
                strokeWidth="2"
                points={getRadarPolygonPoints(selectedPlan.radarScores)}
                className="transition-all duration-300"
              />

              {selectedPlanId !== recommendedPlanId && (
                <polygon
                  fill="rgba(121, 89, 0, 0.15)"
                  stroke="#795900"
                  strokeWidth="1.5"
                  strokeDasharray="4"
                  points={getRadarPolygonPoints(plans[recommendedPlanId].radarScores)}
                  className="transition-all duration-300"
                />
              )}
            </svg>
          </div>

          <div className="mt-4 flex flex-wrap gap-4 justify-center">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-primary"></div>
              <span className="font-label-sm text-label-sm text-on-surface">Selected ({selectedPlanId})</span>
            </div>
            {selectedPlanId !== recommendedPlanId && (
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full border border-secondary border-dashed bg-transparent"></div>
                <span className="font-label-sm text-label-sm text-on-surface">Weighted Rec ({recommendedPlanId})</span>
              </div>
            )}
          </div>
        </div>

        {/* Comparison Table Card */}
        <div className="bg-surface-container-lowest rounded-xl shadow-ambient lg:col-span-2 overflow-hidden flex flex-col border border-outline-variant/30">
          <div className="p-6 border-b border-outline-variant/30 flex justify-between items-center bg-surface-container-lowest">
            <h3 className="font-headline-md text-headline-md font-bold">Plan Metrics</h3>
            <span className="bg-primary-fixed text-on-primary-fixed px-3 py-1 rounded-full font-label-sm text-label-sm flex items-center gap-1 font-semibold">
              <span className="material-symbols-outlined text-[16px] filled">verified</span>
              Recommendation Ready
            </span>
          </div>

          <div className="overflow-x-auto flex-grow">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-surface-container-low text-on-surface-variant font-label-sm text-label-sm uppercase tracking-wider">
                  <th className="p-4 font-semibold">Plan</th>
                  <th className="p-4 font-semibold">Main Crops</th>
                  <th className="p-4 font-semibold">Yield (t/ha)</th>
                  <th className="p-4 font-semibold">Cost/ha</th>
                  <th className="p-4 font-semibold">Land Impact</th>
                  <th className="p-4 font-semibold">Water Usg.</th>
                </tr>
              </thead>
              <tbody className="font-body-md text-body-md text-on-surface">
                {Object.keys(plans).map((id) => {
                  const plan = plans[id];
                  const isSelected = selectedPlanId === id;
                  const isRec = recommendedPlanId === id;

                  return (
                    <tr
                      key={id}
                      onClick={() => setSelectedPlanId(id)}
                      className={`border-b border-outline-variant/20 hover:bg-surface-container-low transition-colors cursor-pointer relative ${
                        isSelected ? 'bg-primary/5 font-semibold' : ''
                      }`}
                    >
                      <td className={`p-4 font-bold flex items-center gap-2 ${
                        id === 'A' ? 'text-primary' : id === 'B' ? 'text-secondary' : 'text-on-surface-variant'
                      }`}>
                        Plan {id}
                        {isSelected && <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary"></div>}
                        {isRec && (
                          <span className="bg-secondary-fixed text-on-secondary-fixed-variant text-[10px] px-1.5 py-0.5 rounded font-bold">
                            Rec
                          </span>
                        )}
                      </td>
                      <td className="p-4 text-sm">{plan.crops}</td>
                      <td className="p-4">{plan.yieldVal}</td>
                      <td className={`p-4 ${plan.cost > 50000 ? 'text-error font-medium' : ''}`}>₹{plan.cost.toLocaleString()}</td>
                      <td className="p-4">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-2 bg-surface-variant rounded-full w-16 overflow-hidden">
                            <div
                              className={`h-full rounded-full ${plan.cost > 50000 ? 'bg-secondary' : 'bg-primary'}`}
                              style={{ width: `${(parseInt(plan.impact) / 20) * 100}%` }}
                            ></div>
                          </div>
                          <span className="text-sm font-semibold">{plan.impact}</span>
                        </div>
                      </td>
                      <td className="p-4">
                        <span className={`px-2 py-1 rounded-md text-xs font-semibold ${
                          plan.water === 'Efficient' ? 'bg-primary-fixed-dim text-on-primary-fixed' :
                          plan.water === 'High' ? 'bg-error-container text-on-error-container' :
                          'bg-primary-fixed-dim text-on-primary-fixed'
                        }`}>
                          {plan.water}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Detailed view of selected plan */}
      <div className="bg-surface-container-lowest rounded-xl shadow-ambient p-6 mt-4 border border-outline-variant/30">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4 border-b border-outline-variant/20 pb-6">
          <div>
            <div className="flex flex-wrap items-center gap-3 mb-1">
              <h3 className="font-headline-lg text-headline-lg-mobile md:text-headline-lg text-primary font-bold">
                {selectedPlan.name}
              </h3>
              {selectedPlanId === recommendedPlanId && (
                <span className="bg-secondary-fixed text-on-secondary-fixed-variant px-3 py-1 rounded-full font-label-sm text-label-sm font-bold flex items-center gap-1 shadow-sm">
                  <span className="material-symbols-outlined text-[16px] filled">star</span> Recommended
                </span>
              )}
            </div>
            <p className="text-on-surface-variant font-body-md">Optimal crop schedules and custom multi-objective irrigation planning.</p>
          </div>

          <button
            onClick={() => {
              onSelectPlan(selectedPlanId);
              alert(`Activated Plan ${selectedPlanId}! It is now the primary optimization plan.`);
            }}
            className={`w-full md:w-auto px-8 py-3 rounded-full font-label-md text-label-md hover:opacity-90 active:scale-95 transition-all shadow-ambient-hover min-h-[48px] flex justify-center items-center gap-2 cursor-pointer font-bold ${
              activePlanId === selectedPlanId
                ? 'bg-outline-variant text-on-surface-variant hover:bg-surface-container-high'
                : 'bg-primary text-on-primary'
            }`}
          >
            <span className="material-symbols-outlined">check_circle</span>
            {activePlanId === selectedPlanId ? 'Currently Active' : 'Select This Plan'}
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div>
            <h4 className="font-headline-md text-headline-md font-bold mb-4">Plot Crop Allocations</h4>
            <div className="space-y-4">
              {selectedPlan.allocations.map((alloc, idx) => (
                <div key={idx} className="flex justify-between items-center p-3 bg-surface-container-low rounded-lg border border-outline-variant/30 hover:border-primary transition-all">
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded flex items-center justify-center font-bold ${alloc.color}`}>
                      {alloc.letter}
                    </div>
                    <div>
                      <p className="font-semibold text-on-surface font-body-md">{alloc.crop}</p>
                      <p className="text-xs text-on-surface-variant">{alloc.plots}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold text-on-surface font-body-md">{alloc.pct}</p>
                    <p className="text-xs text-on-surface-variant">{alloc.ha}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <h4 className="font-headline-md text-headline-md font-bold mb-4 flex justify-between items-end">
              Irrigation Schedule
              <button
                onClick={() => alert("Calendar details generated for selected plan.")}
                className="font-label-sm text-label-sm text-primary cursor-pointer hover:underline font-semibold"
              >
                View Full Calendar
              </button>
            </h4>
            <div className="relative pl-6 border-l-2 border-surface-variant space-y-6">
              {selectedPlan.schedule.map((sch, idx) => (
                <div key={idx} className="relative">
                  <div className={`absolute -left-[31px] w-4 h-4 rounded-full border-4 border-surface-container-lowest ${
                    sch.active ? 'bg-primary' : 'bg-surface-variant'
                  }`}></div>
                  <p className={`text-xs font-bold mb-1 uppercase tracking-wide ${sch.active ? 'text-primary' : 'text-on-surface-variant'}`}>
                    {sch.time}
                  </p>
                  <div className={`bg-surface-container-low p-3 rounded-lg border border-outline-variant/20 ${!sch.active ? 'opacity-70' : ''}`}>
                    <p className="font-semibold text-sm font-body-md text-on-surface">{sch.desc}</p>
                    <p className="text-xs text-on-surface-variant mt-1 flex items-center gap-1 font-semibold">
                      <span className="material-symbols-outlined text-[14px]">water_drop</span>
                      {sch.details}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      </>
      )}

      {/* Adjust Weights overlay modal */}
      {adjustWeightsOpen && hasData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 backdrop-blur-sm p-4 animate-[fadeIn_0.2s_ease-out]">
          <div className="bg-surface-container-lowest w-full max-w-md rounded-xl shadow-ambient p-6 border border-outline-variant/30 flex flex-col">
            <div className="flex justify-between items-center mb-6 border-b border-outline-variant/20 pb-4">
              <h3 className="font-headline-md text-headline-md text-primary font-bold">Adjust Plan weights</h3>
              <button onClick={() => setAdjustWeightsOpen(false)} className="cursor-pointer text-on-surface hover:text-primary">
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>

            <p className="text-sm text-on-surface-variant mb-6 font-semibold">Adjust weights to find the plan recommendations matching your current criteria.</p>

            <div className="space-y-6">
              <div>
                <div className="flex justify-between mb-2">
                  <label className="font-label-md text-label-md text-on-surface-variant">Yield Weight</label>
                  <span className="font-label-sm text-label-sm font-bold">{weights.yield}%</span>
                </div>
                <input
                  value={weights.yield}
                  onChange={(e) => setWeights(prev => ({ ...prev, yield: Number(e.target.value) }))}
                  className="w-full h-2 bg-surface-variant rounded-lg appearance-none cursor-pointer accent-primary"
                  max="100"
                  min="0"
                  type="range"
                />
              </div>

              <div>
                <div className="flex justify-between mb-2">
                  <label className="font-label-md text-label-md text-on-surface-variant">Cost Reduction Weight</label>
                  <span className="font-label-sm text-label-sm font-bold">{weights.cost}%</span>
                </div>
                <input
                  value={weights.cost}
                  onChange={(e) => setWeights(prev => ({ ...prev, cost: Number(e.target.value) }))}
                  className="w-full h-2 bg-surface-variant rounded-lg appearance-none cursor-pointer accent-primary"
                  max="100"
                  min="0"
                  type="range"
                />
              </div>

              <div>
                <div className="flex justify-between mb-2">
                  <label className="font-label-md text-label-md text-on-surface-variant">Water Conservation Weight</label>
                  <span className="font-label-sm text-label-sm font-bold">{weights.water}%</span>
                </div>
                <input
                  value={weights.water}
                  onChange={(e) => setWeights(prev => ({ ...prev, water: Number(e.target.value) }))}
                  className="w-full h-2 bg-surface-variant rounded-lg appearance-none cursor-pointer accent-secondary"
                  max="100"
                  min="0"
                  type="range"
                />
              </div>

              <div className="flex gap-4 pt-4 border-t border-outline-variant/20">
                <button
                  onClick={() => setWeights({ yield: 50, cost: 50, water: 50 })}
                  className="flex-1 bg-surface-container-high hover:bg-surface-dim font-label-md text-label-md py-3 rounded-lg transition-colors cursor-pointer font-bold"
                >
                  Reset
                </button>
                <button
                  onClick={() => setAdjustWeightsOpen(false)}
                  className="flex-1 bg-primary text-on-primary font-label-md text-label-md py-3 rounded-lg hover:opacity-90 transition-opacity shadow-sm cursor-pointer font-bold"
                >
                  Apply & Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
