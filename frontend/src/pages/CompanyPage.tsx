import { useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { fetchCompany, fetchPrices, fetchInsiders, fetchStatistics, fetchPrediction, usingResearchMocks } from '../api/client';
import { ApiError } from '../api/http';
import { useResource } from '../hooks/useResource';
import { AppShell, PageContainer, ProductHeader, Panel, PanelSkeleton, StateMessage, InsiderEdgeScore, PriceChart, AnalystBrief, ExplainSignal, PanelBoundary, StatisticsEvidence, PredictionEvidence, numeric } from '../components';

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

          {/* Section 5, 6, 7: Detailed Statistics Panels */}
          {data.latest_signal ? (
            <div className="ie-grid">
              <Panel title="Quantitative Evidence">
                <dl className="ie-stack">
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <dt className="ie-muted">Statistical Anomaly</dt>
                    <dd className="ie-number"><strong>{data.latest_signal.anomaly_score?.toFixed(1) || '—'}</strong> / 100</dd>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <dt className="ie-muted">Activity Concentration</dt>
                    <dd className="ie-number"><strong>{data.latest_signal.activity_score?.toFixed(1) || '—'}</strong> / 100</dd>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <dt className="ie-muted">Market Dislocation</dt>
                    <dd className="ie-number"><strong>{data.latest_signal.dislocation_score?.toFixed(1) || '—'}</strong> / 100</dd>
                  </div>
                </dl>
              </Panel>

              <Panel title="Machine Learning Prediction">
                <dl className="ie-stack">
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <dt className="ie-muted">Outperformance Probability</dt>
                    <dd className="ie-number">
                      <strong>
                        {data.latest_signal.ml_outperformance_probability !== null 
                          ? `${(data.latest_signal.ml_outperformance_probability * 100).toFixed(1)}%` 
                          : '—'}
                      </strong>
                    </dd>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <dt className="ie-muted">Model Status</dt>
                    <dd>
                      {data.latest_signal.ml_outperformance_probability !== null 
                        ? <span className="ie-badge ie-badge--info">Inference complete</span>
                        : <span className="ie-badge ie-badge--neutral">Data insufficient</span>}
                    </dd>
                  </div>
                </dl>
              </Panel>
            </div>
          ) : null}

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
  const { ticker = '' } = useParams();
  // A keyed resource scope prevents old-company values or AI results surviving navigation.
  return <CompanyResearch key={ticker.toUpperCase()} ticker={ticker.toUpperCase()} />;
}
function CompanyResearch({ ticker }: { ticker: string }) {
  const company = useResource(ticker, useCallback((signal: AbortSignal) => fetchCompany(ticker, signal), [ticker]));
  const prices = useResource(ticker, useCallback((signal: AbortSignal) => fetchPrices(ticker, signal), [ticker]));
  const insiders = useResource(ticker, useCallback((signal: AbortSignal) => fetchInsiders(ticker, signal), [ticker]));
  const statistics = useResource(ticker, useCallback((signal: AbortSignal) => fetchStatistics(ticker, signal), [ticker]));
  const prediction = useResource(ticker, useCallback((signal: AbortSignal) => fetchPrediction(ticker, signal), [ticker]));
  const data = company.data;
  const navigation = [{ label: 'Radar', href: '/' }, { label: 'Company', href: `/company/${encodeURIComponent(ticker)}`, current: true }];
  const retry = (action: () => void) => <button className="ie-button" onClick={action}>Retry</button>;
  const eventKey = data?.latest_public_event_day || 'no-event';
  return <AppShell navigation={navigation}><PageContainer>
    <ProductHeader title={data ? `${data.ticker} · ${data.company_name}` : ticker || 'Company Research'} description={data?.sector || 'Company Research'} actions={<Link to="/" className="ie-button">Back to Radar</Link>} />
    {usingResearchMocks && <p className="ie-muted">Development mock data · Not measured research results.</p>}
    {company.loading ? <div className="ie-stack"><PanelSkeleton label="Loading company score" rows={8} /><div className="ie-grid"><PanelSkeleton label="Loading research evidence" /><PanelSkeleton label="Loading price history" /></div></div>
      : company.error || !data ? <div className="ie-reserved-panel"><StateMessage kind="error" title={company.error instanceof ApiError && company.error.status === 404 ? 'Unknown ticker' : 'Unable to load company data'} actions={retry(company.retry)}>Research data for this company could not be loaded. Return to Radar or retry.</StateMessage></div>
      : <div className="ie-stack">
        <PanelBoundary label="Score">{data.latest_signal ? <InsiderEdgeScore evidence={data.latest_signal} /> : <Panel title="InsiderEdge Score"><StateMessage title="No recent insider events">No recent qualifying insider event is available. No score has been invented.</StateMessage></Panel>}</PanelBoundary>
        <div className="ie-grid">
          <Panel title="Recent Insider Activity">
            {insiders.loading ? <PanelSkeleton label="Loading insider history" rows={3} /> : insiders.error ? <StateMessage kind="error" title="Insider history unavailable" actions={retry(insiders.retry)}>Other company results remain usable.</StateMessage> : !insiders.data?.research_events.length ? <StateMessage title="No recent insider events">No qualifying research events are available in this history.</StateMessage> : <p>{data.latest_signal?.insider_signal_summary || 'Insider events are available in the historical record.'}</p>}
          </Panel>
          <Panel title="Market Context"><p>Dislocation score: {numeric(data.latest_signal?.dislocation_score)}</p></Panel>
        </div>
        <PanelBoundary label="Statistics">{statistics.loading ? <PanelSkeleton label="Loading statistics" rows={8} /> : statistics.error || !statistics.data ? <Panel title="Statistical Evidence"><StateMessage kind="error" title="Statistical evidence unavailable" actions={retry(statistics.retry)}>Anomaly history, event-study CAR5/CAR30/CAR90, and comparable-event evidence could not be loaded. Missing values are not zero.</StateMessage></Panel> : <StatisticsEvidence data={statistics.data} />}</PanelBoundary>
        <PanelBoundary label="Prediction">{prediction.loading ? <PanelSkeleton label="Loading model prediction" /> : prediction.error || !prediction.data ? <Panel title="ML Prediction"><StateMessage title="Model prediction unavailable" actions={retry(prediction.retry)}>Model probability and held-out evidence could not be loaded. The score and other research results remain visible.</StateMessage></Panel> : <PredictionEvidence data={prediction.data} />}</PanelBoundary>
        <PanelBoundary label="Price history"><Panel title="Historical Price & Events"><div className="ie-chart-region">
          {prices.loading ? <PanelSkeleton label="Loading price history" rows={8} /> : prices.error ? <StateMessage kind="error" title="Price history unavailable" actions={retry(prices.retry)}>Price history could not be loaded. Other evidence remains usable.</StateMessage> : !prices.data?.prices.some(point => Number.isFinite(point.analysis_price) && point.analysis_price > 0) ? <StateMessage title="No price history available">No usable adjustment-aware price history is available.</StateMessage> : <><PriceChart prices={prices.data.prices} transactions={insiders.data?.transactions || []} />{insiders.error && <p className="ie-muted">Insider markers unavailable; the price series remains visible.</p>}</>}
        </div></Panel></PanelBoundary>
        <PanelBoundary label="AI explanation" key={`explain:${eventKey}`}><ExplainSignal ticker={data.ticker} evidenceKey={eventKey} evidence={<p className="ie-muted">AI interprets the quantitative evidence above; it does not calculate the signal.</p>} /></PanelBoundary>
        <PanelBoundary label="Analyst brief" key={`brief:${eventKey}`}><AnalystBrief ticker={data.ticker} evidenceKey={eventKey} /></PanelBoundary>
      </div>}
  </PageContainer></AppShell>;
}
