# Issue #31: final demo polish

Owner: Mingquan Lin. Branch: frontend/31-demo-polish.
The changes follow docs/DEMO_PLAN.md and preserve the existing product structure.

Presentation changes:

- Larger body/table text, explicit Model probability and Research priority score
  headings, restrained emphasis for the score column, and keyboard row focus.
- Larger score ring and numeric headline, more readable component labels/bars,
  and stacked component values on narrow screens.
- Aligned CAR cards, prominent model probability, and spacing between evidence text.
- Larger chart ticks, more space for axis labels, clearer price tooltip labeling,
  and slightly larger existing insider markers. Marker dates/filtering are unchanged.
- Section dividers and bounded line lengths for Gemini explanations; full-width
  native audio controls; content-shaped static skeletons.

No requests, sorting, calculations, API contracts, marker timing, chart library,
fallback behavior, or animation durations changed. No dependencies were added.
The score retains its existing 300ms reveal; chart animation retains its reduced-
motion check; shared CSS retains 150/220/300ms tokens and reduced-motion override.
No additional animation or expensive per-frame work was introduced.

Validation: npm run build passed with zero errors, npm test passed all 24 tests,
and git diff --check passed. Vite still reports the existing non-blocking bundle
size warning for the application containing Recharts.

Manual review before judging: rehearse the chosen real company at 1366x768 and
1920x1080, inspect the horizontally scrollable Radar table at 375px, tab through
links/buttons/audio controls, enable reduced motion, and exercise slow data,
Gemini failure, and audio failure. Check long/unavailable numeric values, tooltip
readability, and animation smoothness on the actual demo laptop/projector.
Browser visuals and performance have not been instrumented in this session.

PR target: main.

Closes #31
