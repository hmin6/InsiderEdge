import { RadarResponse, CompanyResponse } from '../types/api';

export const DEV_MOCK_RADAR: RadarResponse = {
  items: [
    {
      ticker: "AAPL",
      company_name: "Apple Inc.",
      sector: "Technology",
      public_event_day: "2026-10-08",
      insider_signal_summary: "Multiple executive purchases (DEV MOCK)",
      insider_edge_score: 85,
      anomaly_score: 90,
      activity_score: 80,
      statistical_score: 75,
      dislocation_score: 85,
      ml_outperformance_probability: 0.65,
      score_status: "complete",
      unavailable_components: []
    }
  ]
};

export const DEV_MOCK_COMPANY: CompanyResponse = {
  ticker: "AAPL",
  cik: "0000320193",
  company_name: "Apple Inc.",
  sector: "Technology",
  industry: "Consumer Electronics",
  latest_public_event_day: "2026-10-08",
  latest_signal: DEV_MOCK_RADAR.items[0]
};