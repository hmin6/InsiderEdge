# Frozen hackathon universe — Issue #3

`universe.csv` is the fixed InsiderEdge universe frozen on **October 9, 2026**.
It contains **101 securities representing 100 issuer CIKs**. GOOG and GOOGL remain
separate Alphabet share-class records with the same issuer CIK.

Membership, company/security names, and sectors come from the equity holdings of
the [iShares S&P 100 ETF (OEF)](https://www.ishares.com/us/products/239723/ishares-sp-100-etf),
as of **October 8, 2026**, the latest completed holdings date at retrieval. OEF
tracks the S&P 100; its equity holdings were selected as the available membership
source for this hackathon. This is a fund-holdings snapshot rather than a licensed
direct index constituent export. Cash, futures, and other non-equities are excluded.
Review membership against the index provider if a tracker discrepancy is discovered.

CIKs were matched by exact canonical ticker against the
[SEC company ticker file](https://www.sec.gov/files/company_tickers.json), retrieved
on October 9. No fuzzy company-name matching or guessed identifiers were used.
All 101 securities resolved; the only shared CIK in this snapshot is Alphabet's.
`universe.provenance.json` records source URLs, source-file SHA-256 hashes, snapshot
hash, counts, dates, and transformations. Company names retain the source security
labels, including classes. The CSV contains only `ticker,cik,company_name,sector`;
no prices, weights, or measured research outputs are included.

CIKs are nullable ten-digit strings. Integer and unpadded digit-string inputs
normalize to that representation; zero, floats, booleans, and malformed strings
are rejected. Missing identifiers stay missing. Tickers are uppercase with
surrounding whitespace removed. The internal Berkshire Class B symbol is `BRK.B`;
the documented source/provider aliases `BRK B` and `BRK-B` resolve to it. No general
punctuation removal is performed: unrelated securities are never collapsed.
`Communication` from OEF is normalized to the project sector name
`Communication Services`. All other sectors retain source labels.

## Historical limitation and freeze policy

Using this current/hackathon-start universe for 2020–2026 research is **not a
point-in-time reconstruction of historical S&P 100 membership**. It introduces
survivorship and selection bias. Results must disclose this limitation. P0 does
not reconstruct historical membership.

Runtime lookups read only the checked-in CSV and make no network requests. They
never update membership automatically. Once the training/evaluation dataset is
generated, retain the same snapshot and provenance hash across all splits.
Changing it requires an explicit reviewed dataset/version decision and dataset
regeneration; do not quietly rerun with a newer membership list.

The one-time offline builder refuses to overwrite a snapshot. It can reproduce
the snapshot in a **new output directory** from the original downloaded files:

```powershell
# From backend/; source files were retained locally, excluded from Git.
..\.venv\Scripts\python -m scripts.freeze_universe --holdings ../data/universe_sources/holdings.csv --sec-identifiers ../data/universe_sources/company_tickers.json --freeze-date 2026-10-09 --output ../data/universe_sources/reproduced
```

The source URLs are mutable; matching the recorded source hashes is required for
exact reproduction. The checked-in CSV is the actual runtime data artifact.

## Reusable lookups

```python
from app.services.universe import Universe, AmbiguousCIKError

universe = Universe.from_csv()  # Path is independent of current working directory.
universe.ticker_to_cik('aapl')           # '0000320193'
universe.ticker_to_company('GOOGL')     # Exact Class A metadata record
universe.cik_to_ticker(320193)          # 'AAPL'
universe.cik_to_tickers(1652044)        # ('GOOG', 'GOOGL')
universe.cik_to_ticker(1652044)         # Raises AmbiguousCIKError; never guesses
universe.resolve_issuer(1652044)        # Explicit ambiguous result, ticker=None
universe.resolve_issuer(1652044, 'GOOG') # Exact compatible ticker resolves Class C
```

Missing/unknown single lookups return `None`; plural lookup returns an empty tuple.
`resolve_issuer` returns status, selected ticker or None, candidate tickers, and
reason. Status is `matched`, `unmapped`, `ambiguous`, `conflict`, or `invalid`.
Contradictory known ticker/CIK pairs are conflicts. No source symbols are silently
reassigned to a different known issuer. A unique CIK can resolve an unknown/missing
symbol, but a CIK shared by several classes requires an exact compatible ticker.

The SEC persistence layer reuses these rules against **existing database company
rows**, not by automatically loading the CSV or creating company records. An
ambiguous/conflicting/unmapped transaction retains its issuer CIK and provenance,
gets a NULL ticker, and produces a diagnostic. It does not use security-title
heuristics to guess a share class. Previously mapped transaction rows are not
retroactively changed: review earlier mappings after adding share classes.

## Approved database correction

`companies.ticker` remains the primary key; `companies.cik` now has a **non-unique
index**. This was explicitly approved as Issue #3's narrow real-data correction.
No company_id, API change, research-event change, or other schema redesign is used.

For a fresh database, `scripts.init_db` creates the corrected definition. For an
existing PostgreSQL/Tiger Data database created by Issue #1, run this migration
before inserting share-class records (set DATABASE_URL in the process environment):

```powershell
# From backend/
..\.venv\Scripts\python -m scripts.migrate_company_cik
```

The migration reflects the table, drops only single-column CIK uniqueness
constraints/indexes, and creates `ix_companies_cik` if absent. It runs in a
transaction and is repeatable. It preserves the ticker primary key, other
constraints, and all data. `create_all` alone does not alter an existing constraint.
No database migration or company population was executed during implementation.

Manual review: verify the migration twice on disposable PostgreSQL, confirm shared
CIKs can be inserted while duplicate tickers remain prohibited, inspect ambiguous
SEC diagnostics, and review the dated source membership and share-class labels.
