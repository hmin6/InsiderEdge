import type { RadarItem } from '../types/api';
import { numeric } from './ResearchStates';

/** No Signal means unevaluated components, not five independently failed models. */
export function RadarComponentValues({ item }: { item: RadarItem }) {
  if (item.availability_status === 'not_scored') return <td colSpan={5} className="ie-muted">Model components not evaluated</td>;
  return <>
    <td className="ie-number">{numeric(item.anomaly_score)}</td>
    <td className="ie-number">{numeric(item.activity_score)}</td>
    <td className="ie-number">{numeric(item.statistical_score)}</td>
    <td className="ie-number">{numeric(item.dislocation_score)}</td>
    <td className="ie-number">{numeric(item.ml_outperformance_probability, true)}</td>
  </>;
}
