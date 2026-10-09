# InsiderEdge Coursework and Methodology Mapping

This document distinguishes methods grounded in Math 340–343 from finance/time-series extensions and InsiderEdge-specific design choices. Do not present external/project-specific methods as if they came directly from coursework.

## Coursework-derived methods

| Course | Concepts | InsiderEdge use |
|---|---|---|
| Math 340 | probability, expectation/variance, covariance, covariance matrices, multivariate reasoning, Mahalanobis distance | market variability and covariance-aware anomaly detection; chi-square calibration under the course assumptions |
| Math 341 | statistical inference, confidence intervals, hypothesis-testing logic, p-values, multiple testing/FDR | interpretation of historical event evidence; optional FDR if many simultaneous tests are shown |
| Math 342W | Logistic Regression, predictive modeling, honest out-of-sample validation, ROC/AUC, Brier/probability scoring, overfitting/generalization, tree/ensemble/boosting concepts where covered | Logistic baseline, probability prediction, chronological validation, held-out metrics; XGBoost is an implementation candidate, not claimed as a full course derivation |
| Math 343 | bootstrap, permutation/randomization concepts, computational inference, robust/asymptotic modeling, optional Poisson/change-point ideas | bootstrap CI for CAR30, conceptual basis for randomization inference, optional activity-rate extensions |

## Finance/time-series extensions retained in the master plan

These methods are not claimed as course-derived:

- market-model event studies;
- abnormal returns and CAR;
- event-window overlap/dependence concerns;
- filing/public timing as an information boundary;
- finance-specific outcome-window leakage safeguards.

Recent/canonical references retained by the master plan include:

- El Ghoul, Guedhami, Mansi, and Sy (2023), *Event studies in international finance research*. DOI: https://doi.org/10.1057/s41267-022-00534-6
- Eden, Miller, Khan, Weiner, and Li (2022), *The event study in international business research: Opportunities, challenges, and practical solutions*. DOI: https://doi.org/10.1057/s41267-022-00509-7
- Nguyen and Wolf (2024), *Single-firm inference in event studies via the permutation test*. DOI: https://doi.org/10.1007/s00181-023-02530-7
- Pynnönen (2022), *Non-Parametric Statistic for Testing Cumulative Abnormal Stock Returns*. DOI: https://doi.org/10.3390/jrfm15040149
- Dezhkam et al. (2023), *A Bayesian-based classification framework for financial time series trend prediction*. DOI: https://doi.org/10.1007/s11227-022-04834-4
- Lasfer and Ye (2024), *Corporate insiders' exploitation of investors' anchoring bias at the 52-week high and low*. DOI: https://doi.org/10.1111/fire.12371
- Oenschläger and Möllenhoff (2025), *Insider filings as trading signals—Does it pay to be fast?*. DOI: https://doi.org/10.1016/j.frl.2024.106514
- Cline and Houston (2023), *Insider Filing Violations and Illegal Information Delay*. DOI: https://doi.org/10.1017/S0022109022000953
- SEC ownership form codes: https://www.sec.gov/edgar/searchedgar/ownershipformcodes.html
- SEC Insider Transactions Data Sets: https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets
- MacKinlay (1997), *Event Studies in Economics and Finance*, retained as canonical background.

## InsiderEdge-specific design choices

These are transparent project choices, not formulas copied from coursework or a cited paper:

- exact CAR5/CAR30/CAR90 horizons;
- 30-session SPY-outperformance ML target;
- one-`ticker` + `public_event_day` research-event aggregation;
- broad role hierarchy `Executive > Director > Other`;
- comparable-event cohort hierarchy and minimum sample sizes;
- exact randomized-timing null construction;
- activity-score formula;
- market-dislocation formula;
- Mahalanobis reference-population/fallback policy;
- 0–100 bootstrap/randomization support mappings;
- final InsiderEdge Score weights;
- partial-score handling policy concretized in `MODEL_SPEC.md`.

These choices must be described as heuristics/design decisions and never as theoretically optimized or statistically guaranteed.

## Concise presentation line

> We combined multivariate statistics, statistical inference, resampling methods, and predictive modeling from our coursework with recent financial event-study methodology, while clearly separating our own research-event, scoring, and validation design choices.
