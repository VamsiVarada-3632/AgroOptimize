import React, { useMemo, useState } from 'react';
import LineChart from '../charts/LineChart';
import BarChart from '../charts/BarChart';
import ChartCard from '../charts/ChartCard';
import { formatNumber } from '../charts/chartTheme';
import {
  CROP_METRICS, MONTH_SHORT, cropSeries, filterCropRecords, monthlyRainSeries, yearDistribution,
} from '../../utils/districtView';

/**
 * Section components for the District Intelligence page. They render the
 * payload of GET /api/district-intelligence/{district}; every number and
 * sentence comes from the backend. Missing values show "Data not available".
 */

export const NA = 'Data not available';
const show = (v, suffix = '', digits = 0) => (v === null || v === undefined ? NA : `${formatNumber(v, digits)}${suffix}`);

export function SectionHeader({ icon, title, subtitle }) {
  return (
    <div className="mb-3">
      <h3 className="font-headline-md text-headline-md font-bold text-on-surface flex items-center gap-2">
        <span className="material-symbols-outlined text-primary" aria-hidden="true">{icon}</span>{title}
      </h3>
      {subtitle && <p className="text-sm text-on-surface-variant mt-0.5">{subtitle}</p>}
    </div>
  );
}

export function StatTile({ label, value, hint, icon }) {
  const missing = value === NA;
  return (
    <div className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4" title={hint}>
      <div className="flex items-center justify-between">
        <p className="text-xs text-on-surface-variant font-semibold uppercase tracking-wide">{label}</p>
        {icon && <span className="material-symbols-outlined text-primary text-[18px]" aria-hidden="true">{icon}</span>}
      </div>
      <p className={`mt-1 ${missing ? 'text-sm text-on-surface-variant italic' : 'text-lg font-bold text-on-surface'}`}>{value}</p>
      {hint && !missing && <p className="text-[11px] text-on-surface-variant mt-0.5">{hint}</p>}
    </div>
  );
}

function ItemCards({ items, empty }) {
  if (!items?.length) return <p className="text-sm text-on-surface-variant">{empty}</p>;
  return (
    <ul className="space-y-2">
      {items.map((i) => (
        <li key={i.id} className="p-3 rounded-lg bg-surface-container-low text-sm" title={`Source: ${i.source}`}>
          <p className="font-semibold text-on-surface">{i.title}</p>
          <p className="text-on-surface-variant mt-0.5">{i.detail}</p>
        </li>
      ))}
    </ul>
  );
}

function Select({ label, value, onChange, options }) {
  return (
    <label className="flex items-center gap-2 text-xs font-semibold text-on-surface-variant">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="h-9 px-2 rounded-lg border border-outline-variant bg-surface-bright text-on-surface text-sm cursor-pointer">
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

// ---------------------------------------------------------------------------

export function OverviewSection({ intel }) {
  const o = intel.overview;
  const c = intel.coverage;
  const seasons = Object.entries(c.seasons_available).filter(([, ys]) => ys.length).map(([s, ys]) => `${s} (${ys[0]}–${ys[ys.length - 1]})`);
  return (
    <section>
      <SectionHeader icon="map" title="District overview" subtitle={`${o.land_basis} Land figures from ${o.land_year_basis ?? '–'}.`} />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="Agricultural area" icon="agriculture" value={show(o.agricultural_area_ha, ' ha')}
          hint={o.total_area_ha ? `of ${formatNumber(o.total_area_ha)} ha total land` : undefined} />
        <StatTile label="Irrigated share" icon="water" value={show(o.irrigated_pct, '%', 1)} hint="Irrigated ÷ agricultural land" />
        <StatTile label="Average annual rainfall" icon="rainy" value={show(o.average_annual_rainfall_mm, ' mm')}
          hint={o.stated_annual_normal_mm ? `Stated normal ${formatNumber(o.stated_annual_normal_mm)} mm` : undefined} />
        <StatTile label="Average temperature" icon="device_thermostat" value={show(o.average_temperature_c, ' °C', 1)}
          hint={o.average_humidity_pct ? `Mean humidity ${o.average_humidity_pct}%` : undefined} />
        <StatTile label="Soil types" icon="landscape" value={o.soil_types.length ? o.soil_types.join(', ') : NA} />
        <StatTile label="Agro-climatic zone" icon="public" value={o.agricultural_zone ?? NA} hint={o.agricultural_zone_note} />
        <StatTile label="Primary irrigation sources" icon="waves"
          value={o.primary_irrigation_sources.length ? o.primary_irrigation_sources.map((s) => s.source).join(', ') : NA}
          hint="Ordered by share of monthly records" />
        <StatTile label="Last dataset update" icon="update" value={c.last_dataset_update ?? NA} hint={c.last_dataset_update_basis} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mt-3">
        <div className="lg:col-span-2 bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4">
          <p className="text-xs text-on-surface-variant font-semibold uppercase tracking-wide mb-2">Major crops by sown area</p>
          {o.major_crops.length ? (
            <ul className="space-y-1.5 text-sm">
              {o.major_crops.map((m) => (
                <li key={`${m.crop}-${m.season}`} className="flex justify-between gap-2">
                  <span className="font-semibold">{m.crop} <span className="text-on-surface-variant font-normal">· {m.season}</span></span>
                  <span className="text-on-surface-variant">{formatNumber(m.mean_area_ha)} ha · {m.mean_area_share_pct}% of season area</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm italic text-on-surface-variant">{NA}</p>}
        </div>
        <div className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4 text-sm">
          <p className="text-xs text-on-surface-variant font-semibold uppercase tracking-wide mb-2">Data coverage</p>
          <p>Observed years: <b>{c.observed_years.join(', ') || NA}</b></p>
          <p>Estimated (excluded): <b>{c.estimated_years.join(', ') || 'none'}</b></p>
          <p>Seasons: {seasons.join(', ') || NA}</p>
          <p className="text-xs text-on-surface-variant mt-1">
            Monthly records complete: rainfall {show(c.monthly_completeness_pct.rainfall, '%')}, water {show(c.monthly_completeness_pct.water, '%')}
          </p>
        </div>
      </div>
    </section>
  );
}

export function ClimateSection({ intel, insights }) {
  const cl = intel.climate;
  const years = cl.annual.map((a) => a.year);
  const [year, setYear] = useState('latest');
  const monthly = useMemo(() => monthlyRainSeries(cl.monthly, year === 'latest' ? null : year), [cl.monthly, year]);
  const observations = insights.filter((i) => ['rainfall-trend', 'rainfall-normal', 'rainfall-season', 'temperature'].includes(i.id));
  return (
    <section>
      <SectionHeader icon="partly_cloudy_day" title="Climate profile" subtitle="Observed years only. Hover a chart for values, or switch to the table view." />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <ChartCard title="Annual rainfall vs normal" subtitle="Bars: observed total; line: the dataset's normal for that year."
          table={{ columns: [{ key: 'year', label: 'Year' }, { key: 'total_mm', label: 'Rainfall (mm)' }, { key: 'normal_mm', label: 'Normal (mm)' },
            { key: 'deviation_pct', label: 'Deviation %' }, { key: 'rainy_days', label: 'Rainy days' }], rows: cl.annual }}>
          <BarChart ariaLabel="Annual rainfall by year" unit=" mm" referenceLabel="Normal"
            data={cl.annual.map((a) => ({ key: a.year, label: String(a.year), value: a.total_mm, reference: a.normal_mm, detail: `${a.deviation_pct}% vs normal` }))} />
        </ChartCard>
        <ChartCard title="Monthly rainfall" subtitle={`${monthly.selectedYear} highlighted; other observed years in gray.`}
          actions={<Select label="Year" value={year} onChange={setYear}
            options={[{ value: 'latest', label: 'Latest' }, ...years.map((y) => ({ value: String(y), label: String(y) }))]} />}
          table={{ columns: [{ key: 'year', label: 'Year' }, { key: 'month', label: 'Month' }, { key: 'rainfall_mm', label: 'Rainfall (mm)' },
            { key: 'normal_mm', label: 'Normal (mm)' }, { key: 'met_season', label: 'Season' }],
          rows: cl.monthly.filter((m) => m.year === monthly.selectedYear) }}>
          <LineChart ariaLabel="Monthly rainfall" xValues={monthly.xValues} series={monthly.series}
            formatX={(m) => MONTH_SHORT[m - 1]} unit=" mm" digits={0} yLabel="mm" />
        </ChartCard>
        <ChartCard title="Where the year's rain comes from" subtitle="Share of observed annual rainfall by meteorological season."
          table={{ columns: [{ key: 'season', label: 'Season' }, { key: 'share_pct', label: 'Share %' }, { key: 'mean_mm_per_year', label: 'mm / year' }], rows: cl.met_season_share }}>
          <BarChart ariaLabel="Rainfall by season" orientation="horizontal" unit="%" digits={1}
            data={cl.met_season_share.map((m) => ({ key: m.season, label: m.season, value: m.share_pct, detail: `${m.mean_mm_per_year} mm a year` }))} />
        </ChartCard>
        <ChartCard title="Temperature and humidity" subtitle="Annual means of the monthly records."
          table={{ columns: [{ key: 'year', label: 'Year' }, { key: 'mean_temp_c', label: 'Mean °C' }, { key: 'max_temp_c', label: 'Max °C' },
            { key: 'min_temp_c', label: 'Min °C' }, { key: 'humidity_pct', label: 'Humidity %' }], rows: cl.annual }}>
          <LineChart ariaLabel="Mean annual temperature" xValues={years} unit=" °C" digits={1} yLabel="°C" minSpan={2}
            series={[{ id: 'temp', label: 'Mean', emphasis: true, points: cl.annual.map((a) => ({ x: a.year, y: a.mean_temp_c })) }]} />
          <p className="text-xs text-on-surface-variant mt-2">
            Humidity: {cl.annual.map((a) => `${a.year} ${a.humidity_pct}%`).join(' · ')}
          </p>
        </ChartCard>
      </div>
      <div className="mt-3 bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4">
        <p className="text-xs text-on-surface-variant font-semibold uppercase tracking-wide mb-2">Observations</p>
        <ItemCards items={observations} empty={NA} />
      </div>
    </section>
  );
}

export function SoilSection({ intel }) {
  const s = intel.soil;
  if (!s.available) return <section><SectionHeader icon="landscape" title="Soil profile" /><p className="italic text-sm text-on-surface-variant">{NA}</p></section>;
  const kharif = s.records.filter((r) => r.season === 'Kharif');
  return (
    <section>
      <SectionHeader icon="landscape" title="Soil profile" subtitle={`Latest observed year: ${s.latest_year}.`} />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="Soil type" value={s.soil_types.join(', ')} />
        <StatTile label="pH" value={show(s.latest.ph, '', 2)} />
        <StatTile label="Organic carbon" value={show(s.latest.organic_carbon_pct, '%', 2)} />
        <StatTile label="Fertility index" value={`${s.latest.fertility_index_mean} / 100`}
          hint={`Fuzzy soil set: ${s.latest.fuzzy_set} (memberships ${Object.entries(s.latest.fuzzy_membership).map(([k, v]) => `${k} ${v}`).join(', ')})`} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-3">
        <ChartCard title="Soil fertility index over time" subtitle="Kharif records; index = 0.3·pH score + 0.3·organic-carbon score + 0.4·N/P/K score."
          table={{ columns: [{ key: 'year', label: 'Year' }, { key: 'season', label: 'Season' }, { key: 'ph', label: 'pH' },
            { key: 'organic_carbon_pct', label: 'OC %' }, { key: 'n_status', label: 'N' }, { key: 'p_status', label: 'P' },
            { key: 'k_status', label: 'K' }, { key: 'fertility_index', label: 'Index' }], rows: s.records }}>
          <LineChart ariaLabel="Soil fertility index" xValues={kharif.map((r) => r.year)} digits={1} minSpan={20}
            series={[{ id: 'fi', label: 'Fertility index', emphasis: true, points: kharif.map((r) => ({ x: r.year, y: r.fertility_index })) }]} />
        </ChartCard>
        <div className="space-y-3">
          <div className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4">
            <p className="text-xs text-on-surface-variant font-semibold uppercase tracking-wide mb-2">Characteristics</p>
            <ItemCards items={s.characteristics} empty={NA} />
          </div>
          <div className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4">
            <p className="text-xs text-on-surface-variant font-semibold uppercase tracking-wide mb-2">Limitations</p>
            <ItemCards items={s.limitations} empty="No soil limitation detected in the latest records." />
          </div>
        </div>
      </div>
      <div className="mt-3 bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4">
        <p className="text-xs text-on-surface-variant font-semibold uppercase tracking-wide mb-1">Crop categories grown here</p>
        <p className="text-xs text-on-surface-variant mb-2">{s.crop_categories_basis}</p>
        <div className="flex flex-wrap gap-2">
          {s.crop_categories_grown.map((g) => (
            <span key={g.crop_type} className="text-xs px-2.5 py-1 rounded-full bg-surface-container-high" title={g.crops.join(', ')}>
              {g.crop_type}: {g.crops.join(', ')}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

export function WaterSection({ intel }) {
  const w = intel.water;
  if (!w.available) return <section><SectionHeader icon="water_drop" title="Water profile" /><p className="italic text-sm text-on-surface-variant">{NA}</p></section>;
  const months = w.storage_by_month;
  return (
    <section>
      <SectionHeader icon="water_drop" title="Water profile"
        subtitle={w.storage_identical_every_year ? 'Reservoir storage is recorded identically every year, so the chart shows the seasonal pattern only.' : undefined} />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {w.storage_by_season.map((s) => (
          <StatTile key={s.season} label={`${s.season} storage`} value={`${s.storage_pct}%`}
            hint={`Fuzzy water set: ${s.fuzzy_set}${s.below_action_threshold ? ' · below the 40% irrigation-action threshold' : ''}`} />
        ))}
        <StatTile label="Reservoir capacity" value={show(w.reservoir_capacity_mcm, ' MCM', 1)} hint={w.glossary.storage_pct} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-3">
        <ChartCard title="Reservoir storage through the year" subtitle="% of capacity, mean of observed years; dashed line: 40% irrigation-action threshold."
          table={{ columns: [{ key: 'month', label: 'Month' }, { key: 'storage_pct', label: 'Storage %' },
            { key: 'varies_between_years', label: 'Varies by year', format: (v) => (v ? 'yes' : 'no') }], rows: months }}>
          <LineChart ariaLabel="Monthly reservoir storage" xValues={months.map((_, i) => i + 1)} formatX={(m) => MONTH_SHORT[m - 1]}
            unit="%" digits={0} reference={{ value: 40, label: '40%' }}
            series={[{ id: 'storage', label: 'Storage', emphasis: true, points: months.map((m, i) => ({ x: i + 1, y: m.storage_pct })) }]} />
        </ChartCard>
        <ChartCard title="Water demand by year" subtitle={w.glossary.irrigation_share_pct}
          table={{ columns: [{ key: 'year', label: 'Year' }, { key: 'irrigation_mcm', label: 'Irrigation' }, { key: 'drinking_mcm', label: 'Drinking' },
            { key: 'industrial_mcm', label: 'Industrial' }, { key: 'total_demand_mcm', label: 'Total (MCM)' },
            { key: 'irrigation_share_pct', label: 'Irrigation %' }, { key: 'inflow_mcm', label: 'Inflow (MCM)' }], rows: w.yearly }}>
          <BarChart ariaLabel="Irrigation demand by year" unit=" MCM" digits={1}
            data={w.yearly.map((y) => ({ key: y.year, label: String(y.year), value: y.irrigation_mcm, detail: `${y.irrigation_share_pct}% of total demand` }))} />
        </ChartCard>
        <ChartCard title="Groundwater status" subtitle={`Share of monthly records by status. Depth: ${Object.entries(w.groundwater.level_mbgl_by_year).map(([y, v]) => `${y} ${v} m`).join(', ')}${w.groundwater.level_varies ? '' : ' (constant in the data)'}.`}
          table={{ columns: [{ key: 'status', label: 'Status' }, { key: 'months', label: 'Months' }, { key: 'share_pct', label: 'Share %' }], rows: w.groundwater.status_distribution }}>
          <BarChart ariaLabel="Groundwater status distribution" orientation="horizontal" unit="%" digits={1}
            data={w.groundwater.status_distribution.map((s) => ({ key: s.status, label: s.status, value: s.share_pct, detail: `${s.months} months` }))} />
        </ChartCard>
        <div className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4">
          <p className="text-xs text-on-surface-variant font-semibold uppercase tracking-wide mb-2">Water stress indicators</p>
          <ItemCards items={w.stress_indicators} empty={NA} />
          <p className="text-xs text-on-surface-variant mt-3">
            Irrigated land: {Object.entries(w.irrigation_dependency.irrigated_pct_by_year).map(([y, v]) => `${y} ${v}%`).join(' · ') || NA}
          </p>
        </div>
      </div>
    </section>
  );
}

export function CropPerformanceSection({ intel }) {
  const c = intel.crops;
  const [season, setSeason] = useState(c.filters?.seasons?.[0] || 'Kharif');
  // Default to highlighting the season's most widely grown crop: with every
  // line in the accent colour, crops cannot be told apart.
  const topCrop = (s) => c.trends?.filter((t) => t.season === s).sort((a, b) => (b.mean_area_ha ?? 0) - (a.mean_area_ha ?? 0))[0]?.crop || 'all';
  const [crop, setCrop] = useState(() => topCrop(c.filters?.seasons?.[0] || 'Kharif'));
  const [year, setYear] = useState(String(c.filters?.years?.[c.filters.years.length - 1] ?? ''));
  const [metric, setMetric] = useState('yield_t_ha');
  const seasonCrops = useMemo(() => [...new Set(filterCropRecords(c.records, { season }).map((r) => r.crop))].sort(), [c.records, season]);
  const activeCrop = seasonCrops.includes(crop) ? crop : 'all';
  const lines = useMemo(() => cropSeries(c.records, season, metric, activeCrop), [c.records, season, metric, activeCrop]);
  const bars = useMemo(() => yearDistribution(c.records, season, Number(year), metric, activeCrop), [c.records, season, year, metric, activeCrop]);
  const m = CROP_METRICS[metric];
  if (!c.available) return <section><SectionHeader icon="grass" title="Historical crop performance" /><p className="italic text-sm text-on-surface-variant">{NA}</p></section>;
  const tableRows = filterCropRecords(c.records, { season, crop: activeCrop });
  const trendRows = c.trends.filter((t) => t.season === season);
  return (
    <section>
      <SectionHeader icon="grass" title="Historical crop performance" subtitle="Observed crop records. Filter by season, crop and year." />
      <div className="flex flex-wrap gap-3 mb-3">
        <Select label="Season" value={season} onChange={(v) => { setSeason(v); setCrop(topCrop(v)); }} options={c.filters.seasons.map((s) => ({ value: s, label: s }))} />
        <Select label="Crop" value={activeCrop} onChange={setCrop} options={[{ value: 'all', label: 'All crops' }, ...seasonCrops.map((x) => ({ value: x, label: x }))]} />
        <Select label="Year" value={year} onChange={setYear} options={c.filters.years.map((y) => ({ value: String(y), label: String(y) }))} />
        <Select label="Metric" value={metric} onChange={setMetric} options={Object.entries(CROP_METRICS).map(([k, v]) => ({ value: k, label: v.label }))} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <ChartCard title={`${m.label} over time – ${season}`} subtitle={activeCrop === 'all' ? 'All crops of the season.' : `${activeCrop} highlighted; other ${season} crops in gray.`}
          table={{ columns: [{ key: 'year', label: 'Year' }, { key: 'crop', label: 'Crop' }, { key: 'area_ha', label: 'Area (ha)' },
            { key: 'production_t', label: 'Production (t)' }, { key: 'yield_t_ha', label: 'Yield (t/ha)' }, { key: 'area_share_pct', label: 'Share %' }], rows: tableRows }}>
          {lines.series.length > 3 && activeCrop === 'all' && (
            <p className="text-xs text-on-surface-variant mb-1">Tip: pick a crop to highlight it.</p>
          )}
          <LineChart ariaLabel={`${m.label} by year`} xValues={lines.xValues} series={lines.series} unit={m.unit} digits={m.digits} />
        </ChartCard>
        <ChartCard title={`${m.label} by crop – ${season} ${year}`} subtitle="Crop distribution within the season for the selected year.">
          <BarChart ariaLabel={`${m.label} by crop`} orientation="horizontal" unit={m.unit} digits={m.digits} data={bars} />
        </ChartCard>
      </div>
      <div className="mt-3 overflow-x-auto bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4">
        <p className="text-xs text-on-surface-variant font-semibold uppercase tracking-wide mb-2">Trends {season}, {c.filters.years[0]}–{c.filters.years[c.filters.years.length - 1]}</p>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-on-surface-variant"><th className="py-1 pr-3">Crop</th><th className="py-1 pr-3">Production</th><th className="py-1 pr-3">Area</th><th className="py-1 pr-3">Yield</th><th className="py-1">Yield variability</th></tr></thead>
          <tbody>
            {trendRows.map((t) => (
              <tr key={t.crop} className={`border-t border-outline-variant/30 ${t.crop === activeCrop ? 'bg-primary-fixed/20' : ''}`}>
                <td className="py-1.5 pr-3 font-semibold">{t.crop}</td>
                {['production', 'area', 'yield'].map((k) => (
                  <td key={k} className="py-1.5 pr-3">{t[k] ? `${t[k].direction} (${t[k].change_pct > 0 ? '+' : ''}${t[k].change_pct}%)` : NA}</td>
                ))}
                <td className="py-1.5">{t.yield ? `${t.yield.variability} (CV ${t.yield.cv})` : NA}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function SuitabilitySection({ intel }) {
  const s = intel.suitability;
  const [season, setSeason] = useState('all');
  if (!s.available) return <section><SectionHeader icon="leaderboard" title="Crop suitability rankings" /><p className="italic text-sm text-on-surface-variant">{NA}</p></section>;
  const rows = s.rankings.filter((r) => season === 'all' || r.season === season);
  const compLabels = { climate_soil: 'Climate & soil', rainfall_fit: 'Rainfall fit', prominence: 'Prominence', yield_stability: 'Yield stability', resource_efficiency: 'Resource efficiency' };
  return (
    <section>
      <SectionHeader icon="leaderboard" title="Crop suitability rankings" subtitle={`Computed from ${s.year_basis} observed data. Hover a score for its components.`} />
      <details className="mb-3 text-xs text-on-surface-variant bg-surface-container-low rounded-lg p-3">
        <summary className="cursor-pointer font-semibold">How the score is calculated</summary>
        <p className="mt-2">{s.method}</p>
      </details>
      <div className="mb-3">
        <Select label="Season" value={season} onChange={setSeason}
          options={[{ value: 'all', label: 'All seasons' }, ...['Kharif', 'Rabi', 'Summer'].map((x) => ({ value: x, label: x }))]} />
      </div>
      <div className="overflow-x-auto bg-surface-container-lowest rounded-xl border border-outline-variant/30">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-on-surface-variant bg-surface-container-low">
              {['Rank', 'Crop', 'Season', 'Suitability', 'Expected yield', 'Historical yield', 'Water need', 'Cost', 'Env. impact', 'Area share', 'Production trend'].map((h) => (
                <th key={h} scope="col" className="py-2 px-3 font-semibold whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.crop}-${r.season}`} className="border-t border-outline-variant/30">
                <td className="py-2 px-3 font-bold">#{season === 'all' ? r.rank : r.season_rank}</td>
                <td className="py-2 px-3 font-semibold">{r.crop}</td>
                <td className="py-2 px-3">{r.season}</td>
                <td className="py-2 px-3 min-w-[140px]" title={Object.entries(r.components).map(([k, v]) => `${compLabels[k]}: ${v === null ? 'n/a' : v}`).join('\n')}>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-2 bg-surface-variant rounded-full overflow-hidden" aria-hidden="true">
                      <div className="h-full bg-primary rounded-full" style={{ width: `${r.score}%` }}></div>
                    </div>
                    <span className="font-semibold w-10 text-right">{r.score}</span>
                  </div>
                </td>
                <td className="py-2 px-3 whitespace-nowrap">{r.expected_yield_t_ha} t/ha</td>
                <td className="py-2 px-3 whitespace-nowrap">{show(r.historical_mean_yield_t_ha, ' t/ha', 2)}</td>
                <td className="py-2 px-3 whitespace-nowrap">{r.water_req_mm} mm</td>
                <td className="py-2 px-3 whitespace-nowrap">₹{formatNumber(r.cost_rs_ha)}/ha</td>
                <td className="py-2 px-3 whitespace-nowrap">{r.env_impact_per_ha}/ha</td>
                <td className="py-2 px-3 whitespace-nowrap">{show(r.mean_area_share_pct, '%', 1)}</td>
                <td className="py-2 px-3">{r.production_trend ?? NA}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function MarketSection({ intel }) {
  const mk = intel.market;
  const crops = mk.crops || [];
  const [crop, setCrop] = useState(crops[0]?.crop || '');
  if (!mk.available) return <section><SectionHeader icon="payments" title="Market intelligence" /><p className="italic text-sm text-on-surface-variant">{NA}</p></section>;
  const sel = crops.find((c) => c.crop === crop) || crops[0];
  const years = Object.keys(sel.prices_by_year).map(Number);
  return (
    <section>
      <SectionHeader icon="payments" title="Market intelligence" />
      <p className="mb-3 text-xs bg-secondary-fixed/30 text-on-surface rounded-lg px-3 py-2 flex gap-2">
        <span className="material-symbols-outlined text-[16px]" aria-hidden="true">history</span>{mk.note}
      </p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <ChartCard title={`Historical price – ${sel.crop}`} subtitle="₹ per quintal, from the dataset."
          actions={<Select label="Crop" value={sel.crop} onChange={setCrop} options={crops.map((c) => ({ value: c.crop, label: c.crop }))} />}
          table={{ columns: [{ key: 'crop', label: 'Crop' }, { key: 'mean_rs_qtl', label: 'Mean ₹/qtl' },
            { key: 'trend', label: 'Change', format: (t) => (t ? `${t.change_pct > 0 ? '+' : ''}${t.change_pct}%` : NA) },
            { key: 'trend', label: 'Variability', format: (t) => (t ? `${t.variability} (CV ${t.cv})` : NA) }], rows: crops }}>
          <LineChart ariaLabel={`Price of ${sel.crop}`} xValues={years} unit=" ₹/qtl" digits={0} minSpan={(sel.mean_rs_qtl || 0) * 0.5}
            series={[{ id: sel.crop, label: sel.crop, emphasis: true, points: years.map((y) => ({ x: y, y: sel.prices_by_year[y] })) }]} />
        </ChartCard>
        <div className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4 grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-xs text-on-surface-variant font-semibold uppercase tracking-wide mb-2">Strongest price growth</p>
            <ul className="space-y-1">{mk.strongest_price_growth.map((g) => <li key={g.crop} className="flex justify-between"><span>{g.crop}</span><b>{g.change_pct > 0 ? '+' : ''}{g.change_pct}%</b></li>)}</ul>
          </div>
          <div>
            <p className="text-xs text-on-surface-variant font-semibold uppercase tracking-wide mb-2">Weakest price growth</p>
            <ul className="space-y-1">{mk.weakest_price_growth.map((g) => <li key={g.crop} className="flex justify-between"><span>{g.crop}</span><b>{g.change_pct > 0 ? '+' : ''}{g.change_pct}%</b></li>)}</ul>
          </div>
        </div>
      </div>
    </section>
  );
}

export function InsightsSection({ insights }) {
  return (
    <section>
      <SectionHeader icon="lightbulb" title="Agricultural insights" subtitle="Generated from the observed records; hover an insight to see its source." />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {insights.map((i) => (
          <div key={i.id} className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4" title={`Source: ${i.source}\nEvidence: ${JSON.stringify(i.evidence)}`}>
            <p className="font-semibold text-sm text-on-surface">{i.title}</p>
            <p className="text-sm text-on-surface-variant mt-1">{i.detail}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
