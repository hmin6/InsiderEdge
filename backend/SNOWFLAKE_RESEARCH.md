# Snowflake Research Context - Issue #77



Snowflake Cortex REST inference is an optional supplemental qualitative layer.

Tiger/PostgreSQL remains the core source of truth. Snowflake never supplies inputs

to quant, ML, event selection, research-event creation, scores or Signal persistence.

Gemini and ElevenLabs remain independent and unchanged.



## A. Repository behavior



`POST /api/companies/{ticker}/snowflake-research` normalizes the ticker through the

existing frozen universe (unknown ticker: 404). The service selects the latest

persisted research event first, without requiring or borrowing a Signal.

It returns ticker, research_event_id, provider, model, status, context, provenance

and limitations. Context contains event_context, research_considerations and

filing_context string arrays. Missing configuration, missing event, invalid output

or provider failure returns HTTP 200 with status `unavailable` and null context/model.

Database failures retain the existing sanitized 503 behavior.



Only a user button click starts generation. There are no startup calls, automatic

retries, caching, generated-text persistence or database writes. The panel remains

separate from quantitative evidence and escapes output as text.



Transmitted data: frozen ticker/company name/sector; latest event ID, public day,

information date, source transaction/filing counts, supported buyer count (including

null), aggregate purchase value (including zero), and role bucket. When canonical

source transaction IDs exist in event provenance, at most 20 matching, non-amended,

qualifying rows for that ticker filed by the information boundary contribute

accession, document type, transaction/filing dates, P/A and derivative fields,

and bounded source-owner names/roles. Owner labels are not inferred buyer identities.

Legacy events without source IDs contribute no filing rows. The returned provenance

shows the exact supplied evidence; sample limits are explicit.



No prices, CAR outcomes, scores, probabilities, arbitrary feature_metadata,

credentials, unrelated rows or user-written prompts are transmitted. No web

browsing, SEC retrieval or RAG is performed. Output is validated as three required

arrays of one to six strict nonempty strings, at most 700 characters each; extra

fields, recommendations, ungrounded numeric tokens, links and markup are rejected. Numeric tokens must
match complete tokens in the exact serialized input; currency/unit suffixes are
part of a token. Numeric score/probability/return/price claims remain rejected.
Dates and accessions can be copied verbatim; formatting changes can be rejected. These

conservative checks can mark a benign model answer unavailable. Researchers must

still compare qualitative interpretations with the displayed source evidence.



## B. Account setup



The human confirmed a successful external Cortex REST request with `llama3.1-8b`,

a PAT restricted to `INSIDEREDGE_CORTEX_API`, and the database role

`SNOWFLAKE.CORTEX_REST_API_USER`. Keep tokens private. The integration uses

`POST /api/v2/cortex/v1/chat/completions` with model/messages, `max_completion_tokens=1800`, non-streaming JSON,

Bearer PAT authentication, and JSON HTTP headers. No SDK dependency is added.

See the [official Cortex REST reference](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-rest-api).



## C. Database/schema/warehouse



No project-data loading, Snowflake database/schema/warehouse creation, Cortex

Search service, PostgreSQL migration or core-data modification is required.



## D. Render environment - manual after review



Set backend-only variables using the account URL and private token configured

locally; never put them in Vercel or a `VITE_` variable:



- `SNOWFLAKE_ACCOUNT_URL`: HTTPS account origin ending in `.snowflakecomputing.com`.

- `SNOWFLAKE_PAT`: required secret, no default.

- `SNOWFLAKE_MODEL`: defaults to `llama3.1-8b`.

- `SNOWFLAKE_TIMEOUT_SECONDS`: defaults to 30; allowed range 1-60 seconds.



The ignored root `.env` supports local configuration through the existing backend

launcher. Missing variables do not prevent FastAPI startup. The existing transport

rejects redirects, caps the response at 128 KiB, sanitizes errors and never retries.



## E. Production verification - pending



After reviewing/deploying the branch and manually configuring Render, verify AXP

core reads and the optional panel, then authorize a single live generation using

the persisted event. Check exact provenance, qualitative grounding and graceful

fallback with configuration absent. Confirm scores and Signals are unchanged.

No live Snowflake, Gemini or ElevenLabs request was made for implementation tests.

Production domains, deployment configuration and existing demo evidence are unchanged.
