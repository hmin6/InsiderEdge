import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchRadar } from "../api/client";
import { RadarItem } from "../types/api";
import {
  AppShell,
  PageContainer,
  ProductHeader,
  ScoreStatusBadge,
  PanelSkeleton,
  StateMessage,
} from "../components";

export default function RadarPage() {
  const [data, setData] = useState<RadarItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetchRadar()
      .then((res) => {
        const sorted = res.items.sort((a, b) => {
          const scoreA = a.insider_edge_score ?? 0;
          const scoreB = b.insider_edge_score ?? 0;
          return scoreB - scoreA;
        });
        setData(sorted);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, []);

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
          <StateMessage kind="error" title="Unable to load Radar">
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

        <div className="ie-panel ie-table-scroll">
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
                    {item.anomaly_score?.toFixed(1) ?? "—"}
                  </td>
                  <td className="ie-number">
                    {item.activity_score?.toFixed(1) ?? "—"}
                  </td>
                  <td className="ie-number">
                    {item.dislocation_score?.toFixed(1) ?? "—"}
                  </td>
                  <td className="ie-number">
                    {item.ml_outperformance_probability !== null
                      ? `${(item.ml_outperformance_probability * 100).toFixed(1)}%`
                      : "—"}
                  </td>
                  <td className="ie-number">
                    <strong>
                      {item.insider_edge_score?.toFixed(1) ?? "—"}
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
