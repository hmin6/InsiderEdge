import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { BriefTranscript } from './AnalystBrief';
import { briefAudioBlob, requestBrief, validateBrief } from '../api/brief';
import type { BriefResponse } from '../types/brief';

const brief: BriefResponse = { ticker: 'AAPL', transcript: 'Research transcript', audio_base64: null, audio_mime_type: null, status: 'audio_unavailable' };
test('brief generation POST goes to backend with encoded ticker and cancellation', async () => {
  const signal = new AbortController().signal;
  const fetcher: typeof fetch = async (url, init) => {
    assert.equal(url, 'http://backend/api/companies/BRK%2FB/brief');
    assert.equal(init?.method, 'POST');
    assert.equal(init?.signal, signal);
    return Response.json({ ...brief, ticker: 'BRK/B' });
  };
  assert.equal((await requestBrief('BRK/B', signal, 'http://backend/', fetcher)).transcript, brief.transcript);
});
test('failed generation does not expose provider error details', async () => {
  const fetcher: typeof fetch = async () => new Response('private error', { status: 503 });
  await assert.rejects(requestBrief('AAPL', new AbortController().signal, '', fetcher), /Analyst brief unavailable/);
});
test('validates response structure and company identity', () => {
  assert.equal(validateBrief(brief, 'AAPL').status, 'audio_unavailable');
  assert.throws(() => validateBrief(brief, 'MSFT'));
  assert.throws(() => validateBrief({ ...brief, transcript: null }, 'AAPL'));
});
test('decodes base64 audio and handles unavailable or invalid audio independently', async () => {
  assert.equal(briefAudioBlob(brief), null);
  const audioBrief = { ...brief, status: 'ok' as const, audio_base64: btoa('audio bytes'), audio_mime_type: 'audio/mpeg' };
  const blob = briefAudioBlob(audioBrief)!;
  assert.equal(blob.type, 'audio/mpeg');
  assert.equal(await blob.text(), 'audio bytes');
  assert.throws(() => briefAudioBlob({ ...audioBrief, audio_base64: '%' }));
  assert.throws(() => briefAudioBlob({ ...audioBrief, audio_mime_type: 'text/html' }));
});
test('transcript is escaped text and handles missing content', () => {
  assert.match(renderToStaticMarkup(<BriefTranscript transcript="<script>text</script>" />), /&lt;script&gt;/);
  assert.match(renderToStaticMarkup(<BriefTranscript transcript="" />), /No transcript provided/);
});
