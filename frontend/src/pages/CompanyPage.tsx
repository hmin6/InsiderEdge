import { AIResearchAssistant } from "../components/AIResearchAssistant";
import { useCallback, useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import {
  Joyride as ReactJoyride,
  Step,
  TooltipRenderProps,
} from "react-joyride";
import {
  fetchCompany,
  fetchPrices,
  fetchInsiders,
  fetchStatistics,
  fetchPrediction,
  usingResearchMocks,
} from "../api/client";
import { useResource } from "../hooks/useResource";
import {
  AppShell,
  PageContainer,
  ProductHeader,
  Panel,
  PanelSkeleton,
  StateMessage,
  InsiderEdgeScore,
  PriceChart,
  PanelBoundary,
  EventStudyEvidence,
  StatisticsEvidence,
  PredictionEvidence,
} from "../components";

// --- START OF TOUR GUIDE IMPLEMENTATION ---
const MascotTooltip = ({
  index,
  step,
  backProps,
  primaryProps,
  skipProps,
  tooltipProps,
  isLastStep,
}: TooltipRenderProps) => (
  <div
    {...tooltipProps}
    style={{
      display: "flex",
      alignItems: "center",
      backgroundColor: "var(--ie-panel)",
      padding: "20px",
      borderRadius: "16px",
      color: "var(--ie-text)",
      maxWidth: "450px",
      gap: "15px",
      boxShadow: "0 10px 30px rgba(0,0,0,0.5)",
      border: "1px solid var(--ie-border)",
      backdropFilter: "blur(12px)",
    }}
  >
    <div style={{ flexShrink: 0 }}>
      {/* Assuming you place mascot.png in the frontend/public folder */}
      <img
        src="/mascot.png"
        alt="Agent Mascot"
        style={{
          width: "70px",
          height: "70px",
          imageRendering: "pixelated",
          borderRadius: "50%",
        }}
      />
    </div>
    <div style={{ flexGrow: 1 }}>
      <div
        style={{
          fontSize: "15px",
          marginBottom: "15px",
          lineHeight: "1.5",
        }}
      >
        {step.content}
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px" }}>
        <button
          {...skipProps}
          className="ie-button"
          style={{
            background: "transparent",
            border: "none",
            color: "var(--ie-muted)",
          }}
        >
          Skip
        </button>

        {index > 0 && (
          <button
            {...backProps}
            className="ie-button"
            style={{ background: "transparent", border: "none" }}
          >
            Back
          </button>
        )}
        <button {...primaryProps} className="ie-button ie-button--primary">
          {isLastStep ? "Got it!" : "Next"}
        </button>
      </div>
    </div>
  </div>
);

const tourSteps: Step[] = [
  {
    target: "body",
    placement: "center",
    content:
      "Welcome to InsiderEdge! Let me show you how to read this institutional-grade quantitative research.",
  },
  {
    target: ".tour-score-panel",
    content:
      "This is the overall InsiderEdge Score. It ranks the research priority of this event from 0-100 based on a blend of the components below.",
    placement: "bottom",
  },
  {
    target: ".tour-activity-panel",
    content:
      "Anomaly & Activity measures how unusual this insider buying is. We look at Mahalanobis distances and 30-day clustering to detect true conviction.",
    placement: "right",
  },
  {
    target: ".tour-dislocation-panel",
    content:
      "Market Dislocation evaluates if the stock is being bought into severe weakness or sector-wide drops, signaling a value setup.",
    placement: "right",
  },
  {
    target: ".tour-prediction-panel",
    content:
      "Our Machine Learning engine (XGBoost or Logistic Regression) predicts the exact probability that this stock will beat the benchmark over the next 30 days.",
    placement: "left",
  },
  {
    target: ".tour-event-study-panel",
    content:
      "The Event Study compares this exact setup against historical comparables, proving the edge using p-values, bootstrap intervals, and Mean CAR30.",
    placement: "left",
  },
  {
    target: ".tour-ai-panel",
    content:
      "Finally, our AI Research Assistant uses Gemini and Snowflake Cortex to contextualize the filings, and ElevenLabs to generate an audio analyst brief!",
    placement: "top",
  },
];
// --- END OF TOUR GUIDE IMPLEMENTATION ---

export default function CompanyPage() {
  const { ticker = "" } = useParams();
  return (
    <CompanyResearch key={ticker.toUpperCase()} ticker={ticker.toUpperCase()} />
  );
}

function CompanyResearch({ ticker }: { ticker: string }) {
  const company = useResource(
    ticker,
    useCallback(
      (signal: AbortSignal) => fetchCompany(ticker, signal),
      [ticker],
    ),
  );
  const prices = useResource(
    ticker,
    useCallback((signal: AbortSignal) => fetchPrices(ticker, signal), [ticker]),
  );
  const insiders = useResource(
    ticker,
    useCallback(
      (signal: AbortSignal) => fetchInsiders(ticker, signal),
      [ticker],
    ),
  );
  const statistics = useResource(
    ticker,
    useCallback(
      (signal: AbortSignal) => fetchStatistics(ticker, signal),
      [ticker],
    ),
  );
  const prediction = useResource(
    ticker,
    useCallback(
      (signal: AbortSignal) => fetchPrediction(ticker, signal),
      [ticker],
    ),
  );

  const [runTour, setRunTour] = useState(false);
  const [tourKey, setTourKey] = useState(0);

  // Automatically start the tour the first time the page loads if data is successful
  useEffect(() => {
    const hasSeenTour = localStorage.getItem("ie_has_seen_tour");
    if (!hasSeenTour && company.data) {
      setRunTour(true);
    }
  }, [company.data]);

  const handleJoyrideCallback = (data: any) => {
    const { status } = data;
    if (["finished", "skipped"].includes(status)) {
      setRunTour(false);
      localStorage.setItem("ie_has_seen_tour", "true");
    }
  };

  const startTourManually = () => {
    setTourKey((prev) => prev + 1);
    setRunTour(true);
  };

  const data = company.data;
  const retry = (action: () => void) => (
    <button className="ie-button" onClick={action}>
      Retry
    </button>
  );
  const eventKey = data?.latest_public_event_day || "no-event";

  return (
    <AppShell navigation={[]}>
      {/* @ts-ignore - Bypass strict joyride v3 type mismatches */}
      <ReactJoyride
        {...({
          key: tourKey,
          steps: tourSteps,
          run: runTour,
          continuous: true,
          tooltipComponent: MascotTooltip,
          beaconComponent: () => null,
          callback: handleJoyrideCallback,
          styles: {
            overlay: { zIndex: 10000 },
          },
        } as any)}
      />

      <PageContainer className="ie-reveal">
        <ProductHeader
          title={
            data
              ? `${data.ticker} · ${data.company_name}`
              : ticker || "Company Research"
          }
          description={data?.sector || "Company Research"}
          actions={
            <>
              <button className="ie-button" onClick={startTourManually}>
                🧭 Take a Tour
              </button>
              <Link to="/" className="ie-button ie-button--primary">
                Back to Radar
              </Link>
            </>
          }
        />

        {usingResearchMocks && (
          <p className="ie-muted" style={{ marginBottom: "24px" }}>
            Development mock data · Not measured research results.
          </p>
        )}

        {company.loading ? (
          <div className="ie-stack">
            <PanelSkeleton label="Loading workspace" rows={8} />
          </div>
        ) : company.error || !data ? (
          <StateMessage
            kind="error"
            title="Unable to load company data"
            actions={retry(company.retry)}
          >
            Return to Radar or retry.
          </StateMessage>
        ) : (
          <div className="ie-stack">
            <div className="tour-score-panel">
              <PanelBoundary label="Score">
                {data.latest_signal ? (
                  <InsiderEdgeScore evidence={data.latest_signal} />
                ) : (
                  <Panel title="InsiderEdge Score">
                    <StateMessage title="No recent events">
                      No score has been invented.
                    </StateMessage>
                  </Panel>
                )}
              </PanelBoundary>
            </div>

            <div className="ie-grid" style={{ alignItems: "stretch" }}>
              <div
                className="ie-stack"
                style={{
                  display: "flex",
                  flexDirection: "column",
                  height: "100%",
                }}
              >
                <Panel title="Recent Insider Activity">
                  {insiders.loading ? (
                    <PanelSkeleton label="Loading insider history" rows={2} />
                  ) : !insiders.data?.research_events.length ? (
                    <StateMessage title="No recent insider events">
                      No qualifying research events are available in this
                      history.
                    </StateMessage>
                  ) : (
                    <p style={{ fontSize: "15px", lineHeight: "1.6" }}>
                      {data.latest_signal?.insider_signal_summary ||
                        "Insider events are available in the historical record."}
                    </p>
                  )}
                </Panel>

                <PanelBoundary label="Statistics">
                  <div
                    style={{
                      flexGrow: 1,
                      display: "flex",
                      flexDirection: "column",
                    }}
                  >
                    {statistics.loading ? (
                      <PanelSkeleton label="Loading statistics" rows={4} />
                    ) : statistics.error || !statistics.data ? (
                      <Panel title="Statistical Evidence" style={{ flex: 1 }}>
                        <StateMessage
                          kind="error"
                          title="Statistical evidence unavailable"
                        >
                          Missing values are not zero.
                        </StateMessage>
                      </Panel>
                    ) : (
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: "16px",
                          height: "100%",
                        }}
                      >
                        <div
                          className="tour-activity-panel"
                          style={{ flex: 1 }}
                        >
                          <StatisticsEvidence data={statistics.data} />
                        </div>
                      </div>
                    )}
                  </div>
                </PanelBoundary>
              </div>

              <div
                className="ie-stack"
                style={{
                  display: "flex",
                  flexDirection: "column",
                  height: "100%",
                }}
              >
                <div className="tour-prediction-panel">
                  <PanelBoundary label="Prediction">
                    {prediction.loading ? (
                      <PanelSkeleton
                        label="Loading model prediction"
                        rows={2}
                      />
                    ) : prediction.error || !prediction.data ? (
                      <Panel title="ML Prediction">
                        <StateMessage title="Model prediction unavailable">
                          Model probability could not be loaded.
                        </StateMessage>
                      </Panel>
                    ) : (
                      <PredictionEvidence data={prediction.data} />
                    )}
                  </PanelBoundary>
                </div>

                <div
                  className="tour-event-study-panel"
                  style={{
                    flexGrow: 1,
                    display: "flex",
                    flexDirection: "column",
                  }}
                >
                  <PanelBoundary label="Event Study">
                    <div
                      style={{
                        flexGrow: 1,
                        display: "flex",
                        flexDirection: "column",
                      }}
                    >
                      {statistics.loading ? (
                        <PanelSkeleton label="Loading event study" rows={4} />
                      ) : statistics.error || !statistics.data ? null : (
                        <EventStudyEvidence data={statistics.data} />
                      )}
                    </div>
                  </PanelBoundary>
                </div>
              </div>
            </div>

            <PanelBoundary label="Price history">
              <Panel title="Historical Price & Events">
                <div className="ie-chart-region">
                  {prices.loading ? (
                    <PanelSkeleton label="Loading price history" rows={8} />
                  ) : prices.error ? (
                    <StateMessage
                      kind="error"
                      title="Price history unavailable"
                      actions={retry(prices.retry)}
                    >
                      Price history could not be loaded.
                    </StateMessage>
                  ) : !prices.data?.prices.some(
                      (point) =>
                        point.analysis_price !== null &&
                        Number.isFinite(point.analysis_price) &&
                        point.analysis_price > 0,
                    ) ? (
                    <StateMessage title="No price history available">
                      No usable adjustment-aware price history is available.
                    </StateMessage>
                  ) : (
                    <>
                      <PriceChart
                        prices={prices.data.prices}
                        transactions={insiders.data?.transactions || []}
                      />
                      {insiders.error && (
                        <p className="ie-muted" style={{ marginTop: "12px" }}>
                          Insider markers unavailable; the price series remains
                          visible.
                        </p>
                      )}
                    </>
                  )}
                </div>
              </Panel>
            </PanelBoundary>

            <div className="tour-ai-panel">
              <AIResearchAssistant
                ticker={data.ticker}
                evidenceKey={eventKey}
              />
            </div>
          </div>
        )}
      </PageContainer>
    </AppShell>
  );
}
