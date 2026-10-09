export type RadarItem = {
  ticker: string;
  company_name: string;
  sector: string | null;
  public_event_day: string;
  insider_signal_summary: string | null;
  insider_edge_score: number | null;
  anomaly_score: number | null;
  activity_score: number | null;
  statistical_score: number | null;
  dislocation_score: number | null;
  ml_outperformance_probability: number | null;
  score_status: "complete" | "partial" | "insufficient_data";
  unavailable_components: string[];
};

export type RadarResponse = {
  items: RadarItem[];
};

export type CompanyResponse = {
  ticker: string;
  cik: string | null;
  company_name: string;
  sector: string | null;
  industry: string | null;
  latest_public_event_day: string | null;
  latest_signal: RadarItem | null;
};