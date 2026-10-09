# SEC transaction ingestion — Issue #2

This pipeline stores normalized SEC Form 4 transactions only. It does not build
research events or calculate any research features or scores.

## Running

Install `requirements-dev.txt` into the project virtual environment. Configure
`DATABASE_URL` and a descriptive project/contact `SEC_USER_AGENT` in the ignored
repository-root `.env` or process environment. Only this CLI loads `.env`;
process environment values take precedence. No SEC credentials/API key are needed.
Initialize the Issue #1 schema before importing. From `backend/`:

```powershell
..\.venv\Scripts\python -m scripts.ingest_sec --mode discover
..\.venv\Scripts\python -m scripts.ingest_sec --mode bulk --end 2026-10-09
..\.venv\Scripts\python -m scripts.ingest_sec --mode edgar --end 2026-10-09
..\.venv\Scripts\python -m scripts.ingest_sec --mode all --end 2026-10-09
```

`all` downloads/imports every discovered quarter overlapping the requested date
range, then fills the recent gap. It can be a substantial download. Repeated runs
reuse cached bulk files and remain idempotent. To import a previously downloaded
official archive without web access:

```powershell
..\.venv\Scripts\python -m scripts.ingest_sec --mode bulk --bulk-file ..\data\sec_cache\2026q3_form345.zip
```

Repeat `--bulk-file` for multiple archives. Official `YYYYqN_form345.zip` filenames
are required for reporting. Dates default to 2020-01-01 through today's Eastern
calendar date. Rows with either transaction or filing dates before 2020 are excluded;
`--start`/`--end` additionally filter the filing-date window. Discovery does not
connect to the database. Imports require an explicitly configured database.

EDGAR queries use CIKs already present in `companies`, or repeated `--cik` options.
This is **not** universe construction. Company metadata must be populated by the
appropriate later issue. Supplied CIKs can be imported before mapping exists:
unmapped rows receive a NULL ticker plus diagnostics, preserving issuer CIK/name.
Persistence resolves exact compatible tickers or a unique normalized issuer CIK.
Shared-CIK ambiguity and conflicting known CIKs are diagnosed with NULL tickers;
no share class is chosen arbitrarily. An existing ticker with unknown CIK may
match by exact symbol. The loader
does not create companies, rename tickers, or fetch a mapping provider.

## Sources and joins

- Listing: https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets
- Archives: SEC links ending in `YYYYqN_form345.zip`, discovered from that listing.
- Table definitions: https://www.sec.gov/files/insider_transactions_readme.pdf
- Submissions: `https://data.sec.gov/submissions/CIK##########.json` and overlapping
  `CIK##########-submissions-NNN.json` history files listed by that response.
- Original XML: `https://www.sec.gov/Archives/edgar/data/<CIK integer>/<accession without dashes>/<primary document filename>`.
  XSL rendering directories are removed from metadata paths.

Quarterly archives are UTF-8 tab-separated files. The loader reads:

| Table | Key and use |
| --- | --- |
| SUBMISSION.tsv | `ACCESSION_NUMBER`; filing date, form, issuer CIK/name/symbol, AFF10B5ONE when present |
| REPORTINGOWNER.tsv | `(ACCESSION_NUMBER, RPTOWNERCIK)`; owner names and relationships/titles |
| NONDERIV_TRANS.tsv | `(ACCESSION_NUMBER, NONDERIV_TRANS_SK)`; Table I transaction fields |
| DERIV_TRANS.tsv | `(ACCESSION_NUMBER, DERIV_TRANS_SK)`; Table II transaction fields |

Both transaction tables join many-to-one to SUBMISSION on `ACCESSION_NUMBER`.
Owners are grouped by filing before attachment, so a multi-owner filing never
multiplies transaction shares/value. Distinct owner names and relationship/title
strings are sorted and joined with ` | ` in the existing schema's text fields.
This does not assign a particular transaction to an individual joint filer.
The cached source retains individual owner CIKs and relationship fields for later
research-event work. Holdings, signatures, and footnotes are not used to invent
missing transaction values. Original ZIP/XML files retain their provenance.

## Normalization and qualification

Both parsers emit the existing `insider_transactions` model fields, plus stable
`transaction_id` and `canonical_transaction_key`. Accession IDs use hyphens; CIKs
use ten digits; tickers are uppercase. Dates are parsed separately from ISO or
SEC `DD-MON-YYYY` formats. Acceptance timestamps require an explicit timezone;
invalid optional timestamps are reported and stored as NULL. `public_event_day`
remains NULL: deriving trading-calendar dates belongs to later work.

The exact qualification filter is form `4` or amendment `4-A`, non-derivative
Table I transaction, code `P`, acquired/disposed flag `A`. Code P means an
open-market **or private** purchase. No execution venue is inferred. Non-P and
derivative Form 4 rows remain stored with `is_p0_qualifying=false`.

Numeric fields use Decimal; negative, non-finite, or malformed values are reported
and become NULL. Missing optional values remain NULL without invented zeroes.
`transaction_value` is calculated with sufficient decimal precision only when
both shares and price are valid. A missing price does not erase transaction
provenance or invent purchase value. Security titles are preserved.

## Identity and amendments

Canonical identity version for this initial loader is a SHA-256 signature of:
accession, derivative flag, transaction date, transaction code, acquisition/disposal,
security title, shares, price, post-transaction ownership, and direct/indirect flag.
Text comparisons normalize whitespace/case, and identity numeric values round to
SEC bulk scale 2 with decimal HALF_UP. Stored numbers retain source precision.
This matters because the bulk archive rounds values that XML may report with
additional precision. Filing-wide owner metadata, ticker mapping, acceptance time,
source type, and bulk surrogate IDs are excluded from the signature.

An occurrence counter within each filing/signature preserves multiple legitimate
identical source rows. Their occurrence numbers are stable as a set even if the
bulk and XML transaction ordering differs. The key is
`<accession>:<signature hash>:<occurrence>`; `transaction_id` hashes that key.
Duplicate bulk surrogate keys are diagnosed and skipped before occurrence counting.
Use complete filings when calling parsers; importing arbitrary row subsets can
change occurrence numbering for identical rows.

Database inserts use parameterized SQLAlchemy `ON CONFLICT DO NOTHING` against
the canonical key, including concurrent imports. First-imported source fields
are retained; overlap may fill a previously missing acceptance time or mapped
ticker. Re-importing XML does not silently replace bulk numeric values with more
precise values. If XML precision is preferred, import XML first. Source corrections
that change the signature require review rather than an approximate automatic merge.
Rounding can create signature collisions; occurrence counting preserves source
multiplicity but cannot assign independent provenance beyond the published fields.

Form 4/A retains its own accession, amendment flag, and source rows. It is never
collapsed into the original filing by guessing. No research events are created,
so ingesting an amendment does not itself create a duplicate research event.
Later aggregation must explicitly reconcile amendment provenance before counting.

## Operations, diagnostics, and limits

Requests are sequential with at least 0.5 seconds between starts (at most 2/sec
per client), a 30-second timeout, and at most three attempts. HTTP 429 and selected
5xx/network failures receive bounded exponential backoff; numeric Retry-After is
honored up to 30 seconds. HTTP 403 is reported immediately without repeated access
attempts. Use one loader process to preserve the configured total rate.

The gap begins the day after the newest discovered quarter ends. Retrieval starts
seven calendar days before that boundary, overlapping the final week of bulk data
for cutoff/late-dissemination safety. Submission history pages overlapping the
requested window are included. This is daily filing-date ingestion, not intraday
public-availability reconstruction. Filing metadata is the filing-date authority;
XML transaction date never substitutes for it.

Default cache/report locations under `data/` are gitignored. Reports contain the
newest discovered quarter, quarters actually imported, retrieval/gap dates, source
URLs, counts, and row diagnostics (accession/field/reason, not credentials). Each
source is committed atomically, and reports checkpoint completed sources. A failed
source can be rerun. Inspect diagnostics before downstream use: missing required
dates/codes/identifiers or orphan transaction joins reject rows. Invalid archives,
missing tables, and conflicting submission keys fail explicitly. Network/database
failures exit nonzero; database exception details and credentials are not printed.

Cached files are immutable snapshots, not a refresh mechanism for SEC corrections.
Remove the relevant local cached file to download a corrected source, then review
identity changes before importing. SEC data can contain extraction discrepancies,
joint-owner ambiguity, amendments, and footnote-only prices. Inspect original
filings when they affect research. The loader cannot establish completeness beyond
the SEC sources and supplied issuer CIKs.

## Verification

```powershell
..\.venv\Scripts\python -m pytest -q
```

Tests use clearly synthetic ZIP/TSV/XML fixtures, mocked SEC access, and isolated
SQLite persistence with foreign keys enabled. Live verification on October 9,
2026 discovered 2026Q3 and parsed its real archive: 79,009 normalized Form 4 rows,
5,171 P0 qualifying rows, and eight malformed-row diagnostics. One matching live
XML filing's 29 transaction identities matched the bulk rows after accounting
for bulk numeric precision. These are ingestion validation counts, not research
metrics or investment results. No production database was populated.

Live recent-submissions checks also found six Form 4 filings for one supplied
sample issuer in the October 1–9 gap. An October 8 filing normalized successfully
with one transaction and no diagnostics. This is a sample connectivity/parser
check, not a claim that the whole universe or gap has been imported.

Before review, verify a disposable Tiger Data/PostgreSQL import twice, inspect
unique keys and unmapped diagnostics, and confirm the second run adds no duplicates.
Review the real EDGAR gap range and issuer coverage after company mapping is ready.
