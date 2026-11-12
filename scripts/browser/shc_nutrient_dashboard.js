// Run in a browser tab at https://soilhealth.dac.gov.in/ (the official portal's own public GraphQL API).
// Reproduces data/official/raw/soil_health_tn.csv (cycle 2024-25, primary scheme 660f941a5c8405ca8375c7c6).
const gql = async (query, variables) => (await (await fetch('https://soilhealth4.dac.gov.in/', {method: 'POST',
  headers: {'Content-Type': 'application/json'}, body: JSON.stringify({query, variables})})).json());
const tn = (await gql('query GetState { getState }', {})).data.getState.find(x => /TAMIL/i.test(x.name));
const q = 'query N($state: ID, $district: ID, $block: ID, $village: ID, $cycle: String, $count: Boolean,$scheme: String) { getNutrientDashboardForPortal(state: $state, district: $district, block: $block, village: $village, cycle: $cycle, count: $count,scheme: $scheme) }';
const rows = (await gql(q, {state: tn._id})).data.getNutrientDashboardForPortal
  .filter(r => r.cycle === '2024-25' && r.scheme === '660f941a5c8405ca8375c7c6');
// columns: n,p,k High/Medium/Low; S Sufficient/Deficient; OC H/M/L; pH Acidic/Neutral/Alkaline; EC Saline/NonSaline; Fe,Zn,Cu,B,Mn Sufficient/Deficient
