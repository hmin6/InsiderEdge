import type { CompanyResponse, RadarItem } from '../types/api';
import type { StatisticsResponse, PredictionResponse } from '../types/research';
import { Panel, StateMessage } from './ui';
import { InsiderEdgeScore } from './InsiderEdgeScore';
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
function Metrics({ values }: { values: [string, string][] }) {
  return <dl className="ie-metric-grid">{values.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}
export function CompanyScore({ data }: { data: CompanyResponse }) {
  if (data.latest_signal) return <InsiderEdgeScore evidence={data.latest_signal} />;
  return <Panel title="InsiderEdge Score">
    {data.latest_public_event_day !== null ?
      <StateMessage title="Research-priority score unavailable">A research event is available for {data.latest_public_event_day}, but no matching research-priority signal is available. Missing evidence is not a zero score.</StateMessage> :
      <StateMessage title="No research events">No qualifying research event is available. No score has been invented.</StateMessage>}
  </Panel>;
}
export function StatisticsEvidence({ data }: { data: StatisticsResponse }) {
  const v = data.statistical_validation;
  return <div className="ie-stack">
    <Panel title="Anomaly & Activity Evidence">
      <p>Anomaly: {numeric(data.anomaly.score)} · Activity: {numeric(data.activity.score)}</p>
      {data.anomaly.score === null && <StateMessage title="Insufficient anomaly history">Anomaly evidence is unavailable; it is not a zero score.</StateMessage>}
      <Metrics values={[
        ['Mahalanobis distance', numeric(data.anomaly.mahalanobis_distance)],
        ['Anomaly reference population', data.anomaly.reference_population ?? 'Unavailable'],
        ['Anomaly reference count', numeric(data.anomaly.reference_count)],
        ['Anomaly status', data.anomaly.status],
        ['Recent purchase rate (events/day)', numeric(data.activity.recent_purchase_rate)],
        ['Historical purchase rate (events/day)', numeric(data.activity.historical_purchase_rate)],
        ['Purchase rate ratio', numeric(data.activity.rate_ratio)],
        ['Supported buyers (30 days)', numeric(data.activity.buyers_30d)],
        ['Activity reference population', data.activity.reference_population ?? 'Unavailable'],
        ['Activity status', data.activity.status],
      ]} />
    </Panel>
    <Panel title="Market Dislocation Evidence">
      <Metrics values={[
        ['Stock return (90 sessions)', numeric(data.market.stock_return_90d, true)],
        ['Sector return (90 sessions)', numeric(data.market.sector_return_90d, true)],
        ['Drawdown', numeric(data.market.drawdown, true)],
        ['Dislocation score', numeric(data.market.dislocation_score)],
        ['Market status', data.market.status],
      ]} />
      <p className="ie-muted">Pre-event market context; unavailable observations remain unknown.</p>
    </Panel>
    <Panel title="Event Study & Statistical Evidence">
      <dl className="ie-metric-grid">{(['car5', 'car30', 'car90'] as const).map(key => <div key={key}><dt>{key.toUpperCase()}</dt><dd>{numeric(data.event_study[key], true)}</dd></div>)}</dl>
      <p className="ie-muted">Event-study status: {data.event_study.status}</p>
      {(data.event_study.car30 === null || data.event_study.car90 === null) && <p className="ie-muted">Unavailable horizons may need more completed trading sessions or estimation history. Future CAR is not yet known.</p>}
      {data.event_study.status !== 'complete' && <p className="ie-muted">Event-study evidence is incomplete or has insufficient estimation history.</p>}
      <p>Comparable events: {numeric(v.comparable_event_count)} · Mean CAR30: {numeric(v.mean_car30, true)}</p>
      <p>95% bootstrap interval: {v.bootstrap_ci_95 ? `${numeric(v.bootstrap_ci_95.lower, true)} to ${numeric(v.bootstrap_ci_95.upper, true)}` : 'Unavailable'}</p>
      <p>Randomization p-value: {numeric(v.randomization_p_value)}</p>
      <p>Statistical score: {numeric(v.statistical_score)} · Status: {v.status}</p>
      <p className="ie-muted">{v.cohort_definition || 'Comparable-event cohort unavailable.'}</p>
      {v.statistical_score === null && <StateMessage title="Combined statistical score unavailable">Bootstrap and randomization evidence have separate availability. Any available comparable-event results remain visible above.</StateMessage>}
    </Panel>
  </div>;
}
export function PredictionEvidence({ data }: { data: PredictionResponse }) {
  return <Panel title="ML Prediction">
    {data.outperformance_probability === null ? <StateMessage title="Model prediction unavailable">No model probability is available for this event.</StateMessage> : <p className="ie-model-probability">Benchmark-outperformance probability: <strong>{numeric(data.outperformance_probability, true)}</strong></p>}
    <p className="ie-muted">{data.model_name || 'Model unavailable'}</p>
    <p>Classification threshold: {numeric(data.classification_threshold, true)} · Status: {data.status}</p>
    {data.metrics === null ? <StateMessage title="Held-out metrics unavailable">No durable frozen held-out evaluation is available. Validation metrics are not substituted.</StateMessage> :
      <Metrics values={[
        ['Held-out ROC-AUC', numeric(data.metrics.roc_auc)],
        ['Held-out Brier score', numeric(data.metrics.brier_score)],
        ['Held-out precision', numeric(data.metrics.precision, true)],
        ['Held-out recall', numeric(data.metrics.recall, true)],
        ['Held-out F1', numeric(data.metrics.f1)],
        ['Held-out sample count', numeric(data.metrics.sample_count)],
        ['Held-out positive-class prevalence', numeric(data.metrics.positive_class_prevalence, true)],
        ['Held-out split start', data.metrics.split_start ?? 'Unavailable'],
        ['Held-out split end', data.metrics.split_end ?? 'Unavailable'],
      ]} />}
  </Panel>;
}
