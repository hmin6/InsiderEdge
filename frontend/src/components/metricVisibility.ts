import type { StatisticsResponse, PredictionResponse } from '../types/research';
export function finiteMetric(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}
// Partial/insufficient sections can still contain real diagnostics.
export function sectionAvailable(status?: string) {
  return !status || !/^(unavailable(?:_|$)|not_scored$|error$)/i.test(status);
}
function hasMetrics(section: { status: string }, values: unknown[]) {
  return sectionAvailable(section.status) && values.some(finiteMetric);
}
export function statisticsVisibility(data?: StatisticsResponse | null) {
  if (!data) return { activity: false, market: false, car: false, validation: false, interval: false, eventStudy: false };
  const a = data.anomaly, c = data.activity, m = data.market, e = data.event_study, v = data.statistical_validation;
  const activity = hasMetrics(a, [a.score, a.mahalanobis_distance]) || hasMetrics(c, [c.score, c.recent_purchase_rate, c.historical_purchase_rate, c.rate_ratio, c.buyers_30d]);
  const market = hasMetrics(m, [m.stock_return_90d, m.sector_return_90d, m.drawdown, m.dislocation_score]);
  const car = hasMetrics(e, [e.car5, e.car30, e.car90]);
  const interval = sectionAvailable(v.status) && finiteMetric(v.bootstrap_ci_95?.lower) && finiteMetric(v.bootstrap_ci_95?.upper);
  const validation = hasMetrics(v, [v.comparable_event_count, v.mean_car30, v.randomization_p_value, v.statistical_score]);
  return { activity, market, car, validation, interval, eventStudy: car || validation || interval };
}
export function predictionVisibility(data?: PredictionResponse | null) {
  const probability = !!data && sectionAvailable(data.status) && finiteMetric(data.outperformance_probability);
  const metrics = !!data?.metrics && sectionAvailable(data.status) && Object.entries(data.metrics).some(([key, value]) => !key.startsWith('split_') && finiteMetric(value));
  const panel = !!data && sectionAvailable(data.status) && (probability || metrics || finiteMetric(data.classification_threshold));
  return { probability, metrics, panel };
}

/** Keep onboarding focused on panels that actually contain evidence. */
export function companyTourSteps<T extends { target: string }>(steps: T[], statistics?: StatisticsResponse | null, prediction?: PredictionResponse | null) {
  const visible = statisticsVisibility(statistics);
  const targets = new Set(["body", ".tour-score-panel", ".ie-chart-region", ".tour-ai-panel",
    ...(visible.activity ? [".tour-activity-panel"] : []),
    ...(visible.market ? [".tour-dislocation-panel"] : []),
    ...(visible.eventStudy ? [".tour-event-study-panel"] : []),
    ...(predictionVisibility(prediction).panel ? [".tour-prediction-panel"] : []),
  ]);
  return steps.filter(step => targets.has(step.target));
}
