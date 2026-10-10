import { RadarResponse, CompanyResponse, PricesResponse, InsidersResponse } from '../types/api';
import { StatisticsResponse, PredictionResponse } from '../types/research';export const DEV_MOCK_RADAR: RadarResponse = {
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

export const DEV_MOCK_PRICES: PricesResponse = {
  ticker: "AAPL",
  prices: Array.from({ length: 60 }).map((_, i) => ({
    date: new Date(2026, 8, i + 1).toISOString().split('T')[0],
    open: 150 + Math.random() * 10,
    high: 160 + Math.random() * 10,
    low: 140 + Math.random() * 10,
    close: 155 + Math.random() * 10,
    adjusted_close: 155 + Math.random() * 10,
    analysis_price: 155 + Math.random() * 10,
    volume: 1000000 + Math.random() * 500000
  }))
};

export const DEV_MOCK_INSIDERS: InsidersResponse = {
  ticker: "AAPL",
  transactions: [
    {
      transaction_id: "tx-1",
      accession_number: "0001",
      source_type: "edgar",
      document_type: "4",
      insider_name: "Tim Cook",
      insider_role: "Chief Executive Officer",
      transaction_date: "2026-09-15",
      filing_date: "2026-09-17",
      accepted_at: "2026-09-17T16:30:00Z",
      public_event_day: "2026-09-18",
      transaction_code: "P",
      acquired_or_disposed: "A",
      derivative_flag: false,
      security_title: "Common Stock",
      shares: 10000,
      price: 152.50,
      transaction_value: 1525000,
      shares_owned_after: 3000000,
      direct_or_indirect: "D",
      aff10b5one: false,
      is_amendment: false,
      is_p0_qualifying: true
    }
  ],
  research_events: [
    {
      research_event_id: "event-1", public_event_day: "2026-09-18", information_date: "2026-09-17",
      source_transaction_count: 1, source_filing_count: 1, aggregate_purchase_value: 1525000,
      unique_buyer_count: null, role_bucket: "Executive", has_executive: true,
      has_director: false, has_other: false, has_cfo: null,
      max_valid_ownership_change_pct: null, any_new_position_flag: null,
    }
  ]
};

export const DEV_MOCK_STATISTICS: StatisticsResponse = {
  ticker: "AAPL",
  research_event_id: "evt-1",
  public_event_day: "2026-10-08",
  anomaly: { score: 90, mahalanobis_distance: null, reference_population: null, reference_count: null, status: "partial_diagnostics_unavailable" },
  activity: { score: 80, recent_purchase_rate: null, historical_purchase_rate: null, rate_ratio: null, buyers_30d: null, reference_population: null, status: "partial_diagnostics_unavailable" },
  event_study: { car5: 0.05, car30: 0.12, car90: 0.25, status: "complete" },
  statistical_validation: {
    comparable_event_count: 45,
    cohort_definition: "Tech sector executives acquiring > $1M",
    mean_car30: 0.08,
    bootstrap_ci_95: { lower: 0.02, upper: 0.14 },
    randomization_p_value: 0.03,
    statistical_score: 75,
    status: "complete"
  },
  market: { stock_return_90d: null, sector_return_90d: null, drawdown: null, dislocation_score: 85, status: "partial_diagnostics_unavailable" }
};

export const DEV_MOCK_PREDICTION: PredictionResponse = {
  ticker: "AAPL",
  research_event_id: "evt-1",
  model_name: "XGBoost-v2",
  outperformance_probability: 0.65,
  classification_threshold: null,
  metrics: null,
  status: "partial_evaluation_unavailable"
};
