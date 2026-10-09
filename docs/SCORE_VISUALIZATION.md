# Issue #27: score visualization

Human owner: Mingquan Lin. Branch: `frontend/27-score-visualization`.

Import the shared stylesheet once (`frontend/src/styles/index.css`) and use:

```tsx
import { InsiderEdgeScore } from '../components';

// latest_signal / RadarItem already carries the required fields.
<InsiderEdgeScore evidence={company.latest_signal} />
```

Only render when `latest_signal` exists; the consuming page owns loading and data
fetching. The component accepts the API's score fields through `ScoreEvidence`.
It displays `insider_edge_score` directly, with no weighting or renormalization.
M is displayed as model probability × 100 with a percentage label. Component bars
represent levels, not weighted contributions. Null and invalid values display as
Unavailable; explicit zero remains zero. Backend `score_status` is authoritative.

The first visible reveal uses requestAnimationFrame over 300ms. The visible
temporary count is decorative; accessible text always exposes the exact backend
score. At completion the visible number uses the backend value without rounding.
Ring and bars share the reveal progress. Reduced-motion preference shows final
values immediately and cancels a running animation if the preference changes.
Without IntersectionObserver, the component remains static at final values.

No synthetic financial results are included in the development preview; it shows
the unavailable state. Numeric examples exist only in tests.

Manual review: use real backend evidence in the company page, verify first reveal
when scrolling into view, toggle reduced motion during the reveal, check partial
and missing components, and check layout at 375px width. Automated rendering tests
cover exact values, zero/null distinction, status text, and invalid values; browser
animation and layout have not been automatically exercised.

PR target: `main`.

Closes #27
