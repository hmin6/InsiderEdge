import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { InsiderEdgeScore } from "./InsiderEdgeScore";
import type { ScoreEvidence } from "../types/score";

const evidence: ScoreEvidence = {
  insider_edge_score: 73.125,
  anomaly_score: 0,
  activity_score: 42,
  statistical_score: 63,
  ml_outperformance_probability: 0.75,
  dislocation_score: 80,
  score_status: "complete",
};
test("preserves backend overall score independently of component values", () => {
  const html = renderToStaticMarkup(<InsiderEdgeScore evidence={evidence} />);
  assert.match(html, /73.13 out of 100/);
  assert.match(html, />73.13<\/strong>/);
  assert.match(html, /Research Priority/);
  assert.match(html, />75.00<\/strong>/);
  assert.match(html, /% probability/);
  assert.match(html, /Complete evidence/);
});
test("partial score preserves null and explicit zero distinctly", () => {
  const html = renderToStaticMarkup(
    <InsiderEdgeScore
      evidence={{
        ...evidence,
        statistical_score: null,
        score_status: "partial",
      }}
    />,
  );
  assert.match(html, /Partial evidence/);
  assert.match(html, /Some evidence is unavailable/);
  assert.match(html, />0.00<\/strong>/);
  assert.match(html, /Unavailable/);
  assert.equal((html.match(/class="ie-score-bar"/g) ?? []).length, 4);
  assert.match(html, />73.13<\/strong>/);
});
test("missing overall score is unavailable and never synthesized", () => {
  const html = renderToStaticMarkup(
    <InsiderEdgeScore
      evidence={{
        ...evidence,
        insider_edge_score: null,
        score_status: "insufficient_data",
      }}
    />,
  );
  assert.match(html, /Score unavailable/);
  assert.match(html, /Insufficient data/);
  assert.doesNotMatch(html, /class="ie-score-fill"/);
});
test("invalid numeric input does not produce NaN or misleading filled bars", () => {
  const html = renderToStaticMarkup(
    <InsiderEdgeScore
      evidence={{
        ...evidence,
        insider_edge_score: NaN,
        anomaly_score: Infinity,
        ml_outperformance_probability: 2,
        dislocation_score: -1,
      }}
    />,
  );
  assert.doesNotMatch(html, /NaN|Infinity/);
  assert.equal((html.match(/class="ie-score-bar"/g) ?? []).length, 2);
});


test("two-decimal formatting preserves styled card and probability scale", () => {
  const input = { ...evidence, insider_edge_score: 100, ml_outperformance_probability: .783456 };
  const html = renderToStaticMarkup(<InsiderEdgeScore evidence={input} />);
  assert.match(html, />100.00<\/strong>/);
  assert.match(html, />78.35<\/strong>/);
  assert.match(html, /class="ie-score-headline"/);
  assert.match(html, /class="ie-score-components"/);
  assert.equal(input.ml_outperformance_probability, .783456);
});
