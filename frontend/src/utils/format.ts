/** Presentation only: never use formatted strings for calculations or ordering.
 * Fixed en-US grouping keeps tables, charts and accessible text consistent.
 */
type Measurement = number | null | undefined;
const missing = 'Unavailable';
const finite = (value: Measurement): value is number => typeof value === 'number' && Number.isFinite(value);
const decimal = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const currency = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 });
const integer = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
// Normalize negative values that round to zero, including IEEE negative zero.
const cleanZero = (value: number) => Number(value.toFixed(2)) === 0 ? 0 : value;

export function formatNumber(value: Measurement): string {
  return finite(value) ? decimal.format(cleanZero(value)) : missing;
}
/** Already-scaled percentage points, e.g. 78.35 -> 78.35%. */
export function formatPercent(value: Measurement): string {
  return finite(value) ? `${formatNumber(value)}%` : missing;
}
/** Decimal probability/return, e.g. .7835 -> 78.35%. Scale exactly once. */
export function formatFractionPercent(value: Measurement): string {
  return finite(value) ? formatPercent(value * 100) : missing;
}
export function formatCurrency(value: Measurement): string {
  return finite(value) ? currency.format(cleanZero(value)) : missing;
}
export function formatCount(value: Measurement): string {
  return finite(value) ? integer.format(Object.is(value, -0) ? 0 : value) : missing;
}
/** Keep positive p-values below .01 visible instead of rounding to zero. */
export function formatPValue(value: Measurement): string {
  if (!finite(value)) return missing;
  return value > 0 && value < .01 ? value.toExponential(2) : formatNumber(value);
}
