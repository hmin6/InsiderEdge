import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { act, create, type ReactTestRenderer } from 'react-test-renderer';
import { AIResearchAssistant } from './AIResearchAssistant';
import { combineResearch, researchScript, type ResearchAudioRequest } from '../api/researchDocument';

const fixture = JSON.parse(readFileSync(new URL('../../../backend/tests/fixtures/ai/research_document.json', import.meta.url), 'utf8'));
type Call = { url: string; init?: RequestInit };
const endpoint = (url: string) => url.split('/').pop()!;
function response(url: string, init?: RequestInit) {
  if (endpoint(url) === 'snowflake-research') return Response.json({ ticker: 'AAPL', provider: 'snowflake',
    status: 'available', research_event_id: 'AAPL:2026-10-02', limitations: [], context: fixture.snowflake_context });
  if (endpoint(url) === 'explain') return Response.json(fixture.gemini_explanation);
  const request = JSON.parse(String(init?.body)) as ResearchAudioRequest;
  return Response.json({ ticker: 'AAPL', transcript: researchScript('AAPL', request.document),
    status: 'ok', audio_base64: 'AA==', audio_mime_type: 'audio/mpeg' });
}
async function harness(run: (view: ReactTestRenderer, calls: Call[], revoked: string[]) => Promise<void>, fetcher?: typeof fetch) {
  const original = { fetch: globalThis.fetch, window: globalThis.window, create: URL.createObjectURL, revoke: URL.revokeObjectURL };
  const calls: Call[] = [], revoked: string[] = [];
  let view: ReactTestRenderer | undefined;
  globalThis.window = { setTimeout, clearTimeout } as unknown as Window & typeof globalThis;
  URL.createObjectURL = () => 'blob:research';
  URL.revokeObjectURL = url => { revoked.push(url); };
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return fetcher ? fetcher(url, init) : response(String(url), init);
  };
  try {
    act(() => { view = create(<AIResearchAssistant ticker="AAPL" evidenceKey="2026-10-02" />); });
    await run(view!, calls, revoked);
  } finally {
    if (view) act(() => view!.unmount());
    globalThis.fetch = original.fetch; globalThis.window = original.window;
    URL.createObjectURL = original.create; URL.revokeObjectURL = original.revoke;
  }
}
const content = (view: ReactTestRenderer) => JSON.stringify(view.toJSON());
function button(view: ReactTestRenderer, label: string) {
  return view.root.findAllByType('button').find(node => node.children.join('') === label)!;
}
async function click(view: ReactTestRenderer, label: string) {
  assert.ok(button(view, label), label);
  await act(async () => { button(view, label).props.onClick(); await new Promise(resolve => setTimeout(resolve, 0)); });
}
const summaries = (view: ReactTestRenderer) => view.root.findAllByType('h2').filter(node => node.children.join('') === 'Research Summary');


test('one assistant action, no tabs, no independent analyst brief, and no automatic requests', async () => {
  await harness(async (view, calls) => {
    assert.ok(button(view, 'Generate AI Research'));
    assert.equal(view.root.findAllByProps({ role: 'tab' }).length, 0);
    assert.equal(view.root.findAllByProps({ role: 'tabpanel' }).length, 0);
    assert.equal(button(view, 'Listen to Research'), undefined);
    assert.ok(content(view).includes('AI tools interpret existing evidence.'));
    assert.ok(!content(view).includes('Listen to Brief'));
    assert.ok(!content(view).includes('Explain Signal'));
    assert.equal(calls.length, 0);
  });
});

test('both requests are concurrently in flight; duplicate clicks/rendering never duplicate calls', async () => {
  const resolve: Record<string, (value: Response) => void> = {};
  await harness(async (view, calls) => {
    const generate = button(view, 'Generate AI Research');
    act(() => { generate.props.onClick(); generate.props.onClick(); });
    assert.deepEqual(calls.map(call => endpoint(call.url)), ['snowflake-research', 'explain']);
    assert.ok(button(view, 'Generating AI Research...').props.disabled);
    assert.ok(content(view).includes('Generating...'));
    await act(async () => { resolve.explain(response('/explain')); });
    assert.ok(content(view).includes('Ready'));
    assert.equal(summaries(view).length, 0);
    await act(async () => { resolve['snowflake-research'](response('/snowflake-research')); });
    assert.equal(summaries(view).length, 1);
    act(() => view.update(<AIResearchAssistant ticker="AAPL" evidenceKey="2026-10-02" />));
    assert.equal(calls.length, 2);
  }, url => new Promise<Response>(done => { resolve[endpoint(String(url))] = done; }));
});

test('both providers produce one deterministic, attributed document without rewriting', async () => {
  assert.deepEqual(combineResearch(fixture.snowflake_context, fixture.gemini_explanation), fixture.document);
  assert.equal(researchScript('AAPL', fixture.document), fixture.script);
  await harness(async (view, calls) => {
    await click(view, 'Generate AI Research');
    assert.equal(summaries(view).length, 1);
    const text = content(view);
    for (const section of fixture.document.sections) {
      assert.ok(text.includes(section.title));
      for (const item of section.items) assert.ok(text.includes(item));
    }
    fixture.document.sources.forEach((source: string) => assert.ok(text.includes(source)));
    assert.equal(text.split(fixture.document.disclaimer).length - 1, 1);
    assert.ok(button(view, 'Listen to Research'));
    assert.ok(text.includes('Voice powered by ElevenLabs'));
    assert.equal(calls.length, 2);
  });
});

for (const failed of ['snowflake-research', 'explain', 'both']) {
  test(`${failed} failure: partial research is honest; both failures fabricate no document`, async () => {
    await harness(async (view, calls) => {
      await click(view, 'Generate AI Research');
      if (failed === 'both') {
        assert.equal(summaries(view).length, 0);
        assert.ok(content(view).includes('AI research unavailable'));
        assert.equal(button(view, 'Listen to Research'), undefined);
      } else {
        assert.equal(summaries(view).length, 1);
        assert.ok(content(view).includes(failed === 'explain' ? 'Quantitative AI interpretation was unavailable.' : 'Qualitative research context was unavailable.'));
        const headings = view.root.findAllByType('h3').map(node => node.children.join(''));
        assert.equal(headings.includes('Signal Interpretation'), failed !== 'explain');
        assert.equal(headings.includes('Event & Filing Context'), failed !== 'snowflake-research');
        await click(view, 'Listen to Research');
        const body = JSON.parse(String(calls[2].init?.body));
        assert.equal(Boolean(body.snowflake_context), failed !== 'snowflake-research');
        assert.equal(Boolean(body.gemini_explanation), failed !== 'explain');
      }
      assert.ok(!content(view).includes('private provider failure'));
    }, async (url, init) => failed === 'both' || endpoint(String(url)) === failed
      ? new Response('private provider failure', { status: 503 }) : response(String(url), init));
  });
}

test('Listen to Research sends the displayed document and replays audio without analytical requests', async () => {
  await harness(async (view, calls) => {
    await click(view, 'Generate AI Research'); await click(view, 'Listen to Research');
    const sent = JSON.parse(String(calls[2].init?.body));
    assert.equal(endpoint(calls[2].url), 'research-audio');
    assert.deepEqual(sent.document, fixture.document);
    assert.deepEqual(sent.snowflake_context, fixture.snowflake_context);
    assert.deepEqual(sent.gemini_explanation, fixture.gemini_explanation);
    assert.equal(sent.research_event_id, 'AAPL:2026-10-02');
    assert.equal((calls[2].init?.headers as Record<string, string>)['Content-Type'], 'application/json');
    assert.equal(view.root.findByType('audio').props.src, 'blob:research');
    await click(view, 'Replay from start');
    assert.equal(calls.length, 3);
    assert.equal(summaries(view).length, 1);
  });
});

for (const failure of ['http', 'audio_unavailable', 'mismatched_transcript']) {
  test(`ElevenLabs ${failure} keeps the complete research document`, async () => {
    await harness(async (view, calls) => {
      await click(view, 'Generate AI Research'); await click(view, 'Listen to Research');
      assert.equal(summaries(view).length, 1);
      fixture.document.sections.forEach((section: { items: string[] }) => section.items.forEach(text => assert.ok(content(view).includes(text))));
      assert.equal(view.root.findAllByType('audio').length, 0);
      assert.ok(content(view).includes('unavailable'));
      assert.equal(calls.length, 3);
    }, async (url, init) => {
      if (endpoint(String(url)) !== 'research-audio') return response(String(url), init);
      if (failure === 'http') return new Response('', { status: 503 });
      return Response.json({ ticker: 'AAPL', transcript: failure === 'mismatched_transcript' ? 'a different document' : fixture.script,
        status: 'audio_unavailable', audio_base64: null, audio_mime_type: null });
    });
  });
}

test('explicit regeneration reruns BOTH providers and invalidates the old document/audio', async () => {
  await harness(async (view, calls, revoked) => {
    await click(view, 'Generate AI Research'); await click(view, 'Listen to Research');
    act(() => button(view, 'Generate AI Research').props.onClick());
    assert.equal(summaries(view).length, 0);
    assert.equal(view.root.findAllByType('audio').length, 0);
    assert.deepEqual(revoked, ['blob:research']);
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
    assert.equal(summaries(view).length, 1);
    assert.equal(button(view, 'Listen to Research').props.disabled, false);
    assert.equal(calls.filter(call => endpoint(call.url) === 'explain').length, 2);
    assert.equal(calls.filter(call => endpoint(call.url) === 'snowflake-research').length, 2);
    assert.equal(calls.filter(call => endpoint(call.url) === 'research-audio').length, 1);
  });
});

test('retry after failure explicitly regenerates both without automatic retries', async () => {
  let first = true;
  await harness(async (view, calls) => {
    await click(view, 'Generate AI Research');
    assert.ok(content(view).includes('Quantitative AI interpretation was unavailable.'));
    assert.equal(calls.length, 2);
    first = false;
    await click(view, 'Generate AI Research');
    assert.equal(calls.length, 4);
    assert.equal(summaries(view).length, 1);
    assert.ok(!content(view).includes('Quantitative AI interpretation was unavailable.'));
  }, async (url, init) => first && endpoint(String(url)) === 'explain'
    ? new Response('', { status: 503 }) : response(String(url), init));
});

for (const change of ['company', 'event']) {
  test(`${change} change clears document and audio, preserving event-keyed resets`, async () => {
    await harness(async (view, calls, revoked) => {
      await click(view, 'Generate AI Research'); await click(view, 'Listen to Research');
      act(() => view.update(<AIResearchAssistant ticker={change === 'company' ? 'BRK.B' : 'AAPL'}
        evidenceKey={change === 'event' ? '2026-10-05' : '2026-10-02'} />));
      assert.equal(summaries(view).length, 0);
      assert.equal(view.root.findAllByType('audio').length, 0);
      assert.deepEqual(revoked, ['blob:research']);
      assert.equal(calls.length, 3);
      assert.ok(button(view, 'Generate AI Research'));
    });
  });
}

test('changing event aborts both pending requests and ignores their late responses', async () => {
  const resolves: ((value: Response) => void)[] = [];
  await harness(async (view, calls) => {
    act(() => button(view, 'Generate AI Research').props.onClick());
    act(() => view.update(<AIResearchAssistant ticker="AAPL" evidenceKey="2026-10-05" />));
    calls.forEach(call => assert.ok(call.init?.signal?.aborted));
    await act(async () => { resolves[0](response('/snowflake-research')); resolves[1](response('/explain')); });
    assert.equal(summaries(view).length, 0);
    assert.equal(calls.length, 2);
  }, () => new Promise<Response>(resolve => resolves.push(resolve)));
});

test('only available source sections render and unsupported text is never synthesized by combination', () => {
  const explanation = { ...fixture.gemini_explanation, supportive_evidence: [], risk_evidence: [] };
  const document = combineResearch(null, explanation)!;
  assert.equal(document.sections.some(section => section.title === 'Supporting Evidence'), false);
  assert.equal(document.sections.some(section => section.title === 'Risks / Counter-Evidence'), false);
  assert.equal(combineResearch(null, null), null);
  assert.ok(document.sections.every(section => section.items.every(item => Object.values(explanation).flat().includes(item))));
});
