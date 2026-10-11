import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { readFileSync } from 'node:fs';
import { RadarComponentValues } from './RadarComponentValues';
import { SignalAvailability } from './SignalAvailability';
import { ResearchPriorityValue } from './ResearchPriorityValue';
import { rankRadar } from './ResearchStates';
import { DEV_MOCK_RADAR } from '../api/mocks';
const base = DEV_MOCK_RADAR.items[0];
test('Not scored presents one unevaluated message without hiding a supported estimate', () => {
  const item = {...base, availability_status: 'not_scored' as const, score_status: 'insufficient_data' as const,
    insider_edge_score: null, anomaly_score: null, activity_score: null, statistical_score: null,
    dislocation_score: null, ml_outperformance_probability: null};
  const html = renderToStaticMarkup(<table><tbody><tr><td><SignalAvailability evidence={item} compact /></td>
    <RadarComponentValues item={item} /><td><ResearchPriorityValue score={null} status={item.score_status}
      coverage={{status: 'descriptive_only', partial_index: null, estimated_activity_index: 0,
      purchase_count: 1, purchase_value: 0, information_date: '2024-01-01', coverage_weight: 0,
      available_components: [], missing_components: ['A','C','M','S','D'], calculation_method: 'observed_weight_renormalization', reasons: [], provenance_limitations: []}} /></td></tr></tbody></table>);
  assert.match(html, /Not scored/);
  assert.match(html, /colSpan="5"|colspan="5"/);
  assert.match(html, /Model components not evaluated/);
  assert.match(html, /0.00/);
  assert.match(html, /Estimated Activity/);
  assert.doesNotMatch(html, /Unavailable|No persisted Signal|five evaluated/);
});
test('evaluated components retain statistical zero and probability scale', () => {
  const html = renderToStaticMarkup(<table><tbody><tr><RadarComponentValues item={{...base,
    availability_status: 'complete', statistical_score: 0, ml_outperformance_probability: .25}} /></tr></tbody></table>);
  assert.equal((html.match(/<td/g) || []).length, 5);
  assert.match(html, />0.00</);
  assert.match(html, /25.00%/);
  assert.doesNotMatch(html, /not evaluated/);
});
test('statistical sorting uses raw scores and missing last in both directions', () => {
  const rows = [{...base, ticker: 'A', statistical_score: 1.001}, {...base, ticker: 'B', statistical_score: 1.002}, {...base, ticker: 'C', statistical_score: null}];
  assert.deepEqual(rankRadar(rows, {sortKey: 'statistical', direction: 'desc'}).map(x=>x.ticker), ['B','A','C']);
  assert.deepEqual(rankRadar(rows, {sortKey: 'statistical', direction: 'asc'}).map(x=>x.ticker), ['A','B','C']);
});
test('table headers and colspan include statistical evidence in correct position', () => {
  const source = readFileSync(new URL('../pages/RadarPage.tsx', import.meta.url), 'utf8');
  assert.match(source, /Activity<\/th>\s*<th[^>]*>Statistical Evidence<\/th>\s*<th[^>]*>Dislocation/);
  assert.match(source, /colSpan=\{8\}/);
  assert.match(source, /key: "statistical", label: "Statistical Evidence"/);
  assert.doesNotMatch(source, /Signal Summary/);
});
