import type { ScoreEvidence } from '../types/score';
import { ScoreStatusBadge } from './ui';

/** Missing Signals are distinct from evaluated failures. Legacy responses do not
 * establish persistence, so do not claim the scoring process ran without the field.
 */
export function SignalAvailability({ evidence, showBadge = true }: { evidence: ScoreEvidence; showBadge?: boolean }) {
  const status = evidence.availability_status;
  const descriptions = {
    not_scored: 'No score has been generated for this research event.',
    insufficient_data: 'The scoring process ran, but required information was unavailable.',
    partial: 'A valid score was calculated from an approved subset of components.',
    complete: 'All required components are available.',
  };
  return <div>
    {showBadge && <ScoreStatusBadge status={evidence.score_status} availability={status} />}
    {status && <p className="ie-muted">{descriptions[status]}</p>}
    {status !== 'not_scored' && !!evidence.unavailable_components?.length &&
      <p className="ie-muted">Unavailable components: {evidence.unavailable_components.join(', ')}</p>}
  </div>;
}
