import React, { useEffect, useState } from 'react';
import { api, DISTRICTS, describeApiError } from '../services/api';
import { downloadFile, slug } from '../utils/download';
import { compareRows, cropRecordsCsv, districtReportText } from '../utils/districtView';
import {
  ClimateSection, CropPerformanceSection, InsightsSection, MarketSection, OverviewSection,
  SoilSection, SuitabilitySection, WaterSection,
} from '../components/district/DistrictSections';

/**
 * District Intelligence Center: one page that profiles a district before any
 * optimisation is run. All content comes from
 * GET /api/district-intelligence/{district} (one request per district); this
 * view only lays it out.
 */
export default function DistrictIntelligenceView({ userLocation, onNavigate }) {
  const [district, setDistrict] = useState(DISTRICTS.includes(userLocation) ? userLocation : DISTRICTS[0]);
  const [state, setState] = useState({ loading: true, data: null, error: '' });
  const [compareWith, setCompareWith] = useState('');
  const [compare, setCompare] = useState({ loading: false, data: null, error: '' });

  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, data: null, error: '' });
    api.getDistrictIntelligence(district)
      .then((data) => { if (!cancelled) setState({ loading: false, data, error: '' }); })
      .catch((err) => { if (!cancelled) setState({ loading: false, data: null, error: describeApiError(err) }); });
    return () => { cancelled = true; };
  }, [district]);

  useEffect(() => {
    if (!compareWith) return undefined;
    let cancelled = false;
    setCompare({ loading: true, data: null, error: '' });
    api.getDistrictIntelligence(compareWith)
      .then((data) => { if (!cancelled) setCompare({ loading: false, data, error: '' }); })
      .catch((err) => { if (!cancelled) setCompare({ loading: false, data: null, error: describeApiError(err) }); });
    return () => { cancelled = true; };
  }, [compareWith]);

  const intel = state.data;
  const actions = [
    { id: 'run', icon: 'model_training', label: 'Run optimization', onClick: () => onNavigate('run-optimization', { district }) },
    { id: 'compare', icon: 'compare', label: 'Compare district', onClick: () => setCompareWith(DISTRICTS.find((d) => d !== district)) },
    { id: 'report', icon: 'description', label: 'Generate report', disabled: !intel,
      onClick: () => downloadFile(`agrooptimize-district-${slug(district)}.txt`, districtReportText(intel)) },
    { id: 'analytics', icon: 'analytics', label: 'View analytics', onClick: () => onNavigate('analytics') },
    { id: 'export', icon: 'download', label: 'Export data (CSV)', disabled: !intel,
      onClick: () => downloadFile(`agrooptimize-district-${slug(district)}-crops.csv`, cropRecordsCsv(intel), 'text/csv;charset=utf-8') },
    { id: 'export-json', icon: 'data_object', label: 'Export all (JSON)', disabled: !intel,
      onClick: () => downloadFile(`agrooptimize-district-${slug(district)}.json`, JSON.stringify(intel, null, 2), 'application/json') },
  ];

  return (
    <div className="animate-[fadeIn_0.2s_ease-out] space-y-8">
      <header className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <h2 className="font-headline-lg text-headline-lg-mobile md:text-headline-lg text-primary font-bold">District Intelligence</h2>
          <p className="text-on-surface-variant mt-1 max-w-2xl">
            Climate, soil, water, crop history and suitability for a district, built from the observed records in the dataset.
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm font-semibold text-on-surface-variant">
          District
          <select value={district} onChange={(e) => { setDistrict(e.target.value); setCompareWith(''); }}
            className="h-11 px-3 rounded-lg border border-outline-variant bg-surface-bright text-on-surface cursor-pointer">
            {DISTRICTS.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </label>
      </header>

      {state.loading && (
        <div className="space-y-4" aria-busy="true">
          <div className="h-28 bg-surface-container-high rounded-xl animate-pulse"></div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">{[0, 1, 2, 3].map((i) => <div key={i} className="h-24 bg-surface-container-high rounded-xl animate-pulse"></div>)}</div>
          <div className="h-64 bg-surface-container-high rounded-xl animate-pulse"></div>
        </div>
      )}

      {state.error && (
        <div className="text-center py-16 bg-surface-container-lowest rounded-xl border border-dashed border-outline-variant/30">
          <span className="material-symbols-outlined text-5xl text-outline" aria-hidden="true">cloud_off</span>
          <p className="text-on-surface-variant mt-2">{state.error}</p>
        </div>
      )}

      {intel && (
        <>
          <section className="bg-primary text-on-primary rounded-xl p-6 shadow-ambient">
            <p className="text-xs uppercase tracking-wide font-semibold opacity-80">District summary · {intel.district}</p>
            <p className="mt-2 leading-relaxed">{intel.summary.text}</p>
          </section>

          <nav aria-label="Quick actions" className="flex flex-wrap gap-2">
            {actions.map((a) => (
              <button key={a.id} onClick={a.onClick} disabled={a.disabled}
                className="flex items-center gap-2 px-4 py-2 rounded-full border border-outline-variant bg-surface-container-lowest text-sm font-semibold text-on-surface hover:border-primary hover:text-primary transition-colors cursor-pointer disabled:opacity-40">
                <span className="material-symbols-outlined text-[18px]" aria-hidden="true">{a.icon}</span>{a.label}
              </button>
            ))}
          </nav>

          {compareWith && (
            <section className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <h3 className="font-headline-md text-[17px] font-bold">Compare {intel.district} with</h3>
                <div className="flex items-center gap-2">
                  <select value={compareWith} onChange={(e) => setCompareWith(e.target.value)}
                    className="h-9 px-2 rounded-lg border border-outline-variant bg-surface-bright text-sm cursor-pointer" aria-label="District to compare with">
                    {DISTRICTS.filter((d) => d !== district).map((d) => <option key={d} value={d}>{d}</option>)}
                  </select>
                  <button onClick={() => setCompareWith('')} aria-label="Close comparison" className="p-1 cursor-pointer text-on-surface-variant hover:text-primary">
                    <span className="material-symbols-outlined" aria-hidden="true">close</span>
                  </button>
                </div>
              </div>
              {compare.loading && <div className="h-40 bg-surface-container-high rounded-lg animate-pulse"></div>}
              {compare.error && <p className="text-sm text-on-error-container">{compare.error}</p>}
              {compare.data && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-on-surface-variant border-b border-outline-variant/40">
                        <th scope="col" className="py-2 pr-3">Indicator</th>
                        <th scope="col" className="py-2 pr-3">{intel.district}</th>
                        <th scope="col" className="py-2">{compare.data.district}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {compareRows(intel, compare.data).map((r) => (
                        <tr key={r.label} className="border-b border-outline-variant/20">
                          <th scope="row" className="py-2 pr-3 text-left font-semibold">{r.label}</th>
                          <td className="py-2 pr-3">{r.a}</td>
                          <td className="py-2">{r.b}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}

          <OverviewSection intel={intel} />
          <ClimateSection intel={intel} insights={intel.insights} />
          <SoilSection intel={intel} />
          <WaterSection intel={intel} />
          <CropPerformanceSection key={`crops-${intel.district}`} intel={intel} />
          <SuitabilitySection key={`suit-${intel.district}`} intel={intel} />
          <MarketSection key={`market-${intel.district}`} intel={intel} />
          <InsightsSection insights={intel.insights} />
        </>
      )}
    </div>
  );
}
