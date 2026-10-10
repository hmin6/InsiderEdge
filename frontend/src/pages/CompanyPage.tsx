import { useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import {
  fetchCompany,
  fetchPrices,
  fetchInsiders,
  fetchStatistics,
  fetchPrediction,
  usingResearchMocks,
} from "../api/client";
import { ApiError } from "../api/http";
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
  AnalystBrief,
  ExplainSignal,
  PanelBoundary,
  StatisticsEvidence,
  PredictionEvidence,
  numeric,
} from "../components";

export default function CompanyPage() {
  const { ticker = "" } = useParams();
  // A keyed resource scope prevents old-company values or AI results surviving navigation.
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

  const data = company.data;
  const navigation = [
    { label: "Radar", href: "/" },
    {
      label: "Company",
      href: `/company/${encodeURIComponent(ticker)}`,
      current: true,
    },
  ];
  const retry = (action: () => void) => (
    <button className="ie-button" onClick={action}>
      Retry
    </button>
  );
  const eventKey = data?.latest_public_event_day || "no-event";

  return (
    <AppShell navigation={navigation}>
      <PageContainer className="ie-reveal">
        <ProductHeader
          title={
            data
              ? `${data.ticker} · ${data.company_name}`
              : ticker || "Company Research"
          }
          description={data?.sector || "Company Research"}
          actions={
            <Link to="/" className="ie-button">
              Back to Radar
            </Link>
          }
        />
        {usingResearchMocks && (
          <p className="ie-muted" style={{ marginBottom: "24px" }}>
            Development mock data · Not measured research results.
          </p>
        )}

        {company.loading ? (
          <div className="ie-stack">
            <PanelSkeleton label="Loading company score" rows={4} />
            <div className="ie-grid">
              <PanelSkeleton label="Loading insider activity" rows={2} />
              <PanelSkeleton label="Loading market context" rows={2} />
            </div>
            <div className="ie-grid">
              <PanelSkeleton label="Loading statistics" rows={6} />
              <PanelSkeleton label="Loading predictions" rows={6} />
            </div>
            <PanelSkeleton label="Loading price history" rows={8} />
          </div>
        ) : company.error || !data ? (
          <div className="ie-reserved-panel">
            <StateMessage
              kind="error"
              title={
                company.error instanceof ApiError &&
                company.error.status === 404
                  ? "Unknown ticker"
                  : "Unable to load company data"
              }
              actions={retry(company.retry)}
            >
              Research data for this company could not be loaded. Return to
              Radar or retry.
            </StateMessage>
          </div>
        ) : (
          <div className="ie-stack">
            <PanelBoundary label="Score">
              {data.latest_signal ? (
                <InsiderEdgeScore evidence={data.latest_signal} />
              ) : (
                <Panel title="InsiderEdge Score">
                  <StateMessage title="No recent insider events">
                    No recent qualifying insider event is available. No score
                    has been invented.
                  </StateMessage>
                </Panel>
              )}
            </PanelBoundary>

            {/* Row 2: Insider Activity & Market Context */}
            <div className="ie-grid">
              <Panel title="Recent Insider Activity">
                {insiders.loading ? (
                  <PanelSkeleton label="Loading insider history" rows={2} />
                ) : insiders.error ? (
                  <StateMessage
                    kind="error"
                    title="Insider history unavailable"
                    actions={retry(insiders.retry)}
                  >
                    Other company results remain usable.
                  </StateMessage>
                ) : !insiders.data?.research_events.length ? (
                  <StateMessage title="No recent insider events">
                    No qualifying research events are available in this history.
                  </StateMessage>
                ) : (
                  <p style={{ fontSize: "15px", lineHeight: "1.6" }}>
                    {data.latest_signal?.insider_signal_summary ||
                      "Insider events are available in the historical record."}
                  </p>
                )}
              </Panel>

              <Panel title="Market Context">
                <div className="ie-metric-grid" style={{ marginTop: 0 }}>
                  <div className="ie-metric-card">
                    <div className="ie-metric-label">Dislocation Score</div>
                    <div className="ie-metric-value">
                      {numeric(data.latest_signal?.dislocation_score)}
                    </div>
                  </div>
                </div>
              </Panel>
            </div>

            {/* Row 3: Statistics & Prediction */}
            <div className="ie-grid">
              <PanelBoundary label="Statistics">
                {statistics.loading ? (
                  <PanelSkeleton label="Loading statistics" rows={6} />
                ) : statistics.error || !statistics.data ? (
                  <Panel title="Statistical Evidence">
                    <StateMessage
                      kind="error"
                      title="Statistical evidence unavailable"
                      actions={retry(statistics.retry)}
                    >
                      Missing values are not zero.
                    </StateMessage>
                  </Panel>
                ) : (
                  <StatisticsEvidence data={statistics.data} />
                )}
              </PanelBoundary>

              <PanelBoundary label="Prediction">
                {prediction.loading ? (
                  <PanelSkeleton label="Loading model prediction" rows={6} />
                ) : prediction.error || !prediction.data ? (
                  <Panel title="ML Prediction">
                    <StateMessage
                      title="Model prediction unavailable"
                      actions={retry(prediction.retry)}
                    >
                      Model probability could not be loaded. The score and other
                      research results remain visible.
                    </StateMessage>
                  </Panel>
                ) : (
                  <PredictionEvidence data={prediction.data} />
                )}
              </PanelBoundary>
            </div>

            {/* Row 4: Chart */}
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
                      Price history could not be loaded. Other evidence remains
                      usable.
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

            {/* Row 5: AI Explanation & Audio Brief */}
            <div className="ie-grid">
              <PanelBoundary label="AI explanation" key={`explain:${eventKey}`}>
                <ExplainSignal
                  ticker={data.ticker}
                  evidenceKey={eventKey}
                  evidence={
                    <p className="ie-muted" style={{ marginBottom: "16px" }}>
                      AI interprets the quantitative evidence above; it does not
                      calculate the signal.
                    </p>
                  }
                />
              </PanelBoundary>

              <PanelBoundary label="Analyst brief" key={`brief:${eventKey}`}>
                <AnalystBrief ticker={data.ticker} evidenceKey={eventKey} />
              </PanelBoundary>
            </div>
          </div>
        )}
      </PageContainer>
    </AppShell>
  );
}
