import React, { useEffect, useState } from 'react';
import { api, describeApiError } from '../services/api';
import { OFFICIAL_DATA_NA, showValue, useCatalog, useDatasets } from '../services/officialData';

/**
 * Official Dataset Information: what the backend loaded and what it could not.
 * Everything comes from GET /api/datasets (registry + disabled features),
 * GET /api/catalog (district, season and year coverage) and
 * GET /api/soil-master (Soil Health Card coverage). Nothing is typed in here.
 */

const cell = 'py-2 px-3 align-top';

function Card({ icon, title, subtitle, children }) {
  return (
    <section className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 shadow-soft p-5">
      <h3 className="font-headline-md text-headline-md font-bold text-on-surface flex items-center gap-2">
        <span className="material-symbols-outlined text-primary" aria-hidden="true">{icon}</span>{title}
      </h3>
      {subtitle && <p className="text-sm text-on-surface-variant mt-0.5">{subtitle}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Stat({ label, value }) {
  return (
    <div className="bg-surface-container-low rounded-lg p-3">
      <p className="text-xs text-on-surface-variant font-semibold">{label}</p>
      <p className="font-body-lg text-body-lg font-bold text-on-surface mt-0.5 break-words">{value}</p>
    </div>
  );
}

export default function DatasetsView({ userLocation }) {
  const datasets = useDatasets();
  const catalog = useCatalog();
  const [soil, setSoil] = useState({ loading: true, data: null, error: null });

  useEffect(() => {
    let cancelled = false;
    api.getSoilMaster()
      .then((data) => { if (!cancelled) setSoil({ loading: false, data, error: null }); })
      .catch((error) => { if (!cancelled) setSoil({ loading: false, data: null, error }); });
    return () => { cancelled = true; };
  }, []);

  const list = datasets.data?.datasets ?? [];
  const disabled = datasets.data?.disabled_features ?? [];
  const cat = catalog.data;
  const totalRows = list.reduce((sum, d) => sum + (d.rows_clean || 0), 0);
  const soilAvailable = soil.data?.available ?? [];
  const soilMissing = soil.data?.unavailable ?? [];

  return (
    <div className="animate-[fadeIn_0.2s_ease-out] space-y-6">
      <header>
        <h2 className="font-headline-lg text-headline-lg-mobile md:text-headline-lg text-primary font-bold">Official Dataset Information</h2>
        <p className="text-on-surface-variant mt-1 max-w-3xl">
          Every recommendation is built only from these government datasets. Features whose official dataset is not loaded are
          switched off and listed below, instead of being estimated.
        </p>
      </header>

      {(datasets.error || catalog.error) && (
        <p className="text-sm bg-error-container/40 text-on-error-container px-4 py-3 rounded-lg" role="alert">
          {describeApiError(datasets.error || catalog.error)}
        </p>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Official datasets loaded" value={datasets.loading ? '…' : showValue(list.length || null)} />
        <Stat label="Clean rows" value={datasets.loading ? '…' : showValue(totalRows || null, (v) => v.toLocaleString('en-IN'))} />
        <Stat label="Districts covered" value={catalog.loading ? '…' : showValue(cat?.locations?.length)} />
        <Stat label="Seasons · report years" value={catalog.loading ? '…' : showValue(cat?.seasons?.length ? `${cat.seasons.join(', ')} · ${cat.years.join(', ')}` : null)} />
      </div>

      <Card icon="database" title="Loaded datasets"
        subtitle="The registry the backend keeps for each file: when it was imported, how many rows passed validation, and its checksum.">
        {datasets.loading ? (
          <div className="h-40 bg-surface-container-high rounded-lg animate-pulse" aria-busy="true"></div>
        ) : list.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-on-surface-variant bg-surface-container-low">
                  {['Dataset', 'Government source', 'Coverage', 'Last updated', 'Rows', 'Availability', 'Checksum (sha256)'].map((h) => (
                    <th key={h} scope="col" className="py-2 px-3 font-semibold whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {list.map((d) => (
                  <tr key={d.id} className="border-t border-outline-variant/30">
                    <th scope="row" className={`${cell} text-left`}>
                      <span className="font-semibold">{d.name}</span>
                      <span className="block text-xs text-on-surface-variant font-normal">{d.filename}</span>
                    </th>
                    <td className={`${cell} text-on-surface-variant`}>{showValue(d.source)}</td>
                    <td className={cell}>{showValue(d.report_year, (v) => `Report year ${v}`)}</td>
                    <td className={`${cell} whitespace-nowrap`}>{showValue(d.imported_at, (v) => new Date(v).toLocaleString())}</td>
                    <td className={cell}>{showValue(d.rows_clean, (v) => v.toLocaleString('en-IN'))}</td>
                    <td className={cell}>
                      <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-primary-fixed/40 text-on-primary-fixed">Loaded</span>
                    </td>
                    <td className={`${cell} font-mono text-xs`} title={d.sha256}>{showValue(d.sha256, (v) => `${v.slice(0, 12)}…`)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="text-sm text-on-surface-variant">{OFFICIAL_DATA_NA}</p>}
      </Card>

      <Card icon="block" title="Missing data and disabled features"
        subtitle="Each feature below stays off until its official dataset is loaded. Nothing is filled in with estimates.">
        {datasets.loading ? (
          <div className="h-32 bg-surface-container-high rounded-lg animate-pulse" aria-busy="true"></div>
        ) : disabled.length ? (
          <ul className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {disabled.map((f) => (
              <li key={f.feature} className="p-3 rounded-lg bg-surface-container-low border border-outline-variant/20">
                <p className="font-semibold text-sm text-on-surface">{f.feature}</p>
                <dl className="mt-1.5 space-y-1 text-xs text-on-surface-variant">
                  <div><dt className="inline font-semibold">Missing data: </dt><dd className="inline">{showValue(f.missing_dataset)}</dd></div>
                  <div><dt className="inline font-semibold">Where it would come from: </dt><dd className="inline">{showValue(f.source)}</dd></div>
                  <div><dt className="inline font-semibold">Effect: </dt><dd className="inline">{showValue(f.scope)}</dd></div>
                </dl>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-on-surface-variant">No feature is disabled.</p>}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card icon="science" title="Soil Health Card coverage" subtitle={soil.data ? `Cycle ${soil.data.cycle}` : undefined}>
          {soil.loading ? (
            <div className="h-24 bg-surface-container-high rounded-lg animate-pulse" aria-busy="true"></div>
          ) : soil.error ? (
            <p className="text-sm text-on-surface-variant">{OFFICIAL_DATA_NA}: {describeApiError(soil.error)}</p>
          ) : (
            <div className="space-y-2 text-sm">
              <p><b>{soilAvailable.length}</b> districts have a Soil Health Card record
                {userLocation && <> · {userLocation}: <b>{soilAvailable.includes(userLocation) ? 'available' : OFFICIAL_DATA_NA}</b></>}
              </p>
              {soilMissing.length > 0 && (
                <p className="text-on-surface-variant">
                  No record: {soilMissing.map((m) => `${m.district} (${m.message})`).join(', ')}
                </p>
              )}
            </div>
          )}
        </Card>

        <Card icon="map" title="Geographic coverage">
          {catalog.loading ? (
            <div className="h-24 bg-surface-container-high rounded-lg animate-pulse" aria-busy="true"></div>
          ) : cat ? (
            <div className="space-y-2 text-sm">
              <p>{cat.locations.length} districts: <span className="text-on-surface-variant">{cat.locations.join(', ')}</span></p>
              {Object.values(cat.taluk_notes ?? {}).map((note) => <p key={note} className="text-on-surface-variant">{note}</p>)}
            </div>
          ) : <p className="text-sm text-on-surface-variant">{OFFICIAL_DATA_NA}</p>}
        </Card>
      </div>
    </div>
  );
}
