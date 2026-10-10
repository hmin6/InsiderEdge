import { formatCount, formatPValue } from "../utils/format";
import type { CompanyResponse, RadarItem } from "../types/api";
import type { StatisticsResponse, PredictionResponse } from "../types/research";
import { Panel, StateMessage } from "./ui";
import { InsiderEdgeScore } from "./InsiderEdgeScore";

export type RadarSortKey =
  | "default"
  | "company"
  | "status"
  | "anomaly"
  | "activity"
  | "dislocation"
  | "model_prob"
  | "priority";

/** Filter and order raw API values. Missing scores stay last in either direction. */
export function rankRadar(
  items: RadarItem[],
  options: {
    query?: string;
    sortKey?: RadarSortKey;
    direction?: "asc" | "desc";
  } = {},
) {
  const ranked = [...items].sort((a, b) => {
    if (a.insider_edge_score === null)
      return b.insider_edge_score === null ? 0 : 1;
    if (b.insider_edge_score === null) return -1;
    return b.insider_edge_score - a.insider_edge_score;
  });
  const query = (options.query ?? "").trim().toLowerCase();
  const key = options.sortKey ?? "default";
  const direction = options.direction ?? (key === "company" ? "asc" : "desc");
  const fields = {
    anomaly: "anomaly_score",
    activity: "activity_score",
    dislocation: "dislocation_score",
    model_prob: "ml_outperformance_probability",
    priority: "insider_edge_score",
  } as const;

  return ranked
    .filter(
      (item) =>
        item.ticker.toLowerCase().includes(query) ||
        item.company_name.toLowerCase().includes(query),
    )
    .sort((a, b) => {
      if (key === "default") return 0;
      const sign = direction === "asc" ? 1 : -1;
      if (key === "company")
        return (
          sign * a.ticker.localeCompare(b.ticker, "en", { sensitivity: "base" })
        );
      if (key === "status") {
        const completeness = (status: string) =>
          status === "complete" ? 2 : status === "partial" ? 1 : 0;
        return (
          sign * (completeness(a.score_status) - completeness(b.score_status))
        );
      }
      const left = a[fields[key]],
        right = b[fields[key]];
      const leftValid = typeof left === "number" && Number.isFinite(left);
      const rightValid = typeof right === "number" && Number.isFinite(right);
      if (!leftValid) return rightValid ? 1 : 0;
      if (!rightValid) return -1;
      return sign * (left - right);
    });
}

// Enforces 2 decimal places globally for all UI cards
export function numeric(value: number | null | undefined, percent = false) {
  if (value == null || !Number.isFinite(value)) return "Unavailable";
  return percent ? `${(value * 100).toFixed(2)}%` : value.toFixed(2);
}

export function CompanyScore({ data }: { data: CompanyResponse }) {
  if (data.latest_signal)
    return <InsiderEdgeScore evidence={data.latest_signal} />;
  return (
    <Panel title="InsiderEdge Score">
      {data.latest_public_event_day !== null ? (
        <StateMessage title="Not scored">
          No score has been generated for this research event. A research event
          is available for {data.latest_public_event_day}, but no matching
          research-priority signal is available. Missing evidence is not a zero
          score.
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
          <div
            className="ie-metric-card"
            title={`Raw value: ${data.anomaly.score}`}
          >
            <div className="ie-metric-label">Anomaly Score</div>
            <div className="ie-metric-value">{numeric(data.anomaly.score)}</div>
          </div>
          <div
            className="ie-metric-card"
            title={`Raw value: ${data.activity.score}`}
          >
            <div className="ie-metric-label">Activity Score</div>
            <div className="ie-metric-value">
              {numeric(data.activity.score)}
            </div>
          </div>
          <div
            className="ie-metric-card"
            title={`Raw value: ${data.anomaly.mahalanobis_distance}`}
          >
            <div className="ie-metric-label">Mahalanobis Distance</div>
            <div className="ie-metric-value">
              {numeric(data.anomaly.mahalanobis_distance)}
            </div>
          </div>
          <div
            className="ie-metric-card"
            title={`Raw value: ${data.activity.rate_ratio}`}
          >
            <div className="ie-metric-label">Purchase Rate Ratio</div>
            <div className="ie-metric-value">
              {numeric(data.activity.rate_ratio)}
            </div>
          </div>
        </div>

        {data.anomaly.score === null && (
          <StateMessage title="Insufficient anomaly history">
            Anomaly evidence is unavailable; it is not a zero score.
          </StateMessage>
        )}
        <p className="ie-muted" style={{ marginTop: "16px" }}>
          Anomaly Cohort: {data.anomaly.reference_population ?? "Unavailable"} (
          {formatCount(data.anomaly.reference_count)} events) · Status:{" "}
          {data.anomaly.status}
        </p>
        <p className="ie-muted" style={{ marginTop: "4px" }}>
          Activity Cohort: {data.activity.reference_population ?? "Unavailable"}{" "}
          ({formatCount(data.activity.buyers_30d)} supported buyers) · Status:{" "}
          {data.activity.status}
        </p>
      </Panel>

      <Panel title="Market Dislocation Evidence">
        <div className="ie-metric-grid">
          <div
            className="ie-metric-card"
            title={`Raw value: ${data.market.stock_return_90d}`}
          >
            <div className="ie-metric-label">Stock Return (90d)</div>
            <div className="ie-metric-value">
              {numeric(data.market.stock_return_90d, true)}
            </div>
          </div>
          <div
            className="ie-metric-card"
            title={`Raw value: ${data.market.sector_return_90d}`}
          >
            <div className="ie-metric-label">Sector Return (90d)</div>
            <div className="ie-metric-value">
              {numeric(data.market.sector_return_90d, true)}
            </div>
          </div>
          <div
            className="ie-metric-card"
            title={`Raw value: ${data.market.drawdown}`}
          >
            <div className="ie-metric-label">Drawdown</div>
            <div className="ie-metric-value">
              {numeric(data.market.drawdown, true)}
            </div>
          </div>
          <div
            className="ie-metric-card"
            title={`Raw value: ${data.market.dislocation_score}`}
          >
            <div className="ie-metric-label">Dislocation Score</div>
            <div className="ie-metric-value">
              {numeric(data.market.dislocation_score)}
            </div>
          </div>
        </div>
        <p className="ie-muted" style={{ marginTop: "16px" }}>
          Pre-event market context; unavailable observations remain unknown.
          Status: {data.market.status}
        </p>
      </Panel>
    </div>
  );
}
export function EventStudyEvidence({ data }: { data: StatisticsResponse }) {
  const v = data.statistical_validation;
  return (
    <Panel title="Event Study & Statistical Evidence">
      <div className="ie-metric-grid">
        <div
          className="ie-metric-card"
          title={`Raw value: ${data.event_study.car5}`}
        >
          <div className="ie-metric-label">CAR5</div>
          <div className="ie-metric-value">
            {numeric(data.event_study.car5, true)}
          </div>
        </div>
        <div
          className="ie-metric-card"
          title={`Raw value: ${data.event_study.car30}`}
        >
          <div className="ie-metric-label">CAR30</div>
          <div className="ie-metric-value">
            {numeric(data.event_study.car30, true)}
          </div>
        </div>
        <div
          className="ie-metric-card"
          title={`Raw value: ${data.event_study.car90}`}
        >
          <div className="ie-metric-label">CAR90</div>
          <div className="ie-metric-value">
            {numeric(data.event_study.car90, true)}
          </div>
        </div>
      </div>
      <div className="ie-metric-grid">
        <div
          className="ie-metric-card"
          title={`Raw value: ${v.comparable_event_count}`}
        >
          <div className="ie-metric-label">Comparable Events</div>
          <div className="ie-metric-value">
            {formatCount(v.comparable_event_count)}
          </div>
        </div>
        <div className="ie-metric-card" title={`Raw value: ${v.mean_car30}`}>
          <div className="ie-metric-label">Mean CAR30</div>
          <div className="ie-metric-value">{numeric(v.mean_car30, true)}</div>
        </div>
        <div
          className="ie-metric-card"
          title={`Raw value: ${v.randomization_p_value}`}
        >
          <div className="ie-metric-label">P-Value</div>
          <div className="ie-metric-value">
            {formatPValue(v.randomization_p_value)}
          </div>
        </div>
        <div
          className="ie-metric-card"
          title={`Raw value: ${v.statistical_score}`}
        >
          <div className="ie-metric-label">Statistical Score</div>
          <div className="ie-metric-value">{numeric(v.statistical_score)}</div>
        </div>
      </div>

      {(data.event_study.car30 === null || data.event_study.car90 === null) && (
        <p className="ie-muted" style={{ marginTop: "16px" }}>
          Unavailable horizons may need more completed trading sessions or
          estimation history. Future CAR is not yet known.
        </p>
      )}
      {v.statistical_score === null && (
        <StateMessage title="Combined statistical score unavailable">
          Bootstrap and randomization evidence have separate availability. Any
          available comparable-event results remain visible above.
        </StateMessage>
      )}
      <p className="ie-muted" style={{ marginTop: "16px" }}>
        95% bootstrap interval:{" "}
        {v.bootstrap_ci_95
          ? `${numeric(v.bootstrap_ci_95.lower, true)} to ${numeric(v.bootstrap_ci_95.upper, true)}`
          : "Unavailable"}
      </p>
      <p className="ie-muted" style={{ marginTop: "4px" }}>
        Cohort: {v.cohort_definition || "Unavailable"} · Study Status:{" "}
        {data.event_study.status} · Validation Status: {v.status}
      </p>
    </Panel>
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
          <div
            className="ie-metric-card"
            title={`Raw probability: ${data.outperformance_probability}`}
          >
            <div className="ie-metric-label">Outperformance Probability</div>
            <div className="ie-metric-value">
              {numeric(data.outperformance_probability, true)}
            </div>
          </div>
          <div className="ie-metric-card" title={`Engine: ${data.model_name}`}>
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

      <p className="ie-muted" style={{ marginTop: "16px" }}>
        Classification threshold: {numeric(data.classification_threshold, true)}{" "}
        · Status: {data.status}
      </p>

      {data.metrics === null ? (
        <StateMessage title="Held-out metrics unavailable">
          No durable frozen held-out evaluation is available. Validation metrics
          are not substituted.
        </StateMessage>
      ) : (
        <div
          className="ie-metric-grid"
          style={{
            marginTop: "24px",
            paddingTop: "24px",
            borderTop: "1px solid var(--ie-border)",
          }}
        >
          <div
            className="ie-metric-card"
            title={`Raw value: ${data.metrics.roc_auc}`}
          >
            <div className="ie-metric-label">Held-Out ROC-AUC</div>
            <div className="ie-metric-value">
              {numeric(data.metrics.roc_auc)}
            </div>
          </div>
          <div
            className="ie-metric-card"
            title={`Raw value: ${data.metrics.brier_score}`}
          >
            <div className="ie-metric-label">Brier Score</div>
            <div className="ie-metric-value">
              {numeric(data.metrics.brier_score)}
            </div>
          </div>
          <div
            className="ie-metric-card"
            title={`Raw value: ${data.metrics.f1}`}
          >
            <div className="ie-metric-label">F1 Score</div>
            <div className="ie-metric-value">{numeric(data.metrics.f1)}</div>
          </div>
          <div
            className="ie-metric-card"
            title={`Raw value: ${data.metrics.precision}`}
          >
            <div className="ie-metric-label">Precision</div>
            <div className="ie-metric-value">
              {numeric(data.metrics.precision, true)}
            </div>
          </div>
          <div
            className="ie-metric-card"
            title={`Raw value: ${data.metrics.recall}`}
          >
            <div className="ie-metric-label">Recall</div>
            <div className="ie-metric-value">
              {numeric(data.metrics.recall, true)}
            </div>
          </div>
          <div
            className="ie-metric-card"
            title={`Raw value: ${data.metrics.sample_count}`}
          >
            <div className="ie-metric-label">Sample Count</div>
            <div className="ie-metric-value">
              {formatCount(data.metrics.sample_count)}
            </div>
          </div>
        </div>
      )}
    </Panel>
  );
}
