import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { formatNumber, formatPercent, formatFractionPercent, formatCurrency, formatCount, formatPValue } from '../utils/format';
import { rankRadar, StatisticsEvidence } from './ResearchStates';
import { DEV_MOCK_RADAR, DEV_MOCK_STATISTICS } from '../api/mocks';

test('measurements round for display with grouping, signs and trailing zeros', () => {
  for (const [value, expected] of [[83.7462918, '83.75'], [12.999999, '13.00'], [-2.567891, '-2.57'], [0, '0.00'], [-0, '0.00'], [-.0001, '0.00'], [1234567.891, '1,234,567.89']] as const) assert.equal(formatNumber(value), expected);
  assert.equal(formatCount(1234), '1,234');
});
test('fractional units scale once and percentage points stay on their original scale', () => {
  assert.equal(formatFractionPercent(.783456), '78.35%');
  assert.equal(formatPercent(78.3456), '78.35%');
  assert.equal(formatFractionPercent(-.02567891), '-2.57%');
  assert.equal(formatFractionPercent(-0), '0.00%');
});
test('missing and nonfinite measurements never become zero', () => {
  for (const format of [formatNumber, formatPercent, formatFractionPercent, formatCurrency, formatCount, formatPValue]) {
    for (const value of [null, undefined, NaN, Infinity, -Infinity]) assert.equal(format(value), 'Unavailable');
  }
});
test('currency uses cents, grouping and clean signed zero', () => {
  assert.equal(formatCurrency(153.98765), '$153.99');
  assert.equal(formatCurrency(-1234.567), '-$1,234.57');
  assert.equal(formatCurrency(-.00001), '$0.00');
});
test('small positive p-values remain distinguishable from zero', () => {
  assert.equal(formatPValue(.00000123456), '1.23e-6');
  assert.equal(formatPValue(.0099), '9.90e-3');
  assert.equal(formatPValue(.01), '0.01');
  assert.equal(formatPValue(0), '0.00');
});
test('radar sorts by original precision even when formatted scores tie', () => {
  const base = DEV_MOCK_RADAR.items[0];
  const rows = [{ ...base, ticker: 'LOW', insider_edge_score: 83.741 }, { ...base, ticker: 'HIGH', insider_edge_score: 83.744 }];
  assert.equal(formatNumber(rows[0].insider_edge_score), formatNumber(rows[1].insider_edge_score));
  assert.deepEqual(rankRadar(rows).map(row => row.ticker), ['HIGH', 'LOW']);
  assert.equal(rows[0].insider_edge_score, 83.741);
});
test('statistical panels distinguish counts, percentages and tiny p-values', () => {
  const data = { ...DEV_MOCK_STATISTICS, statistical_validation: { ...DEV_MOCK_STATISTICS.statistical_validation, comparable_event_count: 1234, mean_car30: -.02567891, randomization_p_value: .00000123456 } };
  const html = renderToStaticMarkup(<StatisticsEvidence data={data} />);
  assert.match(html, /Comparable events: 1,234/);
  assert.match(html, /Mean CAR30: -2.57%/);
  assert.match(html, /Randomization p-value: 1.23e-6/);
  assert.equal(data.statistical_validation.mean_car30, -.02567891);
});
