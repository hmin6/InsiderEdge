// Only this public origin is embedded into the browser bundle.
export const API_BASE_URL = (
  import.meta.env?.VITE_API_BASE_URL?.trim()
  || (import.meta.env?.PROD ? '' : 'http://localhost:8000')
).replace(/\/+$/, '');
