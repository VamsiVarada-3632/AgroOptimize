import React from 'react';
import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import salem from '../../__fixtures__/district-salem.json';
import soilSalem from '../../__fixtures__/soil-master-salem.json';
import soilChennai from '../../__fixtures__/soil-master-chennai.json';
import {
  ClimateSection, CropPerformanceSection, InsightsSection, MarketSection, NA, OverviewSection,
  SoilHealthCardSection, SoilSection, SuitabilitySection, WaterSection,
} from './DistrictSections';

const text = (html) => html.replace(/<[^>]+>/g, ' ').replace(/&#x27;/g, "'").replace(/&amp;/g, '&');
const clean = (html) => expect(text(html)).not.toMatch(/undefined|NaN|\[object Object\]/);

describe('District sections render the real payload', () => {
  it('overview shows backend values and marks the missing zone', () => {
    const html = renderToString(<OverviewSection intel={salem} />);
    clean(html);
    // the official datasets publish no agro-climatic zone, soil type or temperature
    expect(salem.overview.agricultural_zone).toBeNull();
    expect(text(html).split(NA).length - 1).toBeGreaterThanOrEqual(3);
    expect(text(html)).toContain(salem.overview.major_crops[0].crop);
    expect(text(html)).toContain(String(salem.coverage.observed_years[0]));
  });

  it('climate section draws charts and the backend observations', () => {
    const html = renderToString(<ClimateSection intel={salem} insights={salem.insights} />);
    clean(html);
    // rainfall charts are drawn; temperature has no official data
    expect(html.split('role="img"').length - 1).toBeGreaterThanOrEqual(3);
    expect(text(html)).toContain(NA);
    const obs = salem.insights.find((i) => i.id === 'rainfall-normal');
    expect(text(html)).toContain(obs.detail.slice(0, 40));
  });

  it('soil, water, crops, suitability, market and insights render without gaps', () => {
    for (const el of [
      <SoilSection key="SoilSection" intel={salem} />, <WaterSection key="WaterSection" intel={salem} />, <CropPerformanceSection key="CropPerformanceSection" intel={salem} />,
      <SuitabilitySection key="SuitabilitySection" intel={salem} />, <MarketSection key="MarketSection" intel={salem} />, <InsightsSection key="InsightsSection" insights={salem.insights} />,
    ]) {
      clean(renderToString(el));
    }
  });

  it('suitability table lists every ranked crop with its score', () => {
    const t = text(renderToString(<SuitabilitySection key="SuitabilitySection" intel={salem} />));
    salem.suitability.rankings.forEach((r) => {
      expect(t).toContain(r.crop);
      expect(t).toContain(String(r.score));
    });
  });

  it('market section states the prices are historical, not live', () => {
    const t = text(renderToString(<MarketSection key="MarketSection" intel={salem} />));
    expect(t.toLowerCase()).toContain('not live');
  });
});

describe('Missing data', () => {
  const missing = {
    ...salem,
    soil: { available: false, note: NA },
    water: { available: false, note: NA },
    crops: { available: false, note: NA, records: [], trends: [] },
    suitability: { available: false, note: NA, rankings: [] },
    market: { ...salem.market, available: false, crops: [] },
  };

  it.each([
    ['soil', <SoilSection key="SoilSection" intel={missing} />],
    ['water', <WaterSection key="WaterSection" intel={missing} />],
    ['crops', <CropPerformanceSection key="CropPerformanceSection" intel={missing} />],
    ['suitability', <SuitabilitySection key="SuitabilitySection" intel={missing} />],
    ['market', <MarketSection key="MarketSection" intel={missing} />],
  ])('%s section says data is not available', (_, el) => {
    const html = renderToString(el);
    clean(html);
    expect(text(html)).toContain(NA);
  });

  it('overview copes with empty lists and null values', () => {
    const o = { ...salem.overview, agricultural_area_ha: null, average_temperature_c: null, soil_types: [],
      primary_irrigation_sources: [], major_crops: [] };
    const html = renderToString(<OverviewSection intel={{ ...salem, overview: o }} />);
    clean(html);
    expect(text(html).split(NA).length - 1).toBeGreaterThanOrEqual(5);
  });
});

describe('Soil Health Card section', () => {
  it('lists every parameter with its dominant class, shares and sample count', () => {
    const t = text(renderToString(<SoilHealthCardSection record={soilSalem} />));
    clean(renderToString(<SoilHealthCardSection record={soilSalem} />));
    expect(t).toContain(`${soilSalem.cycle} cycle`);
    for (const [key, label] of [['ph', 'Soil pH'], ['organic_carbon', 'Organic Carbon'], ['nitrogen', 'Nitrogen (N)'],
      ['phosphorus', 'Phosphorus (P)'], ['potassium', 'Potassium (K)'], ['electrical_conductivity', 'Soil Salinity']]) {
      expect(t).toContain(label);
      expect(t).toContain(soilSalem[key].dominant_class);
    }
    expect(t).toContain('Micronutrients, share of samples deficient');
    expect(t).toMatch(new RegExp(`Soil type:\\s+${NA}`));
  });

  it('says official data is not available for a district without a record or on an error', () => {
    expect(soilChennai.available).toBe(false);
    expect(text(renderToString(<SoilHealthCardSection record={soilChennai} />))).toContain(NA);
    expect(text(renderToString(<SoilHealthCardSection record={null} error={new Error('down')} />))).toContain(NA);
  });
});
