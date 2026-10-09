# Issue #28: Explain Signal experience

Owner: Mingquan Lin. Branch: `frontend/28-gemini`.

The Company route currently has placeholder quantitative content. It now mounts
ExplainSignal with an unavailable score/evidence panel; it invents no metrics.
Person 3 can supply existing score/CAR/statistics/prediction panels through the
`evidence` prop. Those panels remain mounted in every explanation state.

```tsx
<ExplainSignal ticker={company.ticker} evidenceKey={researchEventId}
  evidence={<>{existingScorePanel}{existingStatisticsPanel}{existingPredictionPanel}</>} />
```

Changing ticker or evidenceKey remounts the request and clears stale explanations.
Requests are aborted on unmount and time out after 20 seconds. A synchronous request
ref blocks duplicate clicks, including clicks before React renders the disabled
button. Successful responses are retained without repeated generation; failures
allow retry. No provider response/error text is exposed as an error message.

The backend endpoint is POST `/api/companies/{ticker}/explain`, with no provider key
or client-computed evidence sent. Configure `VITE_API_BASE_URL` for FastAPI.
No browser code accesses Gemini or its credentials.

The explain backend is not yet present. Development mode defaults to a clearly
labeled mock matching API_CONTRACT.md; it contains no company conclusions or fake
measured evidence. Set `VITE_EXPLAIN_MOCK=false` and restart Vite to exercise the
real request, loading, timeout, and failure states. Production builds always call
FastAPI and never silently fall back to mock explanations.

All five sections render as escaped plain text. A conservative UI filter withholds
items containing common trade/advice language. This is a supplementary guard, not
a complete advice classifier; the backend provider prompt must enforce the
research-only output policy. No HTML or Markdown from Gemini is executed.

Success uses the shared 220ms reveal; reduced-motion disables it. Skeletons are
static and announced through a status region. Content is visible if motion fails.

Validation: `npm run build`, `npm test`, `git diff --check`.
Manual review: navigate to `/company/AAPL`, inspect the labeled mock and five
sections, then disable mock mode and test slow/error responses, repeated clicks,
ticker navigation, reduced motion, and quantitative evidence persistence.
Real Gemini integration awaits the backend endpoint and company data integration.

PR target: `main`.

Closes #28
