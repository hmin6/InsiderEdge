import { useCallback, useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '../api/base';
import { requestSnowflake } from '../api/snowflake';
import { mockExplanation, requestExplanation } from '../api/explain';

export type ResearchController<T> = {
  state: 'idle' | 'pending' | 'success' | 'error';
  result: T | null;
  generate: () => Promise<void>;
};

function useResearchRequest<T>(load: (signal: AbortSignal) => Promise<T>, timeoutMs: number): ResearchController<T> {
  const [state, setState] = useState<ResearchController<T>['state']>('idle');
  const [result, setResult] = useState<T | null>(null);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => { const request = active.current; active.current = null; request?.abort(); }, []);
  const generate = useCallback(async () => {
    if (active.current) return;
    const controller = new AbortController();
    active.current = controller;
    setResult(null);
    setState('pending');
    const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const data = await load(controller.signal);
      if (active.current !== controller) return;
      if (controller.signal.aborted) throw new Error('Research timed out');
      setResult(data);
      setState('success');
    } catch {
      if (active.current === controller) setState('error');
    } finally {
      window.clearTimeout(timeout);
      if (active.current === controller) active.current = null;
    }
  }, [load, timeoutMs]);
  return { state, result, generate };
}

export function useSnowflakeResearch(ticker: string, expectedEvent?: string) {
  const load = useCallback(async (signal: AbortSignal) => {
    const result = await requestSnowflake(ticker, signal, API_BASE_URL);
    if (result.status !== 'available' || (expectedEvent && result.research_event_id !== expectedEvent)) {
      throw new Error('Research unavailable for this event');
    }
    return result;
  }, [ticker, expectedEvent]);
  return useResearchRequest(load, 65000);
}

export function useGeminiResearch(ticker: string) {
  const load = useCallback((signal: AbortSignal) => {
    const mock = geminiMockEnabled();
    return mock ? Promise.resolve(mockExplanation(ticker)) : requestExplanation(ticker, signal, API_BASE_URL);
  }, [ticker]);
  return useResearchRequest(load, 20000);
}

export function geminiMockEnabled() {
  return import.meta.env?.DEV && import.meta.env.VITE_EXPLAIN_MOCK !== 'false';
}
