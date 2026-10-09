# InsiderEdge Demo and Presentation Plan

## Demo company selection

Do not randomly search during judging. Choose a company with:

- clear qualifying insider purchase events;
- visually interesting stock/sector divergence;
- enough historical comparable events under the locked cohort rule;
- stable calculations;
- a useful Gemini explanation.

## Expected click path

1. Market Dislocation Radar.
2. Open the preselected top company.
3. Show qualifying code-P insider purchase events and filing/public-information dates.
4. Show anomaly score.
5. Show activity/cluster shift.
6. Show stock versus sector dislocation.
7. Show CAR results.
8. Show comparable-event definition and sample size.
9. Show bootstrap confidence interval.
10. Show randomized-timing-null p-value.
11. Show ML outperformance probability and held-out metrics.
12. Show final InsiderEdge Score and component breakdown.
13. Click **Explain Signal**; emphasize that Gemini explains rather than creates the signal.
14. Play ElevenLabs Analyst Brief only if stable.

## Thirty-second pitch

> InsiderEdge starts where a basic Form 4 tracker stops. We take newly public insider purchase events and combine unusual-activity detection, market and sector dislocation, comparable-event CAR analysis, bootstrap and randomized-timing validation, and leakage-aware machine learning to rank which events deserve deeper research. The result is a transparent InsiderEdge research-priority score with the underlying evidence visible, while Gemini explains the model-generated evidence rather than creating the signal. ElevenLabs can optionally turn that evidence into an analyst briefing.

## Presentation structure

1. Problem.
2. Solution.
3. Competitive differentiation: why this is more than a Form 4 tracker.
4. Data and public-information boundary.
5. Quantitative methodology and coursework mapping.
6. ML and chronological validation, including outcome-window split guard.
7. Live product demo — largest share of time.
8. Architecture / sponsor technology.
9. Closing: research prioritization, uncertainty, limitations, and scalability.

## Product-visual presentation goals

The final UI should look like a sleek institutional research product.

- Calm dark navy/charcoal shell with a light research workspace.
- Prominent but analytically honest InsiderEdge Score.
- Component breakdown understandable in seconds.
- Smooth, restrained 150–300 ms interactions.
- Subtle table-row hover/selection.
- Recharts line reveal and insider-event marker emphasis where practical.
- Skeleton loading rather than distracting page spinners.
- Gemini explanation expands/reveals without hiding quantitative evidence.
- No “BUY”, “SELL”, “Strong Buy”, casino, confetti, bouncing cards, or constantly pulsing UI.

## Critical presentation language

Use:

- “research priority” rather than “recommendation”;
- “qualifying code-P insider purchase events” rather than claiming every code-P transaction was exchange-only open-market execution;
- “Gemini explains the signal; it does not generate it.”
- “The model was selected on validation; the final test set was left untouched until the pipeline was frozen.”
- “The frozen current-S&P-100 historical sample may contain survivorship/selection bias.”

## Likely judge questions

### Is this investment advice?

No. It is a research-prioritization tool that surfaces evidence and uncertainty.

### Does Gemini predict the stock?

No. Statistical and ML code computes every quantitative result; Gemini explains structured outputs.

### How do you prevent leakage?

Features use only information available by filing/public-information time, model evaluation is chronological, and 30-trading-day outcome windows cannot cross into the next evaluation split.

### Why bootstrap / randomized timing?

To quantify uncertainty around historical comparable-event evidence and compare the observed historical effect with a randomized timing null.

### What counts as a comparable event?

The cohort rule is fixed in advance: same sector + same broad insider-role bucket, then same-sector fallback, with a minimum sample size. The selected rule and `n` are shown to the user.

### Why are A/C/S/D not ML inputs?

To keep the model probability a more distinct component and avoid intentionally feeding final-score components back into the model.

### Why Tiger Data?

Prices, insider events, rolling metrics, and historical signals are time-oriented data that benefit from persistent time-series querying.

### Why XGBoost?

It can capture nonlinearities/interactions, but it is retained only if validation results justify it versus Logistic Regression.

### Are all code-P transactions “open-market” trades?

No. SEC code P can represent an open-market or private purchase. P0 uses non-derivative code-P acquisitions and does not claim execution venue unless the filing establishes it.

## Failure fallback

Before judging, rehearse:

- slow frontend/backend network;
- Gemini unavailable;
- ElevenLabs unavailable;
- live market provider unavailable.

The demo should continue from persisted data, and quantitative results should remain visible even when optional AI/audio services fail.
