import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { StatisticsEvidence, EventStudyEvidence, PredictionEvidence } from './ResearchStates';
import { DEV_MOCK_STATISTICS, DEV_MOCK_PREDICTION } from '../api/mocks';
import { statisticsVisibility, predictionVisibility } from './metricVisibility';
import type { StatisticsResponse } from '../types/research';

const empty: StatisticsResponse = {
  ...DEV_MOCK_STATISTICS,
  anomaly: { score: null, mahalanobis_distance: null, reference_count: null, reference_population: null, status: 'unavailable_not_persisted' },
  activity: { score: null, recent_purchase_rate: null, historical_purchase_rate: null, rate_ratio: null, buyers_30d: null, reference_population: null, status: 'unavailable_not_persisted' },
  market: { stock_return_90d: null, sector_return_90d: null, drawdown: null, dislocation_score: null, status: 'unavailable_not_persisted' },
  event_study: { car5: null, car30: null, car90: null, status: 'unavailable' },
  statistical_validation: { comparable_event_count: null, cohort_definition: null, mean_car30: null, bootstrap_ci_95: null, randomization_p_value: null, statistical_score: null, status: 'insufficient_data' },
};
test('unscored company has no empty quantitative panels or headings', () => {
  assert.equal(renderToStaticMarkup(<StatisticsEvidence data={empty} />), '');
  assert.equal(renderToStaticMarkup(<EventStudyEvidence data={empty} />), '');
  assert.equal(renderToStaticMarkup(<PredictionEvidence data={{...DEV_MOCK_PREDICTION, outperformance_probability: null, status: 'unavailable'}} />), '');
});
for (const value of [null, undefined, NaN, Infinity, -Infinity]) test(`invalid metric ${value} does not render a card`, () => {
  const data = {...empty, anomaly: {...empty.anomaly, score: value as number, status: 'partial'}, activity: {...empty.activity, score: 0, status: 'insufficient_data'}};
  const html = renderToStaticMarkup(<StatisticsEvidence data={data} />);
  assert.match(html, /Activity Score/);
  assert.match(html, />0.00</);
  assert.doesNotMatch(html, /Anomaly Score|Market Dislocation Evidence|Unavailable|NaN|Infinity/);
});
test('explicit unavailability suppresses contradictory numbers but partial diagnostics remain', () => {
  const data = {...empty, anomaly: {...empty.anomaly, score: 90, status: 'unavailable_not_persisted'}, market: {...empty.market, dislocation_score: 0, status: 'partial_diagnostics_unavailable'}};
  const html = renderToStaticMarkup(<StatisticsEvidence data={data} />);
  assert.doesNotMatch(html, /Anomaly &amp; Activity|Anomaly Score/);
  assert.match(html, /Dislocation Score/);
  assert.match(html, />0.00</);
  assert.deepEqual(statisticsVisibility(data), {activity:false, market:true, car:false, validation:false, interval:false, eventStudy:false});
});
test('realized CAR and partial bootstrap evidence survive missing horizons and p-value', () => {
  const data = {...empty, event_study: {...empty.event_study, car5: 0, status:'partial'}, statistical_validation: {...empty.statistical_validation, bootstrap_ci_95: {lower: -.02, upper: .03}, status:'partial'}};
  const html = renderToStaticMarkup(<EventStudyEvidence data={data} />);
  assert.match(html, /CAR5/);
  assert.match(html, /0.00%/);
  assert.match(html, /-2.00% to 3.00%/);
  assert.doesNotMatch(html, /ie-metric-label[^>]*>CAR30|P-Value|Comparable Events/);
  assert.equal(statisticsVisibility({...data, statistical_validation:{...data.statistical_validation, bootstrap_ci_95:{lower:NaN, upper:0}}}).interval, false);
});
test('held-out metrics survive a missing probability and preserve zero and split dates', () => {
  const data = {...DEV_MOCK_PREDICTION, outperformance_probability:null, metrics:{roc_auc:null, brier_score:0, precision:0, recall:null, f1:0, sample_count:20, positive_class_prevalence:.25, split_start:'2026-01-01', split_end:'2026-06-30'}};
  const html = renderToStaticMarkup(<PredictionEvidence data={data} />);
  for (const text of ['Brier Score', 'F1 Score', 'Precision', '20', '25.00%', '2026-01-01', '2026-06-30']) assert.ok(html.includes(text), text);
  assert.doesNotMatch(html, /Outperformance Probability|Held-Out ROC-AUC|Recall|Unavailable/);
  assert.equal(predictionVisibility(data).panel, true);
});
test('zero probability and zero threshold stay visible with model explanation button', () => {
  const html = renderToStaticMarkup(<PredictionEvidence data={{...DEV_MOCK_PREDICTION, outperformance_probability:0, classification_threshold:0}} />);
  assert.match(html, /Outperformance Probability/);
  assert.match(html, /Classification threshold: 0.00%/);
  assert.match(html, /aria-expanded="false"/);
});

test('onboarding omits missing targets and preserves complete and partial targets', async () => {
  const { companyTourSteps } = await import('./metricVisibility');
  const steps = ['body', '.tour-score-panel', '.tour-activity-panel', '.tour-dislocation-panel', '.tour-prediction-panel', '.tour-event-study-panel', '.ie-chart-region', '.tour-ai-panel'].map(target => ({target}));
  assert.deepEqual(companyTourSteps(steps, empty, {...DEV_MOCK_PREDICTION, outperformance_probability:null}).map(step => step.target), ['body', '.tour-score-panel', '.ie-chart-region', '.tour-ai-panel']);
  assert.deepEqual(companyTourSteps(steps, DEV_MOCK_STATISTICS, DEV_MOCK_PREDICTION), steps);
  const partial = {...empty, market:{...empty.market, drawdown:0, status:'partial'}};
  assert.deepEqual(companyTourSteps(steps, partial).map(step => step.target), ['body', '.tour-score-panel', '.tour-dislocation-panel', '.ie-chart-region', '.tour-ai-panel']);
});

test('bootstrap-only evidence has no empty metric grids', () => {
  const data = {...empty, statistical_validation:{...empty.statistical_validation, bootstrap_ci_95:{lower:0, upper:.03}, status:'partial'}};
  const html = renderToStaticMarkup(<EventStudyEvidence data={data} />);
  assert.match(html, /0.00% to 3.00%/);
  assert.doesNotMatch(html, /ie-metric-grid/);
});
