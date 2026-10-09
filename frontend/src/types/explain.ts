export type ExplainResponse = {
  ticker: string;
  why_flagged: string[];
  supportive_evidence: string[];
  risk_evidence: string[];
  uncertainty: string[];
  limitations: string[];
};
