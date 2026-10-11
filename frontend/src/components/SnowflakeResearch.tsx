import { useEffect, useRef, useState } from 'react';

import { API_BASE_URL } from '../api/base';

import { Panel, StateMessage } from './ui';



import { requestSnowflake, type SnowflakeResult } from '../api/snowflake';
export { requestSnowflake } from '../api/snowflake';
export type { SnowflakeResult } from '../api/snowflake';

export function SnowflakeResearch({ ticker }: { ticker: string }) {

  const [state, setState] = useState<'idle' | 'pending' | 'done' | 'unavailable'>('idle');

  const [result, setResult] = useState<SnowflakeResult | null>(null);

  const request = useRef<AbortController | null>(null);

  useEffect(() => () => { request.current?.abort(); request.current = null; }, []);

  async function generate() {

    if (request.current || state !== 'idle') return;

    const controller = new AbortController(); request.current = controller;

    setState('pending');

    const timeout = window.setTimeout(() => controller.abort(), 65000);

    try {

      const data = await requestSnowflake(ticker, controller.signal, API_BASE_URL);

      if (request.current !== controller || controller.signal.aborted) return;

      setResult(data); setState(data.status === 'available' ? 'done' : 'unavailable');

    } catch { if (request.current === controller) setState('unavailable'); }

    finally { window.clearTimeout(timeout); if (request.current === controller) request.current = null; }

  }

  return <Panel title="Research Context" description="Powered by Snowflake Cortex - Qualitative context from persisted event and filing evidence.">

    <button className="ie-button" onClick={generate} disabled={state !== 'idle'}>{state === 'pending' ? 'Preparing research context...' : 'Generate research context'}</button>

    <div aria-live="polite">

      {state === 'unavailable' && <StateMessage title="Snowflake research context unavailable">Core evidence, Gemini and audio remain available. No automatic retry is performed.</StateMessage>}

      {state === 'done' && result?.context && <>

        <p className="ie-muted">Event: {result.research_event_id}</p>

        {(['event_context', 'research_considerations', 'filing_context'] as const).map(key => <section key={key}><h3>{key.replace(/_/g, ' ')}</h3><ul>{result.context![key].map((text, i) => <li key={i}>{text}</li>)}</ul></section>)}

      </>}

      <p className="ie-muted">Uses supplied company/event evidence only; no web browsing, document retrieval or RAG. Not investment advice.</p>

      {result?.limitations.map((text, i) => <p className="ie-muted" key={i}>{text}</p>)}

    </div>

  </Panel>;

}
