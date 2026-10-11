import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { renderToStaticMarkup } from 'react-dom/server';
import { PriceChart, PriceHoverMarker, uniqueChartDates } from './PriceChart';
import type { PricePoint, InsiderTransaction } from '../types/api';

const prices: PricePoint[] = [{ date: '2026-10-01', analysis_price: 100,
  open: null, high: null, low: null, close: 102, adjusted_close: null, volume: null }];

test('chart legend describes analysis prices and qualifying filing dates, not research events', () => {
  const html = renderToStaticMarkup(<PriceChart prices={prices} transactions={[]} />);
  assert.match(html, /aria-label="Price chart legend"/);
  for (const label of ['Adjustment-aware price', 'Qualifying purchase filing', 'Active price point']) {
    assert.ok(html.includes(label));
  }
  assert.doesNotMatch(html, /Research event|Transaction date|Buy signal/);
  assert.match(html, /flex-wrap:wrap/);
  assert.match(html, /fill="var\(--ie-primary\)"/); // Filled blue event swatch.
  assert.match(html, /stroke="#fbbf24"/); // Amber active-point swatch.
});

test('active marker is an amber outlined ring and cannot intercept chart interaction', () => {
  const html = renderToStaticMarkup(<svg><PriceHoverMarker cx={42} cy={99} /></svg>);
  assert.match(html, /cx="42" cy="99"/);
  assert.match(html, /fill="none"/);
  assert.match(html, /stroke="#fbbf24"/);
  assert.match(html, /stroke-width="2"/);
  assert.match(html, /pointer-events="none"/);
  assert.match(html, /aria-hidden="true"/);
  assert.doesNotMatch(html, /var\(--ie-primary\)/);
});

test('empty history retains the existing empty state without an irrelevant legend', () => {
  const html = renderToStaticMarkup(<PriceChart prices={[]} transactions={[]} />);
  assert.match(html, /No price history available/);
  assert.doesNotMatch(html, /Price chart legend/);
});

// ResponsiveContainer does not render chart geometry during SSR. Check the actual
// ReferenceDot configuration and coincident SVG geometry, not a simulated hover.
test('qualifying filing at the active price remains inside a transparent, non-overlapping ring', () => {
  const purchase: InsiderTransaction = {
    transaction_id: 'purchase-1', accession_number: 'synthetic-1', source_type: 'edgar',
    document_type: '4', insider_name: null, insider_role: null,
    transaction_date: '2026-09-30', filing_date: prices[0].date,
    accepted_at: null, public_event_day: null, transaction_code: 'P',
    acquired_or_disposed: 'A', derivative_flag: false, security_title: null,
    shares: 10, price: 100, transaction_value: 1000, shares_owned_after: null,
    direct_or_indirect: null, aff10b5one: null, is_amendment: false, is_p0_qualifying: true,
  };
  const chart = renderToStaticMarkup(<PriceChart prices={prices} transactions={[purchase]} />);
  assert.match(chart, /Qualifying purchase filing/);
  assert.equal(purchase.filing_date, prices[0].date);

  const source = readFileSync(new URL('./PriceChart.tsx', import.meta.url), 'utf8');
  const eventDot = source.match(/<ReferenceDot\b[\s\S]*?\/>/)?.[0];
  assert.ok(eventDot, 'inspect the permanent chart marker, not its legend swatch');
  assert.match(eventDot, /fill="var\(--ie-primary\)"/);
  const eventRadius = Number(eventDot.match(/r=\{([\d.]+)\}/)?.[1]);
  const eventStroke = Number(eventDot.match(/strokeWidth=\{([\d.]+)\}/)?.[1]);
  assert.ok(Number.isFinite(eventRadius) && Number.isFinite(eventStroke));

  const ring = renderToStaticMarkup(<svg><PriceHoverMarker cx={42} cy={99} /></svg>);
  assert.match(ring, /cx="42" cy="99"/);
  assert.match(ring, /fill="none"/);
  assert.match(ring, /stroke="#fbbf24"/);
  const ringRadius = Number(ring.match(/r="([\d.]+)"/)?.[1]);
  const ringStroke = Number(ring.match(/stroke-width="([\d.]+)"/)?.[1]);
  assert.ok(ringRadius > eventRadius);
  assert.ok(ringRadius - ringStroke / 2 > eventRadius + eventStroke / 2,
    'even the inner amber stroke must clear the outer event stroke at identical coordinates');
});

test('custom inspection uses the transparent marker while retaining keyboard, zoom and saved guides', () => {
  const source = readFileSync(new URL('./PriceChart.tsx', import.meta.url), 'utf8');
  assert.match(source, /active && Number.isFinite\(y\) && <PriceHoverMarker cx=\{x\} cy=\{y\}/);
  assert.match(source, /strokeDasharray=\{active \? '4 4' : '5 3'\}/);
  assert.match(source, /activeDot=\{false\}/);
  assert.match(source, /ArrowLeft.*ArrowRight/);
  assert.match(source, /area.addEventListener\("wheel", wheel, \{ passive: false \}\)/);
  assert.match(source, /isAnimationActive=\{!reducedMotion\}/);
});

test('chart dates are unique without mutating source prices or changing their order', () => {
  const first = prices[0];
  const duplicate = { ...first, analysis_price: 200 };
  const next = { ...first, date: '2026-10-02' };
  const source = [first, duplicate, next];
  assert.deepEqual(uniqueChartDates(source), [first, next]);
  assert.deepEqual(source, [first, duplicate, next]);
  assert.deepEqual(uniqueChartDates([]), []);
});
