import { Link } from "react-router-dom";
import { fetchRadar, usingResearchMocks } from "../api/client";
import { useResource } from '../hooks/useResource';
import { rankRadar, numeric } from '../components/ResearchStates';
import {
  AppShell,
  PageContainer,
  ProductHeader,
  ScoreStatusBadge,
  PanelSkeleton,
  StateMessage,
} from "../components";

export default function RadarPage() {
  const resource = useResource('radar', fetchRadar);
  const { loading, error, retry } = resource;
  const data = rankRadar(resource.data?.items || []);

  const shellNavigation = [{ label: "Radar", href: "/", current: true }];

  if (loading) {
    return (
      <AppShell navigation={shellNavigation}>
        <PageContainer>
          <ProductHeader title="Market Dislocation Radar" />
          <PanelSkeleton label="Loading Radar..." rows={5} />
        </PageContainer>
      </AppShell>
    );
  }

  if (error) {
    return (
      <AppShell navigation={shellNavigation}>
        <PageContainer>
          <ProductHeader title="Market Dislocation Radar" />
          <StateMessage kind="error" title="Unable to load Radar" actions={<button className="ie-button" onClick={retry}>Retry Radar</button>}>
            Failed to fetch current signals.
          </StateMessage>
        </PageContainer>
      </AppShell>
    );
  }

  return (
    <AppShell navigation={shellNavigation}>
      <PageContainer className="ie-reveal">
        <ProductHeader
          eyebrow="Research Queue"
          title="Market Dislocation Radar"
          description="High score indicates research priority, not an investment recommendation."
        />

        {usingResearchMocks && <p className="ie-muted">Development mock data · Not measured research results.</p>}
        {!data.length && <StateMessage title="No research events available" actions={<button className="ie-button" onClick={retry}>Refresh Radar</button>}>No ranked signals are available. Please check again later.</StateMessage>}
        <div className="ie-panel ie-table-scroll ie-radar-region" tabIndex={0} aria-label="Research priority table">
          <table className="ie-table">
            <thead>
              <tr>
                <th>Company</th>
                <th>Signal Summary</th>
                <th>Status</th>
                <th className="ie-number">Anomaly</th>
                <th className="ie-number">Activity</th>
                <th className="ie-number">Dislocation</th>
                <th className="ie-number">ML Prob</th>
                <th className="ie-number">IE Score</th>
              </tr>
            </thead>
            <tbody>
              {data.map((item) => (
                <tr key={`${item.ticker}-${item.public_event_day}`}>
                  <td>
                    <Link
                      to={`/company/${item.ticker}`}
                      style={{ textDecoration: "none" }}
                    >
                      <strong>{item.ticker}</strong>
                      <br />
                      <span className="ie-muted">{item.company_name}</span>
                    </Link>
                  </td>
                  <td>{item.insider_signal_summary || "—"}</td>
                  <td>
                    <ScoreStatusBadge status={item.score_status} />
                  </td>
                  <td className="ie-number">
                    {numeric(item.anomaly_score)}
                  </td>
                  <td className="ie-number">
                    {numeric(item.activity_score)}
                  </td>
                  <td className="ie-number">
                    {numeric(item.dislocation_score)}
                  </td>
                  <td className="ie-number">
                    {numeric(item.ml_outperformance_probability, true)}
                  </td>
                  <td className="ie-number">
                    <strong>
                      {numeric(item.insider_edge_score)}
                    </strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </PageContainer>
    </AppShell>
  );
}
