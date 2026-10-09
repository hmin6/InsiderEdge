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

export type PricePoint = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  adjusted_close: number;
  analysis_price: number;
  volume: number;
};

export type PricesResponse = {
  ticker: string;
  prices: PricePoint[];
};

export type InsiderTransaction = {
  transaction_id: string;
  accession_number: string | null;
  source_type: string;
  document_type: string;
  insider_name: string;
  insider_role: string;
  transaction_date: string;
  filing_date: string;
  accepted_at: string | null;
  public_event_day: string | null;
  transaction_code: string;
  acquired_or_disposed: string | null;
  derivative_flag: boolean;
  security_title: string | null;
  shares: number | null;
  price: number | null;
  transaction_value: number | null;
  shares_owned_after: number | null;
  direct_or_indirect: string | null;
  aff10b5one: boolean;
  is_amendment: boolean;
  is_p0_qualifying: boolean;
};

export type InsidersResponse = {
  ticker: string;
  transactions: InsiderTransaction[];
  research_events: any[];
};