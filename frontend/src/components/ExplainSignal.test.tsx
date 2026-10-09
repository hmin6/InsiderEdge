import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { ExplanationSections } from './ExplainSignal';
import { mockExplanation, requestExplanation, validateExplanation } from '../api/explain';

test('POST uses only backend endpoint and passes abort signal', async () => {
  const controller = new AbortController();
  const fetcher: typeof fetch = async (url, init) => {
    assert.equal(url, 'http://backend/api/companies/BRK%2FB/explain');
    assert.equal(init?.method, 'POST');
    assert.equal(init?.signal, controller.signal);
    return Response.json(mockExplanation('BRK/B'));
  };
  assert.equal((await requestExplanation('BRK/B', controller.signal, 'http://backend/', fetcher)).ticker, 'BRK/B');
});
test('provider errors remain controlled without exposing response details', async () => {
  const fetcher: typeof fetch = async () => new Response('private provider error', { status: 503 });
  await assert.rejects(requestExplanation('AAPL', new AbortController().signal, '', fetcher), /Explanation unavailable/);
});
test('invalid structures and mismatched company responses are rejected', () => {
  assert.throws(() => validateExplanation({ ...mockExplanation('AAPL'), uncertainty: null }, 'AAPL'));
  assert.throws(() => validateExplanation(mockExplanation('MSFT'), 'AAPL'));
});
test('structured sections escape text and withhold trade instructions', () => {
  const html = renderToStaticMarkup(<ExplanationSections explanation={{ ...mockExplanation('AAPL'), supportive_evidence: ['<script>example</script>', 'Buy shares for your portfolio.'] }} />);
  for (const heading of ['Why flagged', 'Supportive evidence', 'Risks / counter-evidence', 'Uncertainty', 'Limitations']) assert.ok(html.includes(heading));
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /Buy shares/);
  assert.match(html, /was withheld/);
  assert.match(html, /Development example only/);
});
