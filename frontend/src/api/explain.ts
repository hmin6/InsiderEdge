import type { ExplainResponse } from '../types/explain';

export const explanationSections = [
  ['why_flagged', 'Why flagged'],
  ['supportive_evidence', 'Supportive evidence'],
  ['risk_evidence', 'Risks / counter-evidence'],
  ['uncertainty', 'Uncertainty'],
  ['limitations', 'Limitations'],
] as const;

export function validateExplanation(value: unknown, ticker: string): ExplainResponse {
  if (!value || typeof value !== 'object') throw new Error('Invalid explanation');
  const data = value as Record<string, unknown>;
  if (data.ticker !== ticker || explanationSections.some(([key]) => !Array.isArray(data[key]) || !(data[key] as unknown[]).every(item => typeof item === 'string'))) {
    throw new Error('Invalid explanation');
  }
  return data as ExplainResponse;
}

export async function requestExplanation(ticker: string, signal: AbortSignal, baseUrl: string, fetcher: typeof fetch = fetch): Promise<ExplainResponse> {
  const response = await fetcher(`${baseUrl.replace(/\/$/, '')}/api/companies/${encodeURIComponent(ticker)}/explain`, { method: 'POST', signal, headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error('Explanation unavailable');
  return validateExplanation(await response.json(), ticker);
}

/** Explicit development fixture: never a fallback for failed production requests. */
export function mockExplanation(ticker: string): ExplainResponse {
  return {
    ticker,
    why_flagged: ['Development example only. No company signal has been evaluated.'],
    supportive_evidence: [],
    risk_evidence: ['Insider purchases do not establish future performance or causation.'],
    uncertainty: ['Real model and statistical evidence must be supplied by the backend.'],
    limitations: ['This is a mock response, not a Gemini-generated analysis or measured company result.'],
  };
}

// Conservative UI guard; the backend remains responsible for enforcing provider policy.
export function isResearchText(text: string): boolean {
  return !/\b(buy|sell|strong buy|trade|invest|investment advice|portfolio|position sizing|price target)\b/i.test(text);
}
