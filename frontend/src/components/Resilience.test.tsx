import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { rankRadar, numeric, StatisticsEvidence, EventStudyEvidence, PredictionEvidence, CompanyScore } from './ResearchStates';
import { mockCompany } from '../api/client';
import { ApiError, getJson } from '../api/http';
import { DEV_MOCK_RADAR, DEV_MOCK_COMPANY, DEV_MOCK_STATISTICS, DEV_MOCK_PREDICTION } from '../api/mocks';
import type { StatisticsResponse } from '../types/research';

test('ranking keeps missing scores last, preserves zero, and does not mutate API data', () => {
  const base = DEV_MOCK_RADAR.items[0];
  const input = [{ ...base, ticker: 'MISSING', insider_edge_score: null }, { ...base, ticker: 'ZERO', insider_edge_score: 0 }, { ...base, ticker: 'HIGH', insider_edge_score: 95 }];
  assert.deepEqual(rankRadar(input).map(item => item.ticker), ['HIGH', 'ZERO', 'MISSING']);
  assert.equal(input[0].insider_edge_score, null);
  assert.equal(numeric(null), 'Unavailable');
  assert.equal(numeric(0), '0.00');
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
  const data: StatisticsResponse = { ...DEV_MOCK_STATISTICS, ticker: 'AAPL', research_event_id: 'test', public_event_day: '2026-10-09', anomaly: { ...DEV_MOCK_STATISTICS.anomaly, score: null, status: 'insufficient_data' }, activity: { ...DEV_MOCK_STATISTICS.activity, score: 0, status: 'complete' }, event_study: { car5: 0, car30: null, car90: null, status: 'partial' }, statistical_validation: { comparable_event_count: null, cohort_definition: null, mean_car30: null, bootstrap_ci_95: null, randomization_p_value: null, statistical_score: null, status: 'insufficient_data' } };
  const html = renderToStaticMarkup(<><StatisticsEvidence data={data} /><EventStudyEvidence data={data} /></>);
  assert.doesNotMatch(html, /Anomaly Score/);
  assert.match(html, /CAR5[\s\S]*?class="ie-metric-value">0.00%/);
  assert.doesNotMatch(html, /ie-metric-label[^>]*>CAR30/);
  assert.doesNotMatch(html, /ie-metric-label[^>]*>CAR90/);
  assert.match(html, /Future CAR is not yet known/);
});
test('missing model probability has no empty probability card', () => {
  const html = renderToStaticMarkup(<PredictionEvidence data={{ ...DEV_MOCK_PREDICTION, ticker: 'AAPL', research_event_id: 'test', model_name: null, outperformance_probability: null, status: 'insufficient_data' }} />);
  assert.doesNotMatch(html, /Outperformance Probability|Model prediction unavailable/);
  assert.doesNotMatch(html, /0.00%/);
});

test('complete statistics display diagnostics, market context and exact statuses', () => {
  const data: StatisticsResponse = {
    ...DEV_MOCK_STATISTICS,
    anomaly: { score: 0, mahalanobis_distance: 2.5, reference_population: 'sector', reference_count: 30, status: 'complete' },
    activity: { score: 0, recent_purchase_rate: 0, historical_purchase_rate: .1, rate_ratio: 0, buyers_30d: 0, reference_population: 'company', status: 'complete' },
    market: { stock_return_90d: -.2, sector_return_90d: .1, drawdown: 0, dislocation_score: 0, status: 'complete' },
  };
  const html = renderToStaticMarkup(<><StatisticsEvidence data={data} /><EventStudyEvidence data={data} /></>);
  for (const field of ['Mahalanobis Dist', 'Recent Rate', 'Historical Rate', 'Purchase Rate Ratio', 'Buyers (30d)', 'Market Dislocation Evidence', 'Stock Return (90d)', 'Sector Return (90d)', 'Drawdown', 'Dislocation Score']) assert.ok(html.includes(field), field);
  assert.match(html, /Mahalanobis Dist[\s\S]*?class="ie-metric-value">2.50/);
  assert.match(html, /Buyers \(30d\)[\s\S]*?class="ie-metric-value">0/);
  assert.match(html, /Stock Return \(90d\)[\s\S]*?class="ie-metric-value">-20.00%/);
  assert.match(html, /Drawdown[\s\S]*?class="ie-metric-value">0.00%/);
});

test('partial bootstrap evidence stays visible when randomization and combined score are unavailable', () => {
  const data: StatisticsResponse = { ...DEV_MOCK_STATISTICS, statistical_validation: {
    ...DEV_MOCK_STATISTICS.statistical_validation, mean_car30: 0,
    bootstrap_ci_95: { lower: -.02, upper: .03 }, randomization_p_value: null,
    statistical_score: null, status: 'partial',
  } };
  const html = renderToStaticMarkup(<><StatisticsEvidence data={data} /><EventStudyEvidence data={data} /></>);
  assert.match(html, /Mean CAR30[\s\S]*?class="ie-metric-value">0.00%/);
  assert.match(html, /-2.00% to 3.00%/);
  assert.doesNotMatch(html, /P-Value/);
  assert.doesNotMatch(html, /ie-metric-label[^>]*>Statistical Score/);
  assert.doesNotMatch(html, /Comparable-event evidence is unavailable/);
});

test('prediction shows only supplied threshold and frozen held-out metrics, preserving zeros and nulls', () => {
  const html = renderToStaticMarkup(<PredictionEvidence data={{ ...DEV_MOCK_PREDICTION,
    outperformance_probability: 0, classification_threshold: .5, metrics: {
      roc_auc: null, brier_score: 0, precision: 0, recall: null, f1: 0,
      sample_count: 20, positive_class_prevalence: .25, split_start: '2026-01-01', split_end: '2026-06-30',
    },
  }} />);
  assert.match(html, /Classification threshold: 50.00%/);
  for (const text of ['Brier Score', 'Precision', 'F1 Score', 'Sample Count', '20', '25.00%', '2026-01-01', '2026-06-30']) assert.ok(html.includes(text), text);
  assert.doesNotMatch(html, /Held-Out ROC-AUC|Recall|Unavailable/);
  const unavailable = renderToStaticMarkup(<PredictionEvidence data={DEV_MOCK_PREDICTION} />);
  assert.doesNotMatch(unavailable, /Held-Out ROC-AUC|Held-out metrics unavailable|Classification threshold/);
  assert.match(unavailable, /Outperformance Probability/);
});

test('existing unscored event is distinct from absent research events', () => {
  const unscored = renderToStaticMarkup(<CompanyScore data={{ ...DEV_MOCK_COMPANY, latest_signal: null }} />);
  assert.match(unscored, /Not scored/);
  assert.match(unscored, /A research event is available for 2026-10-08/);
  assert.doesNotMatch(unscored, /No research events|No recent insider events/);
  const absent = renderToStaticMarkup(<CompanyScore data={{ ...DEV_MOCK_COMPANY, latest_signal: null, latest_public_event_day: null }} />);
  assert.match(absent, /No research events/);
  assert.doesNotMatch(absent, /A research event is available/);
  const scored = renderToStaticMarkup(<CompanyScore data={DEV_MOCK_COMPANY} />);
  assert.match(scored, /Research Priority/);
  assert.match(scored, /85/);
});
