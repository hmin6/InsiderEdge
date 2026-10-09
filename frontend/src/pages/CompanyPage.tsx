import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchCompany, fetchPrices, fetchInsiders } from "../api/client";
import {
  CompanyResponse,
  PricesResponse,
  InsidersResponse,
} from "../types/api";
import {
  AppShell,
  PageContainer,
  ProductHeader,
  Panel,
  PanelSkeleton,
  StateMessage,
  InsiderEdgeScore,
  PriceChart,
} from "../components";

export default function CompanyPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const [data, setData] = useState<CompanyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [pricesData, setPricesData] = useState<PricesResponse | null>(null);
  const [insidersData, setInsidersData] = useState<InsidersResponse | null>(
    null,
  );

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    setError(false);
    Promise.all([
      fetchCompany(ticker),
      fetchPrices(ticker),
      fetchInsiders(ticker),
    ])
      .then(([compRes, priceRes, insRes]) => {
        setData(compRes);
        setPricesData(priceRes);
        setInsidersData(insRes);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, [ticker]);

  const shellNavigation = [
    { label: "Radar", href: "/" },
    { label: "Company", href: `/company/${ticker}`, current: true },
  ];

  if (loading) {
    return (
      <AppShell navigation={shellNavigation}>
        <PageContainer>
          <ProductHeader title={`Loading ${ticker || "Company"}...`} />
          <div className="ie-grid">
            <PanelSkeleton label="Loading score" rows={4} />
            <PanelSkeleton label="Loading statistics" rows={4} />
          </div>
        </PageContainer>
      </AppShell>
    );
  }

  if (error || !data) {
    return (
      <AppShell navigation={shellNavigation}>
        <PageContainer>
          <ProductHeader title={ticker || "Company"} />
          <StateMessage kind="error" title="Unable to load company data">
            Could not fetch research data for {ticker}.
          </StateMessage>
          <Link to="/" className="ie-button" style={{ marginTop: "1rem" }}>
            Return to Radar
          </Link>
        </PageContainer>
      </AppShell>
    );
  }

  return (
    <AppShell navigation={shellNavigation}>
      <PageContainer className="ie-reveal">
        <ProductHeader
          eyebrow={
            data.sector
              ? `${data.sector} ${data.industry ? `· ${data.industry}` : ""}`
              : "Company Research"
          }
          title={`${data.ticker} · ${data.company_name}`}
          actions={
            <Link to="/" className="ie-button">
              Back to Radar
            </Link>
          }
        />

        <div className="ie-stack">
          {/* Section 2: Headline InsiderEdge Score */}
          {data.latest_signal ? (
            <InsiderEdgeScore evidence={data.latest_signal} />
          ) : (
            <Panel title="InsiderEdge Score">
              <StateMessage title="No signal available">
                No recent qualifying insider events found for {data.ticker}.
              </StateMessage>
            </Panel>
          )}

          {/* Section 3: Insider Activity & Section 4: Market Context */}
          <div className="ie-grid">
            <Panel title="Recent Insider Activity">
              <p className="ie-muted">
                {data.latest_signal?.insider_signal_summary ||
                  "No recent activity summary."}
              </p>
            </Panel>

            <Panel title="Market Context">
              <p className="ie-muted">
                {data.latest_signal?.dislocation_score
                  ? `Dislocation Score: ${data.latest_signal.dislocation_score.toFixed(1)}`
                  : "Dislocation metrics unavailable."}
              </p>
            </Panel>
          </div>

          {/* Section 5, 6, 7: Statistical & ML Panels (Placeholders for Issue #23) */}
          <div className="ie-grid">
            <Panel title="Anomaly & Activity Evidence">
              <p className="ie-muted">
                Detailed statistics will be implemented in Issue #23.
              </p>
            </Panel>
            <Panel title="ML Prediction">
              <p className="ie-muted">
                Detailed prediction metrics will be implemented in Issue #23.
              </p>
            </Panel>
          </div>

          {/* Section 8: Price Chart */}
          <Panel title="Historical Price & Events">
            {pricesData && insidersData ? (
              <PriceChart
                prices={pricesData.prices}
                transactions={insidersData.transactions}
              />
            ) : (
              <div
                className="ie-loading"
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  background: "#f6f8fb",
                  borderRadius: "6px",
                }}
              >
                <p className="ie-muted">Chart data unavailable.</p>
              </div>
            )}
          </Panel>

          {/* Section 9 & 10: Gemini & ElevenLabs (Placeholders for Issues #28 & #29) */}
          <div className="ie-grid">
            <Panel title="Gemini Explanation">
              <p className="ie-muted">
                AI explanation will be implemented in Issue #28.
              </p>
            </Panel>
            <Panel title="Analyst Audio Brief">
              <p className="ie-muted">
                ElevenLabs audio will be implemented in Issue #29.
              </p>
            </Panel>
          </div>
        </div>
      </PageContainer>
    </AppShell>
  );
}
