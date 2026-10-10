import {
  formatNumber,
  formatFractionPercent,
  formatCount,
  formatPValue,
} from "../utils/format";
import type { CompanyResponse, RadarItem } from "../types/api";
import type { StatisticsResponse, PredictionResponse } from "../types/research";
import { Panel, StateMessage } from "./ui";
import { InsiderEdgeScore } from "./InsiderEdgeScore";
export function rankRadar(items: RadarItem[]) {
  return [...items].sort((a, b) => {
    if (a.insider_edge_score === null)
      return b.insider_edge_score === null ? 0 : 1;
    if (b.insider_edge_score === null) return -1;
    return b.insider_edge_score - a.insider_edge_score;
  });
}
export function numeric(value: number | null | undefined, percent = false) {
  return value == null || !Number.isFinite(value)
    ? "Unavailable"
    : percent
      ? `${(value * 100).toFixed(2)}%`
      : value.toFixed(1);
}
function Metrics({ values }: { values: [string, string][] }) {
  return (
    <dl className="ie-metric-grid">
      {values.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
export function CompanyScore({ data }: { data: CompanyResponse }) {
  if (data.latest_signal)
    return <InsiderEdgeScore evidence={data.latest_signal} />;
  return (
    <Panel title="InsiderEdge Score">
      {data.latest_public_event_day !== null ? (
        <StateMessage title="Research-priority score unavailable">
          A research event is available for {data.latest_public_event_day}, but
          no matching research-priority signal is available. Missing evidence is
          not a zero score.
        </StateMessage>
      ) : (
        <StateMessage title="No research events">
          No qualifying research event is available. No score has been invented.
        </StateMessage>
      )}
    </Panel>
  );
}
export function StatisticsEvidence({ data }: { data: StatisticsResponse }) {
  const v = data.statistical_validation;
  return (
    <div className="ie-stack">
      <Panel title="Anomaly & Activity Evidence">
        <div className="ie-metric-grid">
          <div className="ie-metric-card">
            <div className="ie-metric-label">Anomaly Score</div>
            <div className="ie-metric-value">{numeric(data.anomaly.score)}</div>
          </div>
          <div className="ie-metric-card">
            <div className="ie-metric-label">Activity Score</div>
            <div className="ie-metric-value">
              {numeric(data.activity.score)}
            </div>
          </div>
        </div>
        {data.anomaly.score === null && (
          <StateMessage title="Insufficient anomaly history">
            Anomaly evidence is unavailable; it is not a zero score.
          </StateMessage>
        )}
      </Panel>

      <Panel title="Event Study & Statistical Evidence">
        <div className="ie-metric-grid">
          <div className="ie-metric-card">
            <div className="ie-metric-label">CAR5</div>
            <div className="ie-metric-value">
              {numeric(data.event_study.car5, true)}
            </div>
          </div>
          <div className="ie-metric-card">
            <div className="ie-metric-label">CAR30</div>
            <div className="ie-metric-value">
              {numeric(data.event_study.car30, true)}
            </div>
          </div>
          <div className="ie-metric-card">
            <div className="ie-metric-label">CAR90</div>
            <div className="ie-metric-value">
              {numeric(data.event_study.car90, true)}
            </div>
          </div>
        </div>
        <div className="ie-metric-grid">
          <div className="ie-metric-card">
            <div className="ie-metric-label">Comparable Events</div>
            <div className="ie-metric-value">
              {numeric(v.comparable_event_count)}
            </div>
          </div>
          <div className="ie-metric-card">
            <div className="ie-metric-label">Mean CAR30</div>
            <div className="ie-metric-value">{numeric(v.mean_car30, true)}</div>
          </div>
          <div className="ie-metric-card">
            <div className="ie-metric-label">P-Value</div>
            <div className="ie-metric-value">
              {numeric(v.randomization_p_value)}
            </div>
          </div>
        </div>
        <p className="ie-muted" style={{ marginTop: "16px" }}>
          Cohort: {v.cohort_definition || "Unavailable"}
        </p>
      </Panel>
    </div>
  );
}

export function PredictionEvidence({ data }: { data: PredictionResponse }) {
  return (
    <Panel title="ML Prediction">
      {data.outperformance_probability === null ? (
        <StateMessage title="Model prediction unavailable">
          No model probability is available for this event.
        </StateMessage>
      ) : (
        <div className="ie-metric-grid">
          <div className="ie-metric-card">
            <div className="ie-metric-label">Outperformance Probability</div>
            <div className="ie-metric-value">
              {numeric(data.outperformance_probability, true)}
            </div>
          </div>
          <div className="ie-metric-card">
            <div className="ie-metric-label">Model Engine</div>
            <div
              className="ie-metric-value"
              style={{ fontSize: "14px", marginTop: "6px" }}
            >
              {data.model_name || "Unavailable"}
            </div>
          </div>
        </div>
      )}
    </Panel>
  );
}
