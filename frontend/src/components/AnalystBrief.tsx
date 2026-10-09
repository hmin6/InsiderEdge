import { useEffect, useRef, useState } from 'react';
import { briefAudioBlob, requestBrief } from '../api/brief';
import type { BriefResponse } from '../types/brief';
import { Panel, PanelSkeleton, StateMessage, StatusBadge } from './ui';

export function BriefTranscript({ transcript }: { transcript: string }) {
  return <section><h3>Transcript</h3><p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', marginTop: 8 }}>{transcript || 'No transcript provided.'}</p></section>;
}

/** Remount for a different company/event to stop playback and discard stale content. */
export function AnalystBrief({ ticker, evidenceKey = ticker }: { ticker: string; evidenceKey?: string }) {
  return <BriefRequest key={`${ticker}:${evidenceKey}`} ticker={ticker} />;
}

function BriefRequest({ ticker }: { ticker: string }) {
  const [state, setState] = useState<'idle' | 'pending' | 'success' | 'error'>('idle');
  const [brief, setBrief] = useState<BriefResponse | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audioError, setAudioError] = useState(false);
  const [playError, setPlayError] = useState(false);
  const request = useRef<AbortController | null>(null);
  const audio = useRef<HTMLAudioElement>(null);
  useEffect(() => () => {
    const active = request.current;
    request.current = null;
    active?.abort();
  }, []);
  useEffect(() => {
    if (!brief) return;
    let url: string | null = null;
    try {
      const blob = briefAudioBlob(brief);
      if (blob) { url = URL.createObjectURL(blob); setAudioUrl(url); }
      else setAudioError(true);
    } catch { setAudioError(true); }
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [brief]);
  async function generate() {
    if (request.current || state === 'success') return;
    const controller = new AbortController();
    request.current = controller;
    setState('pending');
    const timeout = window.setTimeout(() => controller.abort(), 30000);
    try {
      const result = await requestBrief(ticker, controller.signal, import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000');
      if (request.current !== controller) return;
      if (controller.signal.aborted) throw new Error('Timed out');
      setBrief(result);
      setState('success');
    } catch {
      if (request.current === controller) setState('error');
    } finally {
      window.clearTimeout(timeout);
      if (request.current === controller) request.current = null;
    }
  }
  async function replay() {
    if (!audio.current) return;
    setPlayError(false);
    try {
      audio.current.currentTime = 0;
      await audio.current.play();
    } catch { setPlayError(true); }
  }
  return <Panel title="Analyst Brief · ElevenLabs" description="Optional audio interpretation of existing research evidence." actions={<StatusBadge>P1 · Optional</StatusBadge>}>
    <div className="ie-stack">
      <p className="ie-muted">Research context only. Generating audio does not change the signal, score, or model prediction.</p>
      <div><button className="ie-button" onClick={generate} disabled={state === 'pending' || state === 'success'}>{state === 'pending' ? 'Generating analyst brief…' : state === 'success' ? 'Brief generated' : state === 'error' ? 'Retry Generate Analyst Brief' : 'Generate Analyst Brief'}</button></div>
      {state === 'pending' && <PanelSkeleton label="Generating optional analyst brief" rows={3} />}
      {state === 'error' && <StateMessage kind="error" title="Analyst brief unavailable">Please retry. Gemini and quantitative results are unaffected.</StateMessage>}
      {brief && <div className="ie-stack ie-reveal">
        <p role="status" className="ie-sr-only">Analyst brief ready.</p>
        <BriefTranscript transcript={brief.transcript} />
        {audioUrl && !audioError && <>
          <audio className="ie-audio-player" ref={audio} controls preload="none" src={audioUrl} aria-label={`Analyst brief for ${ticker}`} onError={() => setAudioError(true)} style={{ maxWidth: '100%' }} />
          <div><button className="ie-button" onClick={replay}>Replay from start</button></div>
        </>}
        {audioError && <p role="status" className="ie-muted">Audio unavailable. The transcript remains available above.</p>}
        {playError && <p role="status" className="ie-muted">Playback could not start. Try the audio player’s Play control.</p>}
      </div>}
    </div>
  </Panel>;
}
