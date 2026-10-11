import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { formatCount, formatPValue } from "../utils/format";
import type { CompanyResponse, RadarItem } from "../types/api";
import type { StatisticsResponse, PredictionResponse } from "../types/research";
import { Panel, StateMessage } from "./ui";
import { InsiderEdgeScore } from "./InsiderEdgeScore";
import { NOT_SCORED_EXPLANATION } from "./SignalAvailability";

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

function MetricCard({
  label,
  value,
  raw,
  explanation,
  context,
}: {
  label: string;
  value: React.ReactNode;
  raw: any;
  explanation: string;
  context: string;
}) {
  const [isOpen, setIsOpen] = useState(false);

  // Lock scrolling on the main page when the modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  // Close the modal if the user presses the Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    if (isOpen) window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  return (
    <>
      <button
        type="button"
        className="ie-metric-card"
        onClick={() => setIsOpen(true)}
        style={{
          textAlign: "left",
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          borderColor: isOpen ? "var(--ie-primary)" : "var(--ie-border)",
          boxShadow: isOpen ? "0 0 0 1px var(--ie-primary)" : undefined,
        }}
        aria-expanded={isOpen}
      >
        <div
          className="ie-metric-label"
          style={{
            display: "flex",
            justifyContent: "space-between",
            width: "100%",
          }}
        >
          {label}
          <span
            style={{ opacity: 0.5, fontSize: "12px", pointerEvents: "none" }}
          >
            ⓘ
          </span>
        </div>
        <div className="ie-metric-value">{value}</div>
      </button>

      {/* Full-Screen Centered Modal Overlay using Portal */}
      {isOpen &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            className="ie-reveal"
            style={{
              position: "fixed",
              inset: 0,
              zIndex: 9999,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              backgroundColor: "rgba(0, 0, 0, 0.65)",
              backdropFilter: "blur(6px)",
              padding: "20px",
            }}
            onClick={() => setIsOpen(false)}
          >
            <div
              style={{
                position: "relative",
                width: "100%",
                maxWidth: "400px",
                background: "var(--ie-nav)",
                border: "1px solid var(--ie-border)",
                borderRadius: "12px",
                padding: "24px",
                boxShadow: "0 20px 40px rgba(0, 0, 0, 0.6)",
                color: "var(--ie-text)",
                textAlign: "left",
                cursor: "default",
              }}
              onClick={(e) => e.stopPropagation()}
              role="dialog"
              aria-modal="true"
            >
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                style={{
                  position: "absolute",
                  top: "14px",
                  right: "14px",
                  background: "rgba(255, 255, 255, 0.05)",
                  border: "1px solid rgba(255, 255, 255, 0.1)",
                  borderRadius: "50%",
                  color: "var(--ie-muted)",
                  cursor: "pointer",
                  fontSize: "14px",
                  width: "30px",
                  height: "30px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  transition: "background 0.2s, color 0.2s",
                }}
                aria-label="Close explanation"
                onMouseEnter={(e) => {
                  e.currentTarget.style.background =
                    "rgba(255, 255, 255, 0.15)";
                  e.currentTarget.style.color = "#fff";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background =
                    "rgba(255, 255, 255, 0.05)";
                  e.currentTarget.style.color = "var(--ie-muted)";
                }}
              >
                ✕
              </button>
              <div
                style={{
                  fontSize: "18px",
                  fontWeight: 650,
                  marginBottom: "16px",
                  color: "#fff",
                  paddingRight: "24px",
                }}
              >
                {label}
              </div>
              <div
                style={{
                  fontSize: "14.5px",
                  marginBottom: "12px",
                  lineHeight: 1.6,
                }}
              >
                <strong
                  style={{
                    color: "var(--ie-primary)",
                    display: "block",
                    marginBottom: "4px",
                  }}
                >
                  Meaning
                </strong>
                <span style={{ color: "#e2e8f0" }}>{explanation}</span>
              </div>
              <div
                style={{
                  fontSize: "14.5px",
                  marginBottom: "16px",
                  lineHeight: 1.6,
                }}
              >
                <strong
                  style={{
                    color: "var(--ie-primary)",
                    display: "block",
                    marginBottom: "4px",
                  }}
                >
                  Context
                </strong>
                <span style={{ color: "#e2e8f0" }}>{context}</span>
              </div>
              <div
                style={{
                  fontSize: "12px",
                  color: "var(--ie-muted)",
                  borderTop: "1px solid var(--ie-border)",
                  paddingTop: "12px",
                  margin: 0,
                }}
              >
                Raw metric value:{" "}
                <code
                  style={{
                    background: "rgba(255,255,255,0.05)",
                    padding: "2px 6px",
                    borderRadius: "4px",
                  }}
                >
                  {String(raw ?? "null")}
                </code>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

export function CompanyScore({ data }: { data: CompanyResponse }) {
  if (data.latest_signal)
    return <InsiderEdgeScore evidence={data.latest_signal} />;
  return (
    <Panel title="InsiderEdge Score">
      {data.latest_public_event_day !== null ? (
        <StateMessage title="Not scored">
          {NOT_SCORED_EXPLANATION} A research event is available for{" "}
          {data.latest_public_event_day}. Missing evidence is not a zero score.
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
  return (
    <div className="ie-stack" style={{ height: "100%" }}>
      <Panel title="Anomaly & Activity Evidence" style={{ flex: 1 }}>
        <div className="ie-metric-grid">
          <MetricCard
            label="Anomaly Score"
            value={numeric(data.anomaly.score)}
            raw={data.anomaly.score}
            explanation="Percentile ranking of how unusual the insider buying size and market conditions are relative to historical baselines."
            context=">80 is considered highly anomalous and statistically rare."
          />
          <MetricCard
            label="Activity Score"
            value={numeric(data.activity.score)}
            raw={data.activity.score}
            explanation="Percentile ranking of clustered buying intensity within a 30-day window."
            context="Higher scores indicate strong, coordinated insider conviction."
          />
          <MetricCard
            label="Mahalanobis Dist"
            value={numeric(data.anomaly.mahalanobis_distance)}
            raw={data.anomaly.mahalanobis_distance}
            explanation="A multi-dimensional measure of how far this event's features deviate from the norm."
            context=">2.5 typically flags a significant outlier."
          />
          <MetricCard
            label="Purchase Rate Ratio"
            value={numeric(data.activity.rate_ratio)}
            raw={data.activity.rate_ratio}
            explanation="Current 30-day buying rate divided by the historical baseline rate."
            context=">1.0 means insiders are buying faster than usual."
          />
          <MetricCard
            label="Recent Rate"
            value={numeric(data.activity.recent_purchase_rate)}
            raw={data.activity.recent_purchase_rate}
            explanation="Average number of insider purchase events per day over the last 30 days."
            context="Compared against historical rates to detect acceleration."
          />
          <MetricCard
            label="Historical Rate"
            value={numeric(data.activity.historical_purchase_rate)}
            raw={data.activity.historical_purchase_rate}
            explanation="Average number of insider purchase events per day over the last year."
            context="Establishes the company's normal baseline for insider buying."
          />
          <MetricCard
            label="Buyers (30d)"
            value={formatCount(data.activity.buyers_30d)}
            raw={data.activity.buyers_30d}
            explanation="Number of unique executives or directors buying in the last 30 days."
            context="Multiple buyers (clusters) provide much stronger signals than solo buyers."
          />
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

      <Panel title="Market Dislocation Evidence" style={{ flex: 1 }}>
        <div className="ie-metric-grid">
          <MetricCard
            label="Stock Return (90d)"
            value={numeric(data.market.stock_return_90d, true)}
            raw={data.market.stock_return_90d}
            explanation="Price performance over the prior 90 trading sessions."
            context="Used to identify if the stock is being bought into severe weakness."
          />
          <MetricCard
            label="Sector Return (90d)"
            value={numeric(data.market.sector_return_90d, true)}
            raw={data.market.sector_return_90d}
            explanation="Average performance of the company's sector over the last 90 sessions."
            context="Contextualizes whether a stock drop is idiosyncratic or sector-wide."
          />
          <MetricCard
            label="Drawdown"
            value={numeric(data.market.drawdown, true)}
            raw={data.market.drawdown}
            explanation="The percentage drop from the stock's highest price in the last 90 days."
            context="Closer to -20% or worse indicates significant market dislocation."
          />
          <MetricCard
            label="Dislocation Score"
            value={numeric(data.market.dislocation_score)}
            raw={data.market.dislocation_score}
            explanation="A 0-100 score blending the sector performance gap and recent drawdown."
            context="High scores mean the stock is beaten down relative to peers, a classic value setup."
          />
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
    <Panel title="Event Study & Statistical Evidence" style={{ flex: 1 }}>
      <div className="ie-metric-grid">
        <MetricCard
          label="CAR5"
          value={numeric(data.event_study.car5, true)}
          raw={data.event_study.car5}
          explanation="Cumulative Abnormal Return over 5 days. The stock's actual return minus the market benchmark's expected return."
          context="Positive numbers mean the stock outperformed the market post-event."
        />
        <MetricCard
          label="CAR30"
          value={numeric(data.event_study.car30, true)}
          raw={data.event_study.car30}
          explanation="Cumulative Abnormal Return over 30 days."
          context="Used as the primary target variable for the machine learning models."
        />
        <MetricCard
          label="CAR90"
          value={numeric(data.event_study.car90, true)}
          raw={data.event_study.car90}
          explanation="Cumulative Abnormal Return over 90 days."
          context="Measures the long-term sustained edge of the event."
        />
      </div>
      <div className="ie-metric-grid">
        <MetricCard
          label="Comparable Events"
          value={formatCount(v.comparable_event_count)}
          raw={v.comparable_event_count}
          explanation="Historical events with identical sector and role profiles used for backtesting."
          context="10+ is required for statistical validity."
        />
        <MetricCard
          label="Mean CAR30"
          value={numeric(v.mean_car30, true)}
          raw={v.mean_car30}
          explanation="The average 30-day abnormal return of the historical comparable cohort."
          context="Shows the historical track record of this specific setup."
        />
        <MetricCard
          label="P-Value"
          value={formatPValue(v.randomization_p_value)}
          raw={v.randomization_p_value}
          explanation="The probability that the Mean CAR30 was achieved purely by random chance."
          context="Below 0.05 is generally considered statistically significant."
        />
        <MetricCard
          label="Statistical Score"
          value={numeric(v.statistical_score)}
          raw={v.statistical_score}
          explanation="A 0-100 blend of bootstrap confidence intervals and p-value support."
          context="Higher scores indicate a highly repeatable, non-random historical edge."
        />
      </div>

      {(data.event_study.car30 === null || data.event_study.car90 === null) && (
        <p className="ie-muted" style={{ marginTop: "16px" }}>
          Unavailable horizons may need more completed trading sessions. Future
          CAR is not yet known.
        </p>
      )}
      <p className="ie-muted" style={{ marginTop: "16px" }}>
        95% bootstrap interval:{" "}
        {v.bootstrap_ci_95
          ? `${numeric(v.bootstrap_ci_95.lower, true)} to ${numeric(v.bootstrap_ci_95.upper, true)}`
          : "Unavailable"}
      </p>
      <p className="ie-muted" style={{ marginTop: "4px" }}>
        Cohort: {v.cohort_definition || "Unavailable"} · Validation Status:{" "}
        {v.status}
      </p>
    </Panel>
  );
}

export function PredictionEvidence({ data }: { data: PredictionResponse }) {
  return (
    <Panel title="ML Prediction" style={{ flex: 1 }}>
      {data.outperformance_probability === null ? (
        <StateMessage title="Model prediction unavailable">
          No model probability is available for this event.
        </StateMessage>
      ) : (
        <div className="ie-metric-grid">
          <MetricCard
            label="Outperformance Probability"
            value={numeric(data.outperformance_probability, true)}
            raw={data.outperformance_probability}
            explanation="The ML model's confidence that the stock will beat the benchmark over the next 30 days."
            context=">50% leans bullish; >65% is a strong conviction signal."
          />
          <MetricCard
            label="Model Engine"
            value={
              <div style={{ fontSize: "14px", marginTop: "6px" }}>
                {data.model_name || "Unavailable"}
              </div>
            }
            raw={data.model_name}
            explanation="The specific algorithmic architecture used for scoring."
            context="Logistic Regression or XGBoost, determined dynamically during backtesting."
          />
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
          <MetricCard
            label="Held-Out ROC-AUC"
            value={numeric(data.metrics.roc_auc)}
            raw={data.metrics.roc_auc}
            explanation="Area Under the Receiver Operating Characteristic Curve on unseen data."
            context="0.5 is random guessing. 0.6+ shows a genuine predictive edge in finance."
          />
          <MetricCard
            label="Brier Score"
            value={numeric(data.metrics.brier_score)}
            raw={data.metrics.brier_score}
            explanation="Measures the accuracy and calibration of probabilistic predictions."
            context="Lower is better. A score of 0.0 is perfect accuracy; 0.25 is random guessing."
          />
          <MetricCard
            label="F1 Score"
            value={numeric(data.metrics.f1)}
            raw={data.metrics.f1}
            explanation="The harmonic mean of Precision and Recall."
            context="Balances the trade-off between false positives (bad trades) and false negatives (missed trades)."
          />
          <MetricCard
            label="Precision"
            value={numeric(data.metrics.precision, true)}
            raw={data.metrics.precision}
            explanation="When the model flags an event as outperforming, how often is it actually right?"
            context="A crucial metric for capital preservation to minimize false signals."
          />
          <MetricCard
            label="Recall"
            value={numeric(data.metrics.recall, true)}
            raw={data.metrics.recall}
            explanation="Out of all actual outperforming events, how many did the model catch?"
            context="High recall means fewer missed opportunities, but often comes at the cost of lower precision."
          />
          <MetricCard
            label="Sample Count"
            value={formatCount(data.metrics.sample_count)}
            raw={data.metrics.sample_count}
            explanation="The number of historical events used in the held-out validation set."
            context="Larger sample sizes yield more trustworthy and durable metrics."
          />
          <MetricCard
            label="Prevalence"
            value={numeric(data.metrics.positive_class_prevalence, true)}
            raw={data.metrics.positive_class_prevalence}
            explanation="The percentage of historical comparable events that actually outperformed the benchmark."
            context="Indicates the base rate of success before applying the ML model."
          />
        </div>
      )}
    </Panel>
  );
}
