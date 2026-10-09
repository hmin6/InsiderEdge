export class ApiError extends Error {
  constructor(public status: number) { super(status === 404 ? 'Unknown ticker' : 'Research data unavailable'); }
}
export async function getJson<T>(url: string, signal?: AbortSignal, fetcher: typeof fetch = fetch): Promise<T> {
  const response = await fetcher(url, { signal, headers: { Accept: 'application/json' } });
  if (!response.ok) throw new ApiError(response.status);
  return response.json();
}
