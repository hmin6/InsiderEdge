import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { renderToStaticMarkup } from 'react-dom/server';
import { QuantitativeCoverage } from './QuantitativeCoverage';
import type { QuantitativeCoverageData } from '../types/api';

const data: QuantitativeCoverageData = {
  status: 'descriptive_only', purchase_count: 1, purchase_value: 0,
  information_date: '2024-01-02', partial_index: null, coverage_weight: 0,
  available_components: [], missing_components: ['A', 'C', 'M', 'S', 'D'],
  calculation_method: 'observed_weight_renormalization', reasons: ['missing_source_chronology'],
  provenance_limitations: ['Caller-attested; not independently authenticated'],
};
test('descriptive data displays zero, cutoff and provenance without a composite', () => {
  const html = renderToStaticMarkup(<QuantitativeCoverage data={data} />);
  for (const text of ['Available quantitative data', 'Qualifying purchases: 1', '$0.00',
    '2024-01-02', 'not an InsiderEdge Score or ML prediction', 'Score methodology and evidence',
    'not independently authenticated']) assert.ok(html.includes(text));
});
test('unavailable does not fabricate metrics', () => {
  const html = renderToStaticMarkup(<QuantitativeCoverage data={{...data, status: 'unavailable', purchase_count: null, purchase_value: null}} />);
  assert.match(html, /Quantitative evidence unavailable/);
  assert.doesNotMatch(html, /Qualifying purchases:|Qualifying purchase value:/);
  assert.equal(renderToStaticMarkup(<QuantitativeCoverage />), '');
});
test('Radar removes summary column only, preserves canonical sorting and detail explanation', () => {
  const radar = readFileSync(new URL('../pages/RadarPage.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(radar, /<th>Signal Summary<\/th>|item.insider_signal_summary/);
  for (const label of ['Company', 'Status', 'Anomaly', 'Activity', 'Dislocation', 'Model probability', 'Research priority score']) assert.ok(radar.includes(label));
  assert.match(radar, /colSpan=\{7\}/);
  assert.doesNotMatch(radar, /partial_index/);
  const company = readFileSync(new URL('../pages/CompanyPage.tsx', import.meta.url), 'utf8');
  assert.match(company, /insider_signal_summary/);
});

test('provisional index has separate name, coverage and unvalidated disclosure', () => {
  const html = renderToStaticMarkup(<QuantitativeCoverage data={{...data, status: 'provisional',
    partial_index: 42.857142857, coverage_weight: .7, available_components: ['A', 'M', 'D'], missing_components: ['C', 'S']}} />);
  for (const text of ['Provisional Index', '42.86', '70.00%', 'C, S', 'less reliable',
    'Not directly comparable', 'No components were imputed']) assert.ok(html.includes(text));
  assert.doesNotMatch(html, /calibrated probability/);
});

test('estimated methodology is expandable and discloses fixed heuristic assumptions', () => {
  const html = renderToStaticMarkup(<QuantitativeCoverage data={{...data, estimated_activity_index: 6}} />);
  for (const text of ['<details', 'Score methodology and evidence', '6.00', '$100 million', 'five transactions', '70%/30%', 'not a validated historical distribution', 'Form 4 NONDERIV_TRANS']) assert.ok(html.includes(text));
  assert.doesNotMatch(html, /<details open/);
});
