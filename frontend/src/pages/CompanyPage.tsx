import { SnowflakeResearch } from "../components/SnowflakeResearch";
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
  EventStudyEvidence,
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
  const retry = (action: () => void) => (
    <button className="ie-button" onClick={action}>
      Retry
    </button>
  );
  const eventKey = data?.latest_public_event_day || "no-event";

  return (
    <AppShell navigation={[]}>
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
            {/* Score Component */}
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

            {/* Top Grid: Stacks Insider/Stats on Left, Market/Prediction on Right. alignItems: start prevents stretching! */}
            <div className="ie-grid" style={{ alignItems: "stretch" }}>
              {/* Left Column */}
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

                {/* The inner div flexGrow: 1 ensures the Statistics panels stretch down to align with the right column */}
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
                      <StatisticsEvidence data={statistics.data} />
                    )}
                  </div>
                </PanelBoundary>
              </div>

              {/* Right Column */}
              <div
                className="ie-stack"
                style={{
                  display: "flex",
                  flexDirection: "column",
                  height: "100%",
                }}
              >
                <PanelBoundary label="Prediction">
                  {prediction.loading ? (
                    <PanelSkeleton label="Loading model prediction" rows={2} />
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

                {/* The inner div flexGrow: 1 ensures Event Study fills out the remaining vertical space */}
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
            

            {/* Price Chart */}
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

            <PanelBoundary
              label="Snowflake research"
              key={`snowflake:${eventKey}`}
            >
              <SnowflakeResearch ticker={data.ticker} />
            </PanelBoundary>

            {/* AI Side-by-Side Grid */}
            <div className="ie-grid" style={{ alignItems: "start" }}>
              <PanelBoundary label="AI explanation" key={`explain:${eventKey}`}>
                <ExplainSignal
                  ticker={data.ticker}
                  evidenceKey={eventKey}
                  evidence={null}
                />
              </PanelBoundary>

              <PanelBoundary label="Analyst brief" key={`brief:${eventKey}`}>
                <AnalystBrief ticker={data.ticker} evidenceKey={eventKey} />
              </PanelBoundary>
            </div>
            <p
              className="ie-muted"
              style={{ textAlign: "center", paddingTop: "8px" }}
            >
              AI interprets the quantitative evidence above; it does not
              calculate the signal.
            </p>
          </div>
        )}
      </PageContainer>
    </AppShell>
  );
}
