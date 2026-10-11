import type { QuantitativeCoverageData } from '../types/api';
import { formatCurrency, formatNumber } from '../utils/format';

/** Descriptive data never supplies a replacement IES or participates in ranking. */
export function QuantitativeCoverage({ data }: { data?: QuantitativeCoverageData | null }) {
  if (!data) return null;
  return <details aria-label="Quantitative coverage"><summary>Score methodology and evidence</summary>
    <strong>{data.status === 'provisional' ? 'Provisional Index' : data.status === 'descriptive_only' ? 'Available quantitative data' : 'Quantitative evidence unavailable'}</strong>
    {data.status === 'provisional' && data.partial_index !== null && <>
      <p><strong>{formatNumber(data.partial_index)} / 100</strong></p>
      <p>Component coverage: {formatNumber(data.coverage_weight * 100)}%. Available: {data.available_components.join(', ')}. Missing: {data.missing_components.join(', ')}.</p>
      <p className="ie-muted">Calculated using incomplete and/or imputed inputs. This estimate has not been independently validated and is less reliable than a complete InsiderEdge Score.</p>
      <p className="ie-muted">Not directly comparable with complete IES; not a calibrated prediction. Existing Signal-bound inputs have incomplete historical provenance. No components were imputed.</p>
    </>}
    {data.estimated_activity_index != null && <>
      <p>Estimated Activity Index: {formatNumber(data.estimated_activity_index)} / 100</p>
      <p>Method: 100 × (0.70 × min(1, log10(1 + purchase value in USD) / 8) + 0.30 × min(1, qualifying purchase count / 5)).</p>
      <p className="ie-muted">$100 million and five transactions are product-defined saturation anchors; 70%/30% are heuristic weights, not a validated historical distribution. Not a fitted ML probability, return forecast, or validated InsiderEdge Score. Not directly comparable to complete or provisional scores.</p>
    </>}
    <p>Sources: lineage-checked Form 4 NONDERIV_TRANS qualifying purchase records; component values, where available, come from existing Signals.</p>
    {data.purchase_count !== null && <p>Qualifying purchases: {data.purchase_count}</p>}
    {data.purchase_value !== null && <p>Qualifying purchase value: {formatCurrency(data.purchase_value)}</p>}
    <p className="ie-muted">Information boundary: {data.information_date}. Descriptive source data, not an InsiderEdge Score or ML prediction.</p>
    {data.partial_index === null && <p className="ie-muted">Provisional Index unavailable: insufficient valid component evidence.</p>}
    <details><summary>Evidence limitations</summary>
      <ul>{[...data.reasons, ...data.provenance_limitations].map(reason => <li key={reason}>{reason}</li>)}</ul>
    </details>
  </details>;
}
