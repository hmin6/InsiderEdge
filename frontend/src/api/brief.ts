import type { BriefResponse } from '../types/brief';

export function validateBrief(value: unknown, ticker: string): BriefResponse {
  if (!value || typeof value !== 'object') throw new Error('Invalid brief');
  const data = value as Record<string, unknown>;
  if (data.ticker !== ticker || typeof data.transcript !== 'string' ||
    !['ok', 'audio_unavailable'].includes(String(data.status)) ||
    !(data.audio_base64 === null || typeof data.audio_base64 === 'string') ||
    !(data.audio_mime_type === null || typeof data.audio_mime_type === 'string')) throw new Error('Invalid brief');
  return data as BriefResponse;
}

export async function requestBrief(ticker: string, signal: AbortSignal, baseUrl: string, fetcher: typeof fetch = fetch): Promise<BriefResponse> {
  const response = await fetcher(`${baseUrl.replace(/\/$/, '')}/api/companies/${encodeURIComponent(ticker)}/brief`, {
    method: 'POST', signal, headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error('Analyst brief unavailable');
  return validateBrief(await response.json(), ticker);
}

/** Decode only audio MIME types; malformed audio must not discard the transcript. */
export function briefAudioBlob(brief: BriefResponse): Blob | null {
  if (brief.status !== 'ok' || !brief.audio_base64 || !brief.audio_mime_type) return null;
  if (!/^audio\/[a-z0-9.+-]+$/i.test(brief.audio_mime_type)) throw new Error('Invalid audio format');
  const decoded = atob(brief.audio_base64);
  return new Blob([Uint8Array.from(decoded, char => char.charCodeAt(0))], { type: brief.audio_mime_type });
}
