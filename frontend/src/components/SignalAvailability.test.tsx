import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { SignalAvailability } from './SignalAvailability';
import { CompanyScore, rankRadar } from './ResearchStates';
import { DEV_MOCK_RADAR, DEV_MOCK_COMPANY } from '../api/mocks';
import type { AvailabilityStatus } from '../types/api';

for (const [status, description] of [
  ['not_scored', 'No score has been generated'],
  ['insufficient_data', 'The scoring process ran'],
  ['partial', 'approved subset'],
  ['complete', 'All required components'],
] as const) test(`availability renders ${status} accurately`, () => {
  const html = renderToStaticMarkup(<SignalAvailability evidence={{ ...DEV_MOCK_RADAR.items[0], availability_status: status, score_status: status === 'not_scored' ? 'insufficient_data' : status, unavailable_components: status === 'complete' ? [] : status === 'partial' ? ['S'] : ['C', 'S'] }} />);
  assert.ok(html.includes(description));
  const labels = { not_scored: 'Not scored', insufficient_data: 'Insufficient data', partial: 'Partial evidence', complete: 'Complete evidence' };
  assert.ok(html.includes(labels[status]));
  if (status === 'not_scored' || status === 'complete') assert.doesNotMatch(html, /Unavailable components/);
  else assert.ok(html.includes(status === 'partial' ? 'Unavailable components: S' : 'Unavailable components: C, S'));
});
test('legacy payload does not claim scoring ran or infer not_scored from null score', () => {
  const html = renderToStaticMarkup(<SignalAvailability evidence={{ ...DEV_MOCK_RADAR.items[0], insider_edge_score: null, availability_status: undefined, score_status: 'insufficient_data' }} />);
  assert.match(html, /Insufficient data/);
  assert.doesNotMatch(html, /Not scored|The scoring process ran/);
});
test('company distinguishes no events from an event not scored', () => {
  const html = renderToStaticMarkup(<CompanyScore data={{ ...DEV_MOCK_COMPANY, latest_signal: null }} />);
  assert.match(html, /Not scored/);
  assert.doesNotMatch(html, /Unavailable components|The scoring process ran/);
  const empty = renderToStaticMarkup(<CompanyScore data={{ ...DEV_MOCK_COMPANY, latest_signal: null, latest_public_event_day: null }} />);
  assert.match(empty, /No research events/);
  assert.doesNotMatch(empty, /Not scored/);
});
test('availability never changes numerical ranking or null handling', () => {
  const base = DEV_MOCK_RADAR.items[0];
  const rows = [
    { ...base, ticker: 'UNSCORED', availability_status: 'not_scored' as AvailabilityStatus, insider_edge_score: null },
    { ...base, ticker: 'ZERO', availability_status: 'complete' as AvailabilityStatus, insider_edge_score: 0 },
    { ...base, ticker: 'PARTIAL', availability_status: 'partial' as AvailabilityStatus, insider_edge_score: 42.125 },
  ];
  assert.deepEqual(rankRadar(rows).map(x => x.ticker), ['PARTIAL', 'ZERO', 'UNSCORED']);
  assert.equal(rows[0].ticker, 'UNSCORED');
});

for (const availability_status of [undefined, null]) test(`legacy availability ${availability_status} stays conservative`, () => {
  const html = renderToStaticMarkup(<SignalAvailability evidence={{ ...DEV_MOCK_RADAR.items[0], availability_status, insider_edge_score: null, score_status: 'insufficient_data' }} />);
  assert.match(html, /Insufficient data/);
  assert.doesNotMatch(html, /Not scored|The scoring process ran/);
});
for (const status of ['complete', 'partial', 'insufficient_data'] as const) test(`company renders persisted ${status} without duplicate status prose`, () => {
  const evidence = { ...DEV_MOCK_RADAR.items[0], availability_status: status, score_status: status,
    insider_edge_score: status === 'insufficient_data' ? null : 42.125,
    statistical_score: status === 'partial' ? null : 10,
    unavailable_components: status === 'complete' ? [] : status === 'partial' ? ['S'] : ['C'],
  };
  const html = renderToStaticMarkup(<CompanyScore data={{ ...DEV_MOCK_COMPANY, latest_signal: evidence }} />);
  const message = status === 'complete' ? 'All required components are available' : status === 'partial' ? 'approved subset' : 'The scoring process ran';
  assert.ok(html.includes(message));
  assert.equal(html.split(message).length - 1, 1);
  assert.doesNotMatch(html, /No score has been generated|Some evidence is unavailable|Insufficient data · Evidence/);
  if (status === 'partial') assert.match(html, /Unavailable components: S/);
  if (status !== 'insufficient_data') assert.match(html, /42.13 out of 100/);
});

test('Radar search and both sorting directions preserve raw values across availability states', () => {
  const base = DEV_MOCK_RADAR.items[0];
  const rows = [
    { ...base, ticker: 'NS', company_name: 'Shared Unscored', availability_status: 'not_scored' as const, score_status: 'insufficient_data' as const, insider_edge_score: null },
    { ...base, ticker: 'ID', company_name: 'Shared Insufficient', availability_status: 'insufficient_data' as const, score_status: 'insufficient_data' as const, insider_edge_score: null },
    { ...base, ticker: 'PT', company_name: 'Shared Partial', availability_status: 'partial' as const, score_status: 'partial' as const, insider_edge_score: 42.121, unavailable_components: ['S'] },
    { ...base, ticker: 'CP', company_name: 'Shared Complete', availability_status: 'complete' as const, score_status: 'complete' as const, insider_edge_score: 42.124 },
    { ...base, ticker: 'ZR', company_name: 'Shared Zero', availability_status: 'complete' as const, score_status: 'complete' as const, insider_edge_score: 0 },
  ];
  const original = JSON.stringify(rows);
  for (const [direction, expected] of [['asc', ['ZR', 'PT', 'CP', 'NS', 'ID']], ['desc', ['CP', 'PT', 'ZR', 'NS', 'ID']]] as const) {
    const result = rankRadar(rows, { query: ' SHARED ', sortKey: 'priority', direction });
    assert.deepEqual(result.map(row => row.ticker), expected);
    const html = renderToStaticMarkup(<>{result.map(row => <SignalAvailability key={row.ticker} evidence={row} />)}</>);
    for (const label of ['Not scored', 'Insufficient data', 'Partial evidence', 'Complete evidence']) assert.ok(html.includes(label));
  }
  // Search is a substring match across ticker and company name: 'ns' also matches Insufficient.
  assert.deepEqual(rankRadar(rows, { query: 'ns' }).map(item => item.ticker), ['NS', 'ID']);
  for (const row of rows.slice(1)) assert.deepEqual(rankRadar(rows, { query: row.ticker.toLowerCase() }).map(item => item.ticker), [row.ticker]);
  assert.deepEqual(rankRadar(rows, { query: 'not found' }), []);
  assert.deepEqual(rankRadar(rows, { sortKey: 'company' }).map(row => row.ticker), ['CP', 'ID', 'NS', 'PT', 'ZR']);
  assert.deepEqual(rankRadar(rows, { sortKey: 'status' }).map(row => row.ticker), ['CP', 'ZR', 'PT', 'NS', 'ID']);
  assert.equal(JSON.stringify(rows), original);
});
test('all metric sorting uses raw values and leaves unavailable values last in both directions', () => {
  const base = DEV_MOCK_RADAR.items[0];
  const fields = { anomaly: 'anomaly_score', activity: 'activity_score', dislocation: 'dislocation_score', model_prob: 'ml_outperformance_probability' } as const;
  for (const [sortKey, field] of Object.entries(fields)) {
    const rows = [
      { ...base, ticker: 'MISSING', [field]: null },
      { ...base, ticker: 'LOW', [field]: .42121 },
      { ...base, ticker: 'HIGH', [field]: .42124 },
      { ...base, ticker: 'ZERO', [field]: 0 },
    ];
    assert.deepEqual(rankRadar(rows, { sortKey: sortKey as keyof typeof fields, direction: 'asc' }).map(row => row.ticker), ['ZERO', 'LOW', 'HIGH', 'MISSING']);
    assert.deepEqual(rankRadar(rows, { sortKey: sortKey as keyof typeof fields, direction: 'desc' }).map(row => row.ticker), ['HIGH', 'LOW', 'ZERO', 'MISSING']);
  }
});
