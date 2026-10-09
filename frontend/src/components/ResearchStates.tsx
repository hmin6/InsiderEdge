import type { RadarItem } from '../types/api';
import type { StatisticsResponse, PredictionResponse } from '../types/research';
import { Panel, StateMessage } from './ui';
export function rankRadar(items: RadarItem[]) {
  return [...items].sort((a, b) => {
    if (a.insider_edge_score === null) return b.insider_edge_score === null ? 0 : 1;
    if (b.insider_edge_score === null) return -1;
    return b.insider_edge_score - a.insider_edge_score;
  });
}
export function numeric(value: number | null | undefined, percent = false) {
  return value == null || !Number.isFinite(value) ? 'Unavailable' : percent ? `${(value * 100).toFixed(2)}%` : String(value);
}
export function StatisticsEvidence({ data }: { data: StatisticsResponse }) {
  const v = data.statistical_validation;
  return <div className="ie-stack">
    <Panel title="Anomaly & Activity Evidence">
      <p>Anomaly: {numeric(data.anomaly.score)} · Activity: {numeric(data.activity.score)}</p>
      {data.anomaly.score === null && <StateMessage title="Insufficient anomaly history">Anomaly evidence is unavailable; it is not a zero score.</StateMessage>}
    </Panel>
    <Panel title="Event Study & Statistical Evidence">
      <dl className="ie-metric-grid">{(['car5', 'car30', 'car90'] as const).map(key => <div key={key}><dt>{key.toUpperCase()}</dt><dd>{numeric(data.event_study[key], true)}</dd></div>)}</dl>
      {(data.event_study.car30 === null || data.event_study.car90 === null) && <p className="ie-muted">Unavailable horizons may need more completed trading sessions or estimation history. Future CAR is not yet known.</p>}
      {data.event_study.status !== 'complete' && <p className="ie-muted">Event-study evidence is incomplete or has insufficient estimation history.</p>}
      <p>Comparable events: {numeric(v.comparable_event_count)} · Mean CAR30: {numeric(v.mean_car30, true)}</p>
      <p>95% bootstrap interval: {v.bootstrap_ci_95 ? `${numeric(v.bootstrap_ci_95.lower, true)} to ${numeric(v.bootstrap_ci_95.upper, true)}` : 'Unavailable'}</p>
      <p>Randomization p-value: {numeric(v.randomization_p_value)}</p>
      <p className="ie-muted">{v.cohort_definition || 'Comparable-event cohort unavailable.'}</p>
      {v.statistical_score === null && <StateMessage title="Insufficient statistical history">Comparable-event evidence is unavailable. Other research results remain usable.</StateMessage>}
    </Panel>
  </div>;
}
export function PredictionEvidence({ data }: { data: PredictionResponse }) {
  return <Panel title="ML Prediction">
    {data.outperformance_probability === null ? <StateMessage title="Model prediction unavailable">No model probability is available for this event.</StateMessage> : <p className="ie-model-probability">Benchmark-outperformance probability: <strong>{numeric(data.outperformance_probability, true)}</strong></p>}
    <p className="ie-muted">{data.model_name || 'Model unavailable'}</p>
  </Panel>;
}
