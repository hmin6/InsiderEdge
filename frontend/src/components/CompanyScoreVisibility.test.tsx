import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { CompanyScore } from './ResearchStates';
import { InsiderEdgeScore } from './InsiderEdgeScore';
import { DEV_MOCK_COMPANY, DEV_MOCK_RADAR } from '../api/mocks';
import type { QuantitativeCoverageData } from '../types/api';
const coverage: QuantitativeCoverageData = {status: 'descriptive_only', purchase_count: 1, purchase_value: 0,
  information_date: '2024-01-01', partial_index: null, estimated_activity_index: 6, coverage_weight: 0,
  available_components: [], missing_components: ['A','C','M','S','D'], calculation_method: 'observed_weight_renormalization', reasons: [], provenance_limitations: []};
test('company without Signal displays estimate and source zero, not fabricated components', () => {
  const html = renderToStaticMarkup(<CompanyScore data={{...DEV_MOCK_COMPANY, latest_signal: null,
    latest_public_event_day: '2024-01-02', quantitative_coverage: coverage}} />);
  for (const text of ['Estimated Activity Index','6.00 out of 100', '$0.00', 'Qualifying purchases: 1', 'Model components not evaluated.', 'Score methodology and evidence']) assert.ok(html.includes(text), text);
  assert.doesNotMatch(html, /class="ie-score-component"|% probability/);
});
test('provisional headline preserves observed partial components', () => {
  const html = renderToStaticMarkup(<InsiderEdgeScore evidence={{...DEV_MOCK_RADAR.items[0],
    score_status: 'insufficient_data', insider_edge_score: null, activity_score: 0,
    quantitative_coverage: {...coverage, status: 'provisional', partial_index: 42.5}}} />);
  assert.match(html, /Provisional Index/);
  assert.match(html, /42.50 out of 100/);
  assert.match(html, />0.00<\/strong>/);
});
test('estimate zero remains visible, absent estimate never manufactured', () => {
  const render = (value: number | null) => renderToStaticMarkup(<CompanyScore data={{...DEV_MOCK_COMPANY,
    latest_signal: null, latest_public_event_day: '2024-01-02', quantitative_coverage: {...coverage, estimated_activity_index: value}}} />);
  assert.match(render(0), /0.00 out of 100/);
  assert.match(render(null), /Score unavailable/);
  assert.doesNotMatch(render(null), /class="ie-score-fill"/);
});
