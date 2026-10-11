import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { act, create, type ReactTestRenderer } from 'react-test-renderer';
import { AIResearchAssistant } from './AIResearchAssistant';

const labels = ['Research Context', 'Signal Explanation', 'Listen to Brief'];
const endpoints = ['snowflake-research', 'explain', 'brief'];
const generated = ['Persisted filing context.', 'Grounded signal explanation.', 'Deterministic analyst transcript.'];

function response(endpoint: string, ticker: string) {
  if (endpoint === endpoints[0]) return Response.json({ ticker, provider: 'snowflake', status: 'available',
    research_event_id: `${ticker}:2026-03-16`, limitations: [], context: {
      event_context: [generated[0]], research_considerations: ['Review uncertainty.'], filing_context: ['Public filing.'],
    } });
  if (endpoint === endpoints[1]) return Response.json({ ticker, why_flagged: [generated[1]],
    supportive_evidence: [], risk_evidence: [], uncertainty: ['Unknown outcomes.'], limitations: ['Research only.'] });
  return Response.json({ ticker, transcript: generated[2], status: 'ok', audio_base64: 'AA==', audio_mime_type: 'audio/mpeg' });
}

async function harness(run: (view: ReactTestRenderer, calls: string[], revoked: string[]) => Promise<void>,
  fetcher?: typeof fetch) {
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  const originalCreate = URL.createObjectURL;
  const originalRevoke = URL.revokeObjectURL;
  const calls: string[] = [], revoked: string[] = [];
  let view: ReactTestRenderer | undefined;
  globalThis.window = { setTimeout, clearTimeout } as unknown as Window & typeof globalThis;
  URL.createObjectURL = () => 'blob:mock-brief';
  URL.revokeObjectURL = value => { revoked.push(value); };
  globalThis.fetch = async (url, init) => {
    calls.push(String(url));
    if (fetcher) return fetcher(url, init);
    const parts = String(url).split('/');
    return response(parts[parts.length - 1], decodeURIComponent(parts[parts.length - 2]));
  };
  try {
    act(() => { view = create(<AIResearchAssistant ticker="AXP" evidenceKey="2026-03-16" />); });
    await run(view!, calls, revoked);
  } finally {
    if (view) act(() => view!.unmount());
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
    URL.createObjectURL = originalCreate;
    URL.revokeObjectURL = originalRevoke;
  }
}

function select(view: ReactTestRenderer, index: number) {
  act(() => view.root.findAllByProps({ role: 'tab' })[index].props.onClick());
}
function assertActive(view: ReactTestRenderer, index: number) {
  const tabs = view.root.findAllByProps({ role: 'tab' });
  const panels = view.root.findAllByProps({ role: 'tabpanel' });
  assert.equal(panels.length, 3); // Every provider stays mounted.
  panels.forEach((panel, i) => {
    assert.equal(panel.props.hidden, i !== index);
    assert.equal(tabs[i].props['aria-selected'], i === index);
    assert.equal(tabs[i].props.tabIndex, i === index ? 0 : -1);
    assert.equal(tabs[i].props['aria-controls'], panel.props.id);
    assert.equal(panel.props['aria-labelledby'], tabs[i].props.id);
  });
}
async function generate(view: ReactTestRenderer, index: number) {
  select(view, index);
  const panel = view.root.findAllByProps({ role: 'tabpanel' })[index];
  const button = panel.findAllByType('button').find(node => node.props.onClick);
  assert.ok(button);
  await act(async () => { await button.props.onClick(); });
}

test('three attributed tabs share one disclaimer and only context starts visible', async () => {
  await harness(async (view, calls) => {
    const text = JSON.stringify(view.toJSON());
    labels.forEach(label => assert.ok(text.includes(label)));
    ['Snowflake Cortex', 'Gemini', 'ElevenLabs'].forEach(provider => assert.ok(text.includes(`Powered by ${provider}`)));
    assert.equal(text.split('They do not calculate or modify InsiderEdge scores or predictions.').length - 1, 1);
    assertActive(view, 0);
    assert.equal(calls.length, 0);
  });
});

test('switching tabs preserves all generated output, mounted instances and audio without requests', async () => {
  await harness(async (view, calls, revoked) => {
    for (let i = 0; i < 3; i++) { select(view, i); assertActive(view, i); }
    assert.equal(calls.length, 0);
    for (let i = 0; i < 3; i++) await generate(view, i);
    assert.equal(calls.length, 3);
    const audio = view.root.findByType('audio');
    for (const index of [0, 2, 1, 0, 2]) {
      select(view, index);
      assertActive(view, index);
      generated.forEach(text => assert.ok(JSON.stringify(view.toJSON()).includes(text)));
      assert.equal(view.root.findByType('audio'), audio);
      assert.equal(audio.props.src, 'blob:mock-brief');
    }
    assert.equal(revoked.length, 0);
    assert.equal(calls.length, 3);
  });
});

for (const change of ['event', 'company']) {
  test(`${change} change resets generated content, tab selection and audio state`, async () => {
    await harness(async (view, calls, revoked) => {
      for (let i = 0; i < 3; i++) await generate(view, i);
      act(() => view.update(<AIResearchAssistant ticker={change === 'company' ? 'BRK.B' : 'AXP'}
        evidenceKey={change === 'event' ? '2026-03-17' : '2026-03-16'} />));
      assertActive(view, 0);
      generated.forEach(text => assert.ok(!JSON.stringify(view.toJSON()).includes(text)));
      assert.equal(view.root.findAllByType('audio').length, 0);
      assert.deepEqual(revoked, ['blob:mock-brief']);
      assert.equal(calls.length, 3);
    });
  });
}

for (let failed = 0; failed < 3; failed++) {
  test(`${labels[failed]} failure stays isolated to its tab`, async () => {
    await harness(async (view, calls) => {
      for (let i = 0; i < 3; i++) await generate(view, i);
      for (let i = 0; i < 3; i++) {
        select(view, i);
        assertActive(view, i);
        const panel = view.root.findAllByProps({ role: 'tabpanel' })[i];
        if (i !== failed) assert.ok(JSON.stringify(view.toJSON()).includes(generated[i]));
        else {
          const titles = panel.findAllByType('h3').map(node => node.children.join(' '));
          assert.ok(titles.includes(['Snowflake research context unavailable',
            'AI explanation unavailable', 'Analyst brief unavailable'][failed]));
        }
      }
      assert.ok(JSON.stringify(view.toJSON()).includes('unavailable'));
      assert.ok(!JSON.stringify(view.toJSON()).includes('private provider detail'));
      assert.equal(calls.length, 3);
    }, async url => {
      const parts = String(url).split('/');
      return parts[parts.length - 1] === endpoints[failed]
        ? new Response('private provider detail', { status: 503 })
        : response(parts[parts.length - 1], 'AXP');
    });
  });
}

test('a pending request survives tab switching and completes in its original panel', async () => {
  let resolve!: (value: Response) => void;
  await harness(async (view, calls) => {
    const button = view.root.findAllByProps({ role: 'tabpanel' })[0].findByType('button');
    let pending!: Promise<void>;
    act(() => { pending = button.props.onClick(); });
    assert.ok(JSON.stringify(view.toJSON()).includes('Preparing research context'));
    select(view, 1);
    assertActive(view, 1);
    assert.equal(calls.length, 1);
    await act(async () => { resolve(response('snowflake-research', 'AXP')); await pending; });
    select(view, 0);
    assert.ok(JSON.stringify(view.toJSON()).includes(generated[0]));
    assert.equal(calls.length, 1);
  }, () => new Promise<Response>(done => { resolve = done; }));
});

test('keyboard navigation supports arrows, wrapping, Home and End without fetching', async () => {
  await harness(async (view, calls) => {
    let prevented = 0, focused = -1;
    for (const [from, key, expected] of [[0, 'ArrowLeft', 2], [2, 'ArrowRight', 0], [0, 'End', 2], [2, 'Home', 0]] as const) {
      act(() => view.root.findAllByProps({ role: 'tab' })[from].props.onKeyDown({ key,
        preventDefault: () => { prevented++; }, currentTarget: { parentElement: {
          querySelectorAll: () => [0, 1, 2].map(i => ({ focus: () => { focused = i; } })),
        } },
      }));
      assertActive(view, expected);
      assert.equal(focused, expected);
    }
    assert.equal(prevented, 4);
    assert.equal(calls.length, 0);
  });
});

test('responsive tabs wrap with touch-sized controls and hidden panels cannot display', () => {
  const css = readFileSync(new URL('../styles/index.css', import.meta.url), 'utf8');
  assert.match(css, /\.ie-research-assistant-tabs\s*\{[^}]*flex-wrap: wrap/s);
  assert.match(css, /\.ie-research-assistant-tabs \[role="tab"\]\s*\{[^}]*min-height: 44px/s);
  assert.match(css, /\.ie-research-assistant-panel\[hidden\]\s*\{[^}]*display: none/s);
});
