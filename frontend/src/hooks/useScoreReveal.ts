import { useEffect, useRef, useState } from 'react';

/** One 300ms reveal per mounted visualization. Static output is the fallback. */
export function useScoreReveal() {
  const ref = useRef<HTMLDivElement>(null);
  const [progress, setProgress] = useState(1);
  useEffect(() => {
    const element = ref.current;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (!element || preference.matches || !('IntersectionObserver' in window)) return;
    let frame = 0;
    let started = false;
    let cancelled = false;
    setProgress(0);
    const observer = new IntersectionObserver(entries => {
      if (!entries.some(entry => entry.isIntersecting) || started || cancelled) return;
      started = true;
      observer.disconnect();
      let start: number | undefined;
      const tick = (now: number) => {
        if (cancelled) return;
        start ??= now;
        const fraction = Math.min((now - start) / 300, 1);
        setProgress(1 - (1 - fraction) ** 3);
        if (fraction < 1) frame = requestAnimationFrame(tick);
      };
      frame = requestAnimationFrame(tick);
    });
    const finish = () => {
      if (!preference.matches) return;
      cancelled = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      setProgress(1);
    };
    preference.addEventListener('change', finish);
    observer.observe(element);
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      preference.removeEventListener('change', finish);
    };
  }, []);
  return { ref, progress };
}
