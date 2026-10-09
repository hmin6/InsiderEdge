import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { AppShell, Panel, PanelSkeleton, RoleBadge, ScoreStatusBadge, StateMessage } from './ui';

test('role badges preserve all supplied categories without investment semantics', () => {
  for (const role of ['Executive', 'Director', 'Other'] as const) {
    const html = renderToStaticMarkup(<RoleBadge role={role} />);
    assert.ok(html.includes(`>${role}</span>`));
    assert.match(html, /ie-badge--neutral/);
  }
});

test('shell connects skip link to main and identifies the current navigation item', () => {
  const html = renderToStaticMarkup(<AppShell navigation={[{ label: 'Radar', href: '/', current: true }]}><p>Workspace</p></AppShell>);
  const target = html.match(/href="#([^"]+)"/)?.[1];
  assert.ok(target);
  assert.ok(html.includes(`id="${target}" tabindex="-1"`));
  assert.match(html, /aria-current="page"/);
});
test('panels expose distinct accessible headings', () => {
  const html = renderToStaticMarkup(<><Panel title="Statistics">Evidence</Panel><Panel title="Prediction">Model</Panel></>);
  const ids = Array.from(html.matchAll(/aria-labelledby="([^"]+)"/g), match => match[1]);
  assert.equal(new Set(ids).size, 2);
  for (const id of ids) assert.ok(html.includes(`id="${id}"`));
});
test('all score availability states render explicit text without recommendation language', () => {
  for (const [status, label] of Object.entries({ complete: 'Complete evidence', partial: 'Partial evidence', insufficient_data: 'Insufficient data' })) {
    const html = renderToStaticMarkup(<ScoreStatusBadge status={status as 'complete' | 'partial' | 'insufficient_data'} />);
    assert.ok(html.includes(label));
    assert.doesNotMatch(html, /Buy|Sell|recommendation/);
  }
});
test('loading has an accessible status while decorative placeholders stay hidden', () => {
  const html = renderToStaticMarkup(<PanelSkeleton label="Loading statistics" rows={3} />);
  assert.match(html, /role="status" aria-label="Loading statistics"/);
  assert.equal((html.match(/aria-hidden="true"/g) ?? []).length, 4);
});
test('errors expose an alert and preserve recovery controls', () => {
  const html = renderToStaticMarkup(<StateMessage kind="error" title="Unable to load" actions={<button>Retry</button>}>Try again.</StateMessage>);
  assert.match(html, /role="alert"/);
  assert.match(html, /<button>Retry<\/button>/);
});
