// Response shapes from the authoritative API_CONTRACT.md.
export type StatisticsResponse = {
  ticker: string; research_event_id: string; public_event_day: string;
  anomaly: { score: number | null; mahalanobis_distance: number | null; reference_population: string | null; reference_count: number | null; status: string };
  activity: { score: number | null; recent_purchase_rate: number | null; historical_purchase_rate: number | null; rate_ratio: number | null; buyers_30d: number | null; reference_population: string | null; status: string };
  event_study: { car5: number | null; car30: number | null; car90: number | null; status: string };
  statistical_validation: { comparable_event_count: number | null; cohort_definition: string | null; mean_car30: number | null; bootstrap_ci_95: { lower: number; upper: number } | null; randomization_p_value: number | null; statistical_score: number | null; status: string };
  market: { stock_return_90d: number | null; sector_return_90d: number | null; drawdown: number | null; dislocation_score: number | null; status: string };
};
export type PredictionResponse = {
  ticker: string; research_event_id: string; model_name: string | null;
  outperformance_probability: number | null;
  classification_threshold: number | null;
  metrics: {
    roc_auc: number | null; brier_score: number | null; precision: number | null;
    recall: number | null; f1: number | null; sample_count: number | null;
    positive_class_prevalence: number | null; split_start: string | null; split_end: string | null;
  } | null;
  status: string;
};
