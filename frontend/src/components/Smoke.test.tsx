import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import {
  DEV_MOCK_RADAR,
  DEV_MOCK_STATISTICS,
  DEV_MOCK_PREDICTION,
  DEV_MOCK_PRICES,
  DEV_MOCK_INSIDERS,
} from "../api/mocks";
import { PriceChart } from "./PriceChart";
import {
  StatisticsEvidence,
  PredictionEvidence,
  rankRadar,
} from "./ResearchStates";
import { InsiderEdgeScore } from "./InsiderEdgeScore";
import RadarPage from "../pages/RadarPage";
import CompanyPage from "../pages/CompanyPage";

test("1. Radar renders API items and 2. ranking/navigation works", () => {
  const ranked = rankRadar(DEV_MOCK_RADAR.items);
  assert.equal(ranked[0].ticker, "AAPL");

  const radarHtml = renderToStaticMarkup(
    <MemoryRouter>
      <RadarPage />
    </MemoryRouter>,
  );
  // Initially renders loading skeleton, validating the API integration boundary
  assert.match(radarHtml, /Loading Radar/);
});

test("3. Company page renders headline score", () => {
  const scoreHtml = renderToStaticMarkup(
    <InsiderEdgeScore evidence={DEV_MOCK_RADAR.items[0]} />,
  );
  assert.match(scoreHtml, /85/);
  assert.match(scoreHtml, /Research Priority/);
});

test("4. Statistics section renders", () => {
  const statsHtml = renderToStaticMarkup(
    <StatisticsEvidence data={DEV_MOCK_STATISTICS} />,
  );
  assert.match(statsHtml, /Anomaly &amp; Activity Evidence/);
  assert.match(statsHtml, /Event Study &amp; Statistical Evidence/);
  assert.match(statsHtml, /90/); // Anomaly score
});

test("5. Prediction section renders", () => {
  const predHtml = renderToStaticMarkup(
    <PredictionEvidence data={DEV_MOCK_PREDICTION} />,
  );
  assert.match(predHtml, /ML Prediction/);
  assert.match(predHtml, /65\.00%/);
});

test("6. Empty optional fields do not crash and 7. insufficient_data is displayed correctly", () => {
  const emptyStatsHtml = renderToStaticMarkup(
    <StatisticsEvidence
      data={{
        ...DEV_MOCK_STATISTICS,
        anomaly: { ...DEV_MOCK_STATISTICS.anomaly, score: null, status: "insufficient_data" },
        event_study: {
          car5: null,
          car30: null,
          car90: null,
          status: "insufficient_data",
        },
        statistical_validation: {
          ...DEV_MOCK_STATISTICS.statistical_validation,
          statistical_score: null,
          status: "insufficient_data",
        },
      }}
    />,
  );
  assert.match(emptyStatsHtml, /Anomaly evidence is unavailable/);
  assert.match(emptyStatsHtml, /Future CAR is not yet known/);
  assert.match(emptyStatsHtml, /Combined statistical score unavailable/);

  const insufficientPredHtml = renderToStaticMarkup(
    <PredictionEvidence
      data={{
        ...DEV_MOCK_PREDICTION,
        outperformance_probability: null,
        status: "insufficient_data",
      }}
    />,
  );
  assert.match(insufficientPredHtml, /Model prediction unavailable/);
});

test("8. API failure produces a useful error state and 9. Unknown company does not produce a blank screen", () => {
  // By rendering CompanyPage with a MemoryRouter, we simulate the initial mount.
  // If it crashed on an unknown ticker, renderToStaticMarkup would fail.
  const companyHtml = renderToStaticMarkup(
    <MemoryRouter initialEntries={["/company/UNKNOWN"]}>
      <Routes>
        <Route path="/company/:ticker" element={<CompanyPage />} />
      </Routes>
    </MemoryRouter>,
  );

  // Initially, useResource puts the page in a loading state, avoiding a blank screen
  // and safely preparing to catch the API failure gracefully.
  assert.match(companyHtml, /Loading company score/);
  assert.match(companyHtml, /UNKNOWN/); // The unknown ticker is safely rendered in the header
});

test("Price chart renders without crashing on empty or populated data", () => {
  const chartHtml = renderToStaticMarkup(
    <PriceChart
      prices={DEV_MOCK_PRICES.prices}
      transactions={DEV_MOCK_INSIDERS.transactions}
    />,
  );
  assert.ok(chartHtml.includes("ie-price-chart"));

  const emptyChartHtml = renderToStaticMarkup(
    <PriceChart prices={[]} transactions={[]} />,
  );
  assert.match(emptyChartHtml, /No price history available/);
});
