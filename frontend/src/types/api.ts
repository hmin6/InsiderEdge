export type AvailabilityStatus = "not_scored" | "complete" | "partial" | "insufficient_data";

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
  availability_status?: AvailabilityStatus | null;
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
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  adjusted_close: number | null;
  analysis_price: number | null;
  volume: number | null;
};

export type PricesResponse = {
  ticker: string;
  prices: PricePoint[];
};

export type InsiderTransaction = {
  transaction_id: string;
  accession_number: string;
  source_type: "bulk" | "edgar";
  document_type: string | null;
  insider_name: string | null;
  insider_role: string | null;
  transaction_date: string;
  filing_date: string;
  accepted_at: string | null;
  public_event_day: string | null;
  transaction_code: string;
  acquired_or_disposed: string;
  derivative_flag: boolean;
  security_title: string | null;
  shares: number | null;
  price: number | null;
  transaction_value: number | null;
  shares_owned_after: number | null;
  direct_or_indirect: string | null;
  aff10b5one: boolean | null;
  is_amendment: boolean;
  is_p0_qualifying: boolean;
};

export type ResearchEventSummary = {
  research_event_id: string;
  public_event_day: string;
  information_date: string;
  source_transaction_count: number;
  source_filing_count: number;
  aggregate_purchase_value: number | null;
  unique_buyer_count: number | null;
  role_bucket: "Executive" | "Director" | "Other";
  has_executive: boolean;
  has_director: boolean;
  has_other: boolean;
  has_cfo: boolean | null;
  max_valid_ownership_change_pct: number | null;
  any_new_position_flag: boolean | null;
};

export type InsidersResponse = {
  ticker: string;
  transactions: InsiderTransaction[];
  research_events: ResearchEventSummary[];
};
