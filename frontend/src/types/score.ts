import type { AvailabilityStatus } from './api';
/** Backend-provided values; the visualization never constructs a composite score. */
export type ScoreEvidence = {
  insider_edge_score: number | null;
  anomaly_score: number | null;
  activity_score: number | null;
  statistical_score: number | null;
  ml_outperformance_probability: number | null;
  dislocation_score: number | null;
  availability_status?: AvailabilityStatus | null;
  unavailable_components?: string[];
  score_status: 'complete' | 'partial' | 'insufficient_data';
};
