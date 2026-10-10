import { formatNumber } from '../utils/format';
import type { ScoreEvidence } from '../types/score';
import { useScoreReveal } from '../hooks/useScoreReveal';
import { Panel, ScoreStatusBadge } from './ui';

function valid(value: number | null, maximum = 100): number | null {
  return value !== null && Number.isFinite(value) && value >= 0 && value <= maximum ? value : null;
}

/** Pass a RadarItem/latest_signal directly. All final numbers remain backend values. */
export function InsiderEdgeScore({ evidence }: { evidence: ScoreEvidence }) {
  const { ref, progress } = useScoreReveal();
  const score = valid(evidence.insider_edge_score);
  const probability = valid(evidence.ml_outperformance_probability, 1);
  // Scaling probability to percent is unit formatting, not composite-score calculation.
  const components = [
    { key: 'A', label: 'Anomaly', value: valid(evidence.anomaly_score), unit: '/ 100' },
    { key: 'C', label: 'Activity', value: valid(evidence.activity_score), unit: '/ 100' },
    { key: 'M', label: 'Model', value: probability === null ? null : probability * 100, unit: '% probability' },
    { key: 'S', label: 'Statistical Evidence', value: valid(evidence.statistical_score), unit: '/ 100' },
    { key: 'D', label: 'Market Dislocation', value: valid(evidence.dislocation_score), unit: '/ 100' },
  ];
  return <Panel title="InsiderEdge Score" actions={<ScoreStatusBadge status={evidence.score_status} />}>
    <div ref={ref} className="ie-score">
      <div className="ie-score-headline">
        <div className="ie-score-dial">
          <svg viewBox="0 0 120 120" aria-hidden="true" focusable="false">
            <circle className="ie-score-track" cx="60" cy="60" r="52" />
            {score !== null && <circle className="ie-score-fill" cx="60" cy="60" r="52" pathLength="100" strokeDasharray="100" strokeDashoffset={100 - score * progress} />}
          </svg>
          <div className="ie-score-number">
            <span className="ie-sr-only">{score === null ? 'Score unavailable' : `${formatNumber(score)} out of 100`}</span>
            <strong aria-hidden="true">{score === null ? '—' : formatNumber(score * progress)}</strong>
            <span aria-hidden="true">{score === null ? 'Unavailable' : '/ 100'}</span>
          </div>
        </div>
        <p className="ie-score-priority">Research Priority</p>
        <p className="ie-muted">Higher scores prioritize deeper research.</p>
      </div>
      <dl className="ie-score-components">
        {components.map(component => <div className="ie-score-component" key={component.key}>
          <dt><span className="ie-score-letter">{component.key}</span>{component.label}</dt>
          <dd>{component.value === null ? <span className="ie-muted">Unavailable</span> : <><strong>{formatNumber(component.value)}</strong> <span className="ie-muted">{component.unit}</span></>}</dd>
          {component.value !== null && <div className="ie-score-bar" aria-hidden="true"><span style={{ transform: `scaleX(${component.value / 100 * progress})` }} /></div>}
        </div>)}
      </dl>
    </div>
    <div className="ie-score-note">
      {evidence.score_status === 'partial' && <p>Partial score · Some evidence is unavailable. The displayed score is supplied by the backend.</p>}
      {evidence.score_status === 'insufficient_data' && <p>Insufficient data · Evidence needed for the overall research-priority score is unavailable.</p>}
      <p>Research priority is not a trading recommendation or a guarantee of future performance. Component bars show levels, not weighted contributions.</p>
    </div>
  </Panel>;
}
