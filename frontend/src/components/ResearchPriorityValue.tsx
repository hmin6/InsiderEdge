import type { QuantitativeCoverageData } from '../types/api';
import { formatNumber } from '../utils/format';

/** Presentation precedence only; these values never participate in mixed ranking. */
export function ResearchPriorityValue({ score, status, coverage }: {
  score: number | null; status: string; coverage?: QuantitativeCoverageData | null;
}) {
  const selected = selectResearchPriority(score, status, coverage);
  if (!selected) return <span aria-label="No supported research priority value">—</span>;
  return <span title={selected.label === 'Complete' ? 'Canonical InsiderEdge Score' : 'Incomplete evidence; not directly comparable to complete IES'}>
    <strong>{formatNumber(selected.value)}</strong><br /><small className="ie-muted">{selected.label}</small>
  </span>;
}

export function selectResearchPriority(score: number | null, status: string, coverage?: QuantitativeCoverageData | null) {
  const valid = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= 100;
  return status === 'complete' && valid(score) ? { value: score, label: 'Complete' }
    : coverage?.status === 'provisional' && valid(coverage.partial_index) ? { value: coverage.partial_index, label: 'Provisional' }
    : valid(coverage?.estimated_activity_index) ? { value: coverage.estimated_activity_index, label: 'Estimated Activity' } : null;
}
