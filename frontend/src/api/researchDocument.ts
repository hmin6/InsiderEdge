import type { SnowflakeResult } from './snowflake';
import type { ExplainResponse } from '../types/explain';
import { validateBrief } from './brief';

export const RESEARCH_DISCLAIMER = 'AI tools interpret existing evidence. They do not calculate or modify InsiderEdge scores or predictions. Research only; not investment advice.';
export const MAX_RESEARCH_AUDIO_CHARACTERS = 10000;
export type ResearchDocument = {
  title: 'Research Summary';
  sections: { title: string; items: string[] }[];
  sources: string[];
  unavailable: string[];
  disclaimer: typeof RESEARCH_DISCLAIMER;
};
export type ResearchAudioRequest = {
  research_event_id: string;
  snowflake_context?: NonNullable<SnowflakeResult['context']>;
  gemini_explanation?: ExplainResponse;
  document: ResearchDocument;
};

/** Ordered, verbatim source sections. No inference, rewriting, or numerical calculations. */
export function combineResearch(snowflake: SnowflakeResult['context'], gemini: ExplainResponse | null): ResearchDocument | null {
  if (!snowflake && !gemini) return null;
  const sections: ResearchDocument['sections'] = [];
  function add(title: string, items: string[]) { if (items.length) sections.push({ title, items }); }
  if (snowflake) add('Event & Filing Context', [...snowflake.event_context, ...snowflake.filing_context]);
  if (gemini) {
    add('Signal Interpretation', gemini.why_flagged);
    add('Supporting Evidence', gemini.supportive_evidence);
    add('Risks / Counter-Evidence', gemini.risk_evidence);
    add('Uncertainty & Limitations', [...gemini.uncertainty, ...gemini.limitations]);
  }
  if (snowflake) add('Research Considerations', snowflake.research_considerations);
  return { title: 'Research Summary', sections,
    sources: [...(snowflake ? ['Snowflake Cortex - event and filing context'] : []),
      ...(gemini ? ['Gemini - quantitative signal interpretation'] : [])],
    unavailable: [...(snowflake ? [] : ['Qualitative research context was unavailable.']),
      ...(gemini ? [] : ['Quantitative AI interpretation was unavailable.'])],
    disclaimer: RESEARCH_DISCLAIMER };
}

export function researchScript(ticker: string, document: ResearchDocument): string {
  return [`InsiderEdge research for ${ticker}.`, document.title,
    ...document.sections.flatMap(section => [section.title, ...section.items]),
    ...document.unavailable, 'Research generated from:', ...document.sources, document.disclaimer].join('\n');
}

export async function requestResearchAudio(ticker: string, research: ResearchAudioRequest, signal: AbortSignal,
  base: string, fetcher: typeof fetch = fetch) {
  const response = await fetcher(`${base.replace(/\/$/, '')}/api/companies/${encodeURIComponent(ticker)}/research-audio`, {
    method: 'POST', signal, headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(research),
  });
  if (!response.ok) throw new Error('Research audio unavailable');
  const result = validateBrief(await response.json(), ticker);
  // Never play a different document returned from a stale or inconsistent backend.
  if (result.transcript !== researchScript(ticker, research.document)) throw new Error('Research audio mismatch');
  return result;
}
