export type SnowflakeResult = {

  ticker: string; research_event_id: string | null; provider: 'snowflake';

  model: string | null; status: 'available' | 'unavailable';

  context: { event_context: string[]; research_considerations: string[]; filing_context: string[] } | null;

  limitations: string[];

};

export async function requestSnowflake(ticker: string, signal: AbortSignal, base: string, fetcher: typeof fetch = fetch): Promise<SnowflakeResult> {

  const response = await fetcher(`${base.replace(/\/$/, '')}/api/companies/${encodeURIComponent(ticker)}/snowflake-research`, {

    method: 'POST', signal, headers: { Accept: 'application/json' },

  });

  if (!response.ok) throw new Error('Snowflake research context unavailable');

  const result = await response.json();

  if (result.ticker !== ticker || result.provider !== 'snowflake' || !['available', 'unavailable'].includes(result.status)

      || !Array.isArray(result.limitations) || !result.limitations.every((x: unknown) => typeof x === 'string')) throw new Error('Invalid research context');

  if (result.status === 'available' && (!result.context || !['event_context', 'research_considerations', 'filing_context'].every(key =>

    Array.isArray(result.context[key]) && result.context[key].length > 0 && result.context[key].length <= 6 && result.context[key].every((x: unknown) => typeof x === 'string' && x.length > 0 && x.length <= 700)))) throw new Error('Invalid research context');

  return result;

}
