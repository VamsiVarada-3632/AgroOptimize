// Re-records the test fixtures in src/__fixtures__ from a running backend, so
// the frontend tests always exercise real official-data responses.
//
//   AGROOPTIMIZE_RESULTS_DIR=/tmp/agro_results uvicorn app.main:app --port 8000
//   node scripts/refresh-fixtures.mjs [http://localhost:8000]
//
// One Salem Rabi run, ranked with the 'profit' profile, is saved (in the
// backend's results folder) to obtain the explanation and TOPSIS fixtures.
import { writeFile } from 'node:fs/promises';

const BASE = (process.argv[2] || 'http://localhost:8000').replace(/\/+$/, '');
const OUT = new URL('../src/__fixtures__/', import.meta.url);

async function call(path, body) {
  const res = await fetch(`${BASE}${path}`, body === undefined ? undefined : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status} ${await res.text()}`);
  return res.json();
}

async function save(name, data) {
  await writeFile(new URL(name, OUT), `${JSON.stringify(data)}\n`);
  console.log('wrote', name);
}

const base = { location: 'Salem', season: 'Rabi', total_land_ha: 5, preference: 'balanced' };

await save('district-salem.json', await call('/api/district-intelligence/salem'));

await save('simulation-drought.json', await call('/api/simulations/run', {
  base,
  scenario: {
    rainfall_change_pct: -20, water_availability: 'low', fertilizer_cost_change_pct: 0, market_price: 'stable',
    priorities: { yield: 30, cost: 20, water: 40, env: 10 },
  },
}));

// A budget below every plan's cost: the scenario side has no feasible plan.
await save('simulation-infeasible.json', await call('/api/simulations/run', {
  base,
  scenario: { rainfall_change_pct: 0, water_availability: 'current', fertilizer_cost_change_pct: 0, market_price: 'stable', budget_rs: 20000 },
}));

const run = await call('/api/farm-plans', { ...base, profile: 'profit', save_results: true, client_id: 'fixture-refresh' });
const explanation = await call(`/api/results/${run.run_id}/explanation?rank=1`);
await save('fuzzy-reasoning-salem.json', explanation.fuzzy_reasoning);
await save('crop-evidence-salem.json', explanation.crop_evidence);
await save('topsis-explanation-salem.json', explanation.topsis);
await save('topsis-rerank-salem.json', await call(`/api/results/${run.run_id}/topsis?profile=profit&compare=true`));
