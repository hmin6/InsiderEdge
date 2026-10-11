import { useEffect, useRef, useState } from 'react';
import { briefAudioBlob } from '../api/brief';
import { requestResearchAudio, researchScript, MAX_RESEARCH_AUDIO_CHARACTERS, type ResearchAudioRequest } from '../api/researchDocument';
import { API_BASE_URL } from '../api/base';
import type { BriefResponse } from '../types/brief';

const RESEARCH_AUDIO_TIMEOUT_MS = 60_000;

export function ResearchAudio({ ticker, research }: { ticker: string; research: ResearchAudioRequest }) {
  const oversized = researchScript(ticker, research.document).length > MAX_RESEARCH_AUDIO_CHARACTERS;
  const [state, setState] = useState<'idle' | 'pending' | 'success' | 'error'>('idle');
  const [brief, setBrief] = useState<BriefResponse | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audioError, setAudioError] = useState(false);
  const [playError, setPlayError] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
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
    if (request.current || state === 'success' || oversized) return;
    const controller = new AbortController();
    request.current = controller;
    setTimedOut(false);
    setState('pending');
    let deadlineReached = false;
    const timeout = window.setTimeout(() => {
      deadlineReached = true;
      controller.abort();
    }, RESEARCH_AUDIO_TIMEOUT_MS);
    try {
      const result = await requestResearchAudio(ticker, research, controller.signal, API_BASE_URL);
      if (request.current !== controller) return;
      if (controller.signal.aborted) throw new Error('Timed out');
      setBrief(result);
      setState('success');
    } catch {
      if (request.current === controller) {
        setTimedOut(deadlineReached);
        setState('error');
      }
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
  return <div className="ie-stack ie-research-audio">
    <div><button className="ie-button" onClick={generate} disabled={oversized || state === 'pending' || state === 'success'}>
      {state === 'pending' ? 'Preparing research audio...' : state === 'success' ? (brief?.status === 'ok' ? 'Research audio prepared' : 'Audio unavailable') : state === 'error' ? 'Retry Listen to Research' : 'Listen to Research'}
    </button></div>
    <p className="ie-muted">Voice powered by ElevenLabs</p>
    {oversized && <p role="status">This research exceeds the audio size limit. The complete text remains available above.</p>}
    {state === 'error' && <p role="alert">{timedOut
      ? 'Research audio timed out. The research document remains available. Try again.'
      : 'Research audio unavailable. The research document remains available. Verification may have expired; regenerate research before retrying.'}</p>}
    {audioUrl && !audioError && <>
      <audio className="ie-audio-player" ref={audio} controls preload="none" src={audioUrl}
        aria-label={`AI research for ${ticker}`} onError={() => setAudioError(true)} style={{ maxWidth: '100%' }} />
      <div><button className="ie-button" onClick={replay}>Replay from start</button></div>
    </>}
    {audioError && <p role="status" className="ie-muted">Audio unavailable. The research document remains available above.</p>}
    {playError && <p role="status" className="ie-muted">Playback could not start. Try the audio player's Play control.</p>}
  </div>;
}
