import { useEffect, useState } from 'react';
export function useResource<T>(key: string, load: (signal: AbortSignal) => Promise<T>) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ key: string; data: T | null; loading: boolean; error: unknown }>({ key, data: null, loading: true, error: null });
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setState({ key, data: null, loading: true, error: null });
    const timeout = window.setTimeout(() => {
      controller.abort();
      if (active) setState({ key, data: null, loading: false, error: new Error('Request timed out') });
    }, 15000);
    load(controller.signal).then(data => {
      if (active && !controller.signal.aborted) setState({ key, data, loading: false, error: null });
    }).catch(error => {
      if (active) setState({ key, data: null, loading: false, error });
    }).finally(() => window.clearTimeout(timeout));
    return () => { active = false; controller.abort(); window.clearTimeout(timeout); };
  }, [key, attempt, load]);
  const visible = state.key === key ? state : { key, data: null, loading: true, error: null };
  return { ...visible, retry: () => setAttempt(value => value + 1) };
}
