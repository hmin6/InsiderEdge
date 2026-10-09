# Issue #30: resilience audit

Owner: Mingquan Lin. Branch: frontend/30-resilience.

The owner approved correcting Radar's null-to-zero sorting and the mock company's
missing unknown-ticker behavior. API_CONTRACT.md and other hard contracts are unchanged.

| Failure/state | Result |
| --- | --- |
| Radar loading | Content-shaped static skeleton; navigation stays available |
| Radar API failure | Controlled message and Retry Radar |
| Empty Radar | Explicit no-events state and refresh |
| Unknown ticker | ApiError(404), Unknown ticker message, retry/return navigation |
| Company failure | Controlled retry state, no raw server error text |
| Missing/failed prices | Local empty/error panel; score/statistics remain visible |
| Missing/failed insider history | Local empty/error panel; price series still renders without markers |
| No recent signal | Explicit no-event/no-score message |
| Insufficient anomaly history | Explicit unavailable evidence, never zero |
| Insufficient event-study history | Incomplete-history explanation beside returned horizons |
| Recent CAR30/CAR90 | Null remains Unavailable; realized CAR5 can still be displayed |
| Model unavailable | Local unavailable/failed panel, retry on endpoint failure |
| Partial score | Existing backend-status badge and partial-score explanation retained |
| Gemini timeout/failure | Independent request state and panel error boundary; quantitative panels remain mounted |
| ElevenLabs failure | Independent generation/audio state and panel error boundary; transcript survives audio failure |
| Component rendering failure | Panel-local boundary with retry and return navigation |
| Unknown route | Shared page-not-found state with Return to Radar |

Company no longer uses Promise.all to gate all research content. Each endpoint has
its own useResource instance, a 15-second timeout, retry, abort-on-unmount, and a
stale-response guard. Navigation remounts the company resource scope so old values
and AI results cannot appear under a new ticker. Chart space reserves 400px, other
loading/table regions reserve baseline heights; content can grow naturally.

The data client uses mocks only in development and labels them visibly. Set
VITE_USE_MOCKS=false to exercise FastAPI. The only recognized mock ticker is AAPL;
other symbols simulate 404 because no company fixture exists for them. Mock
statistics/prediction requests return controlled unavailable errors rather than
invented measured results. Production always uses FastAPI. Existing Gemini mock
configuration remains separate (VITE_EXPLAIN_MOCK=false for real requests).

PriceChart no longer substitutes zero for missing marker prices and observes
prefers-reduced-motion to disable Recharts animation. CSS skeletons remain static.
No new dependencies, score calculations, or provider credentials were introduced.

Validation: npm run build (zero errors), npm test (24 passing tests), git diff --check.
Vite reports a non-failing chunk-size warning for the bundle containing Recharts.
Tests cover null/zero ranking, normalized mock identity/404, controlled HTTP errors,
incomplete CAR horizons, missing model probability, existing partial-score states,
and provider request/response failure paths.

Manual browser verification remains necessary: throttle each endpoint separately;
exercise loading, retry, ticker changes during requests, empty prices/insider events,
HTTP-200 insufficient statistics, partial scores, provider timeouts, corrupt audio,
reduced motion, and narrow-screen keyboard navigation. Use real backend evidence
when available. Core/quant/statistics endpoints and providers still depend on the
backend team's integration; this issue supplies their failure behavior without
fabricating outputs. Automated tests do not exercise browser playback or layout.

PR target: main.

Closes #30
