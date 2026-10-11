import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { readFileSync } from 'node:fs';
import { ResearchPriorityValue } from './ResearchPriorityValue';
import type { QuantitativeCoverageData } from '../types/api';
const coverage: QuantitativeCoverageData = { status: 'provisional', partial_index: 40,
  estimated_activity_index: 60, purchase_count: 2, purchase_value: 10000,
  information_date: '2024-01-01', coverage_weight: .55, available_components: ['A', 'M'],
  missing_components: ['C', 'S', 'D'], calculation_method: 'observed_weight_renormalization', reasons: [], provenance_limitations: [] };
test('compact precedence preserves zero and canonical separation', () => {
  const render = (score: number | null, status: string, data = coverage) => renderToStaticMarkup(<ResearchPriorityValue score={score} status={status} coverage={data} />);
  assert.match(render(0, 'complete'), /0.00.*<\/strong>.*Complete/);
  assert.doesNotMatch(render(0, 'complete'), /40.00|60.00/);
  assert.match(render(99, 'partial'), /40.00.*Provisional/);
  assert.match(render(null, 'insufficient_data', {...coverage, partial_index: null}), /60.00.*Estimated Activity/);
  assert.match(render(null, 'insufficient_data', {...coverage, partial_index: null, estimated_activity_index: 0}), /0.00/);
  assert.match(render(null, 'insufficient_data', {...coverage, partial_index: null, estimated_activity_index: null}), /—/);
  assert.doesNotMatch(render(null, 'insufficient_data'), /Qualifying purchases|<p>|<details>/);
});
test('Radar uses compact value and retains raw canonical sorting', () => {
  const source = readFileSync(new URL('../pages/RadarPage.tsx', import.meta.url), 'utf8');
  assert.match(source, /<ResearchPriorityValue score=\{item.insider_edge_score\}/);
  assert.doesNotMatch(source, /<QuantitativeCoverage|estimated_activity_index|partial_index|<th>Signal Summary/);
});
