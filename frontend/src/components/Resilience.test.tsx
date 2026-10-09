import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { rankRadar, numeric, StatisticsEvidence, PredictionEvidence } from './ResearchStates';
import { mockCompany } from '../api/client';
import { ApiError, getJson } from '../api/http';
import { DEV_MOCK_RADAR } from '../api/mocks';
import type { StatisticsResponse } from '../types/research';

test('ranking keeps missing scores last, preserves zero, and does not mutate API data', () => {
  const base = DEV_MOCK_RADAR.items[0];
  const input = [{ ...base, ticker: 'MISSING', insider_edge_score: null }, { ...base, ticker: 'ZERO', insider_edge_score: 0 }, { ...base, ticker: 'HIGH', insider_edge_score: 95 }];
  assert.deepEqual(rankRadar(input).map(item => item.ticker), ['HIGH', 'ZERO', 'MISSING']);
  assert.equal(input[0].insider_edge_score, null);
  assert.equal(numeric(null), 'Unavailable');
  assert.equal(numeric(0), '0');
});
test('mock company recognizes normalized known ticker and simulates unknown ticker 404', () => {
  assert.equal(mockCompany('aapl').ticker, 'AAPL');
  assert.throws(() => mockCompany('NOTREAL'), error => error instanceof ApiError && error.status === 404);
});
test('HTTP failures retain status without exposing raw server details', async () => {
  const fetcher: typeof fetch = async () => new Response('private stack trace', { status: 404 });
  await assert.rejects(getJson('http://backend/company', undefined, fetcher), error => error instanceof ApiError && error.status === 404 && !error.message.includes('stack'));
});
test('recent CAR horizons stay unavailable while realized zero CAR5 remains visible', () => {
  const data: StatisticsResponse = { ticker: 'AAPL', research_event_id: 'test', public_event_day: '2026-10-09', anomaly: { score: null, status: 'insufficient_data' }, activity: { score: 0, status: 'complete' }, event_study: { car5: 0, car30: null, car90: null, status: 'partial' }, statistical_validation: { comparable_event_count: null, cohort_definition: null, mean_car30: null, bootstrap_ci_95: null, randomization_p_value: null, statistical_score: null, status: 'insufficient_data' } };
  const html = renderToStaticMarkup(<StatisticsEvidence data={data} />);
  assert.match(html, /Insufficient anomaly history/);
  assert.match(html, /CAR5<\/dt><dd>0.00%/);
  assert.match(html, /CAR30<\/dt><dd>Unavailable/);
  assert.match(html, /CAR90<\/dt><dd>Unavailable/);
  assert.match(html, /Future CAR is not yet known/);
});
test('missing model probability has an explicit state', () => {
  const html = renderToStaticMarkup(<PredictionEvidence data={{ ticker: 'AAPL', research_event_id: 'test', model_name: null, outperformance_probability: null, status: 'insufficient_data' }} />);
  assert.match(html, /Model prediction unavailable/);
  assert.doesNotMatch(html, /0.00%/);
});
