import React, { useState, useMemo, useEffect } from 'react';
import { api } from '../services/api';

// Adapts GET /api/history/{district}'s entries (target_yield, est_cost,
// fuzzy_weights, ...) onto this view's field names. The backend only ever
// returns this browser's own real, saved optimization runs -- never
// CSV-derived filler -- so an empty/failed fetch just means an empty list,
// and the view below shows a plain "no runs yet" state instead.
function adaptHistory(apiHistory) {
  return (apiHistory || []).map((h) => ({
    id: h.id,
    season: h.season,
    year: h.season.split(' ').pop(),
    date: h.date,
    targetYield: h.target_yield,
    estCost: h.est_cost,
    status: h.status,
    details: `${h.num_plans} Pareto-optimal plan(s) generated (preference: ${h.preference || 'balanced'}).` +
      (h.fuzzy_weights
        ? ` Yield confidence ${Math.round(h.fuzzy_weights.yield_confidence * 100)}%, irrigation risk ${Math.round(h.fuzzy_weights.irrigation_risk * 100)}%.`
        : ''),
  }));
}

export default function HistoryView({ userLocation, onNavigate }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedYear, setSelectedYear] = useState('all');
  const [selectedDetail, setSelectedDetail] = useState(null);

  const [historyData, setHistoryData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchFailed, setFetchFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.getHistory(userLocation)
      .then((data) => {
        if (cancelled) return;
        setHistoryData(adaptHistory(data.history));
        setFetchFailed(false);
      })
      .catch(() => {
        if (cancelled) return;
        setHistoryData([]);
        setFetchFailed(true);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [userLocation]);

  const years = useMemo(() => {
    return Array.from(new Set(historyData.map((h) => h.year))).sort((a, b) => Number(b) - Number(a));
  }, [historyData]);

  const filteredHistory = useMemo(() => {
    return historyData.filter(item => {
      const matchSearch = item.season.toLowerCase().includes(searchTerm.toLowerCase());
      const matchYear = selectedYear === 'all' || item.year === selectedYear;
      return matchSearch && matchYear;
    });
  }, [historyData, searchTerm, selectedYear]);

  return (
    <div className="animate-[fadeIn_0.2s_ease-out] w-full">
      <header className="flex flex-col md:flex-row md:justify-between md:items-end space-y-4 md:space-y-0 mb-6 gap-4">
        <div>
          <h2 className="font-headline-lg text-headline-lg-mobile md:text-headline-lg text-primary font-bold">Optimization History</h2>
          <p className="font-body-md text-body-md text-on-surface-variant mt-2">Review past seasons and optimization results.</p>
        </div>
        <div className="flex flex-col sm:flex-row space-y-2 sm:space-y-0 sm:space-x-4 w-full md:w-auto">
          <div className="relative w-full sm:w-64">
            <span className="material-symbols-outlined absolute left-3 top-1/2 transform -translate-y-1/2 text-outline">search</span>
            <input
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-3 rounded-lg border border-outline-variant bg-surface-container-lowest focus:border-primary focus:ring-1 focus:ring-primary font-body-md text-body-md outline-none transition-colors min-h-[48px]"
              placeholder="Search seasons..."
              type="text"
            />
          </div>
          <div className="relative w-full sm:w-48">
            <span className="material-symbols-outlined absolute left-3 top-1/2 transform -translate-y-1/2 text-outline">filter_list</span>
            <select
              value={selectedYear}
              onChange={(e) => setSelectedYear(e.target.value)}
              className="w-full pl-10 pr-8 py-3 rounded-lg border border-outline-variant bg-surface-container-lowest focus:border-primary focus:ring-1 focus:ring-primary font-body-md text-body-md appearance-none outline-none transition-colors min-h-[48px] cursor-pointer"
            >
              <option value="all">All Years</option>
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
        </div>
      </header>

      {/* Timeline / Card List */}
      <div className="relative mt-8">
        <div className="hidden lg:block absolute left-4 top-0 bottom-0 w-0.5 bg-outline-variant/30"></div>
        {loading ? (
          <div className="space-y-8">
            {[0, 1, 2].map((i) => (
              <div key={i} className="lg:ml-12 h-32 bg-surface-container-lowest rounded-xl border border-outline-variant/20 animate-pulse"></div>
            ))}
          </div>
        ) : (
        <div className="space-y-8">
          {filteredHistory.map((item) => (
            <div key={item.id} className="relative flex flex-col lg:flex-row lg:items-start group">
              <div className="hidden lg:flex absolute left-4 transform -translate-x-1/2 mt-6 w-4 h-4 rounded-full bg-primary ring-4 ring-surface-container-lowest z-10 transition-transform group-hover:scale-125"></div>

              <div className="lg:ml-12 w-full">
                <div className="bg-surface-container-lowest rounded-xl p-6 shadow-soft hover:shadow-ambient transition-shadow duration-300 border border-outline-variant/20">
                  <div className="flex justify-between items-start mb-4">
                    <div>
                      <h3 className="font-headline-md text-headline-md font-bold text-on-surface flex items-center gap-2">
                        {item.season}
                      </h3>
                      <p className="font-body-md text-body-md text-on-surface-variant flex items-center mt-1">
                        <span className="material-symbols-outlined text-[18px] mr-1">calendar_month</span>
                        {item.date}
                      </p>
                    </div>
                    <span className="px-3 py-1 bg-primary/10 text-primary rounded-full font-label-sm text-label-sm flex items-center space-x-1 font-semibold">
                      <span className="material-symbols-outlined text-[16px]">check_circle</span>
                      <span>{item.status}</span>
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-surface-container-low rounded-lg p-4">
                    <div>
                      <p className="font-label-sm text-label-sm text-on-surface-variant mb-1 font-medium">Target Yield</p>
                      <p className="font-body-lg text-body-lg font-bold text-primary">{item.targetYield}</p>
                    </div>
                    <div>
                      <p className="font-label-sm text-label-sm text-on-surface-variant mb-1 font-medium">Estimated Cost</p>
                      <p className="font-body-lg text-body-lg font-bold text-on-surface">{item.estCost}</p>
                    </div>
                  </div>

                  <div className="mt-4 flex justify-end">
                    <button
                      onClick={() => setSelectedDetail(item)}
                      className="font-label-md text-label-md text-primary font-bold hover:text-primary-container transition-colors flex items-center min-h-[48px] px-4 cursor-pointer"
                    >
                      View Details <span className="material-symbols-outlined ml-1">arrow_forward</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}

          {filteredHistory.length === 0 && (
            <div className="text-center py-16 bg-surface-container-lowest rounded-xl border border-dashed border-outline-variant/30">
              <span className="material-symbols-outlined text-5xl text-outline mb-2">history</span>
              <p className="font-body-lg text-on-surface-variant">
                {fetchFailed
                  ? "Couldn't reach the backend. Confirm uvicorn is running on port 8000."
                  : historyData.length === 0
                    ? 'No optimization runs found. Generate your first optimization to see it here.'
                    : 'No history entries found matching your search/filter.'}
              </p>
              {!fetchFailed && historyData.length === 0 && onNavigate && (
                <button
                  onClick={() => onNavigate('run-optimization')}
                  className="mt-4 inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-primary text-on-primary font-label-md text-label-md hover:opacity-90 transition-opacity cursor-pointer font-bold"
                >
                  <span className="material-symbols-outlined text-[18px]">model_training</span>
                  Run Optimization
                </button>
              )}
            </div>
          )}
        </div>
        )}
      </div>

      {/* Details Popup Modal */}
      {selectedDetail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 backdrop-blur-sm p-4 animate-[fadeIn_0.2s_ease-out]">
          <div className="bg-surface-container-lowest w-full max-w-md rounded-xl shadow-ambient p-6 border border-outline-variant/30 flex flex-col">
            <div className="flex justify-between items-center mb-6 border-b border-outline-variant/20 pb-4">
              <h3 className="font-headline-md text-headline-md text-primary font-bold">{selectedDetail.season} Detail</h3>
              <button
                onClick={() => setSelectedDetail(null)}
                className="cursor-pointer text-on-surface hover:text-primary flex items-center justify-center"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <span className="font-label-sm text-label-sm text-on-surface-variant block mb-1">Execution Date</span>
                <span className="font-body-md text-on-surface font-semibold">{selectedDetail.date}</span>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <span className="font-label-sm text-label-sm text-on-surface-variant block mb-1">Target Yield</span>
                  <span className="font-body-md text-primary font-bold">{selectedDetail.targetYield}</span>
                </div>
                <div>
                  <span className="font-label-sm text-label-sm text-on-surface-variant block mb-1">Est. Cost</span>
                  <span className="font-body-md text-on-surface font-bold">{selectedDetail.estCost}</span>
                </div>
              </div>
              <div>
                <span className="font-label-sm text-label-sm text-on-surface-variant block mb-1">Optimization Notes</span>
                <p className="text-sm text-on-surface leading-relaxed">{selectedDetail.details}</p>
              </div>
            </div>

            <button
              onClick={() => setSelectedDetail(null)}
              className="mt-6 w-full bg-primary text-on-primary font-label-md text-label-md py-3 rounded-lg hover:opacity-90 transition-opacity shadow-sm cursor-pointer font-bold"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
