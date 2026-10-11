import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { SnowflakeResearch, requestSnowflake } from './SnowflakeResearch';
const unavailable = { ticker: 'AXP', provider: 'snowflake', status: 'unavailable', context: null, limitations: [] };
test('Snowflake is on demand and separate from scoring', () => {
  const html = renderToStaticMarkup(<SnowflakeResearch ticker="AXP" />);
  assert.match(html, /Research Context/);
  assert.match(html, /Powered by Snowflake Cortex/);
  assert.match(html, /Generate research context/);
});
test('request uses backend POST and accepts unavailable without crashing', async () => {
  const fetcher: typeof fetch = async (url, init) => {
    assert.equal(url, 'https://backend/api/companies/AXP/snowflake-research');
    assert.equal(init?.method, 'POST');
    return Response.json(unavailable);
  };
  assert.equal((await requestSnowflake('AXP', new AbortController().signal, 'https://backend/', fetcher)).status, 'unavailable');
});
test('malformed or wrong-company results are rejected', async () => {
  const fetcher: typeof fetch = async () => Response.json({ ...unavailable, ticker: 'MSFT' });
  await assert.rejects(requestSnowflake('AXP', new AbortController().signal, '', fetcher));
});
test('provider failure does not expose response details', async () => {
  const fetcher: typeof fetch = async () => new Response('private', { status: 503 });
  await assert.rejects(requestSnowflake('AXP', new AbortController().signal, '', fetcher), /Snowflake research context unavailable/);
});
