// Fields consumed by resilience panels from API_CONTRACT.md.
export type StatisticsResponse = {
  ticker: string; research_event_id: string; public_event_day: string;
  anomaly: { score: number | null; status: string };
  activity: { score: number | null; status: string };
  event_study: { car5: number | null; car30: number | null; car90: number | null; status: string };
  statistical_validation: { comparable_event_count: number | null; cohort_definition: string | null; mean_car30: number | null; bootstrap_ci_95: { lower: number; upper: number } | null; randomization_p_value: number | null; statistical_score: number | null; status: string };
};
export type PredictionResponse = {
  ticker: string; research_event_id: string; model_name: string | null;
  outperformance_probability: number | null; status: string;
};
