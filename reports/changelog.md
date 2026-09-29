# Research/software changelog

## Software 0.1.12 / P1-04 market inputs and EV bridge — 2026-09-29

- Add distinct SECZ NYSE share price, basic/diluted counts, interest-bearing debt, preferred/noncontrolling claims, unrestricted/restricted cash and nonoperating assets; add UNI/XLM native circulating and total supply concepts. Prices bind exact security, instrument, venue, currency and timestamp.
- Add five locked read-only equity/cap/FDV/EV formulas and `market-report`. An incomplete EV bridge returns Unknown; provider cap comparison retains delta, dates, tolerance and an explicitly analyst-classified discrepancy note. Scenario price reverse input remains separate from observed current-market reverse input.
- Enforce publication/system knowledge, quote age, structure age, as-of precision, issuer security and source lineage. Bundle market definitions in v2 audit schema `2.0-compute-bundle.6`. [P1-04 validation](p1-04-validation.md): 156 tests; real market/financial observations remain 0. P1-05 UNI evidence is next.

## Software 0.1.11 / P1-03 normalization dictionary — 2026-09-29

- Add explicit measurement basis, YTD periods and role-level accounting filters. Equal GAAP/adjusted values remain conflicting evidence; supersession and resolutions cannot cross measurement bases.
- Add six locked, read-only transformations for scaling, exact-period average FX, TTM, YTD difference, CAGR and percent to basis points. DERIVED reports preserve raw OBSERVED leaves, source IDs and formula signatures; unsuitable units, fiscal periods, scopes and denominators fail closed.
- Freeze registry and signature lock in v2 audit bundle `2.0-compute-bundle.5`; preserve v1 snapshots and empty canonical finance evidence. [P1-03 validation](p1-03-validation.md): 145 tests. P1-04 market inputs and EV bridge are next.

## Software 0.1.10 / P1-02 entity and security identity — 2026-09-29

- Add strict, read-only v2 identity master with distinct entity/security/instrument IDs, venue-scoped dated aliases, corporate-action links, underlying rights and independent research/listing/eligibility dimensions. Unknown alias starts and personal trade access remain unknown; checked links are not approved source artifacts or financial observations.
- Correct SECZ legacy listing metadata after checking SEC completion and registration filings plus issuer listing announcement; predecessor CEPT is a separate security. Preserve original v1 financial formulas, fixture snapshots and empty research evidence.
- Bundle identity definitions in v2 audit replay contract `2.0-compute-bundle.4`; [P1-02 validation](p1-02-validation.md): 136 tests, DEMO/RESEARCH 94 metrics and zero issues. P1-03 normalization is next.

## Software 0.1.9 / P1-01 source staging and review — 2026-09-29

- Add strict manual source capture into an append-only staging ledger with actual acquisition time, SHA-256/size, locator, rights and explicit failure/unknown-date states. Raw bytes are content-addressed outside the checkout; URL credentials and raw checkout paths are refused.
- Add human review and atomic metadata promotion into the v2 source registry under the existing publication journal. Approved sources retain artifact digest and review ID, while observations remain empty. V2 audit bundles now archive the staging/review trail under `2.0-compute-bundle.3` without copying raw restricted bytes.
- [P1-01 validation](p1-01-validation.md): 132 tests, both validation modes 94 metrics/0 issues, original v1 snapshot digests unchanged. No real artifact/source/observation was ingested; P1-02 identity and investability is next.

## Software 0.1.8 / P0-10 G0 integration acceptance — 2026-09-29

- Lock the G0 interpreter and dependency version, add pull-request/main CI and a read-only acceptance command covering the full regression suite, both validation modes, backlog blockers and research observation count.
- Add disposable cross-boundary negative tests for fixture isolation, knowledge-time and scope rejection, digest replay and crash recovery; independently recompute existing UNI/SECZ/XLM synthetic golden values without changing their expectations.
- [P0-10 validation](p0-10-validation.md): 127 tests; DEMO/RESEARCH 94 metrics and zero issues each; two original v1 DEMO snapshot digests unchanged. Engineering G0 passes, decision-ready research remains blocked by unresolved P0 priorities, absent real observations and incomplete G1. P1-01 is next.

## Software 0.1.7 / P0-09 quality and reviewed conflict selection — 2026-09-29

- Split v2 source tier, freshness, declared coverage, unverified measurement, mechanism, and conflict into inspectable dimensions. Multi-layer derived metrics and quarterly rules retain upstream assumption/scenario IDs; legacy v1 confidence now follows transitive leaves.
- Add strict research/DEMO resolution ledgers; a reviewed decision can select only from the exact eligible conflicting candidate set after all candidates were published and ingested. Later candidates invalidate the prior selection; rejected evidence and rationale stay visible.
- [P0-09 validation](p0-09-validation.md): 119 tests; bundle contract `2.0-compute-bundle.2` archives the new ledger and replays offline, two v1 DEMO snapshots unchanged, DEMO/RESEARCH each 94 metrics and zero issues. P0-10 integration gate remains pending.

## Software 0.1.6 / P0-08 pure reads and recoverable publication — 2026-09-28

- `/api/state` no longer writes snapshots; HTTP reads and read-only CLI use a project lock and return a pending-publication error instead of a mixed version.
- Explicit `apply-event` stages ledger, immutable snapshot and changelog in a synced redo journal under a cross-process lock; `recover` completes interrupted writes. Concurrent publishers rebase and identical retries do not repeat observations or events. V1/v2 single-file snapshots share the lock.
- [P0-08 validation](p0-08-validation.md): 113 tests, five injected failure boundaries, CLI multi-process retry, GET file fingerprints, external-edit fail-closed recovery; DEMO/RESEARCH validation 94 metrics/0 issues. Original v1 snapshot digests unchanged. P0-09 quality propagation remains pending.

## Software 0.1.5 / P0-07 replayable v2 compute bundles — 2026-09-27

- Added separate v2 `snapshot-v2`/`replay-v2` CLI commands. Deterministic, content-addressed audit bundles freeze the runtime lock, all engine code, formula/rule/dictionary/graph definitions, exact evidence ledgers and source metadata, query cutoffs, selected record/source hashes and both v2 economics/cadence outputs. Replay compares installed code byte-for-byte and recomputes from extracted frozen inputs without the original checkout.
- Explicit HISTORICAL and CURRENT tracks stay separate: historical clocks and knowledge policy are required; current captures UTC now and uses system-as-known. A selected record with knowledge after its cutoff is refused, incomplete results remain Unknown, and artifacts are marked AUDIT_ONLY. V1 snapshots stay byte-identical and cannot be promoted to v2 historical replay.
- [P0-07 validation and migration report](p0-07-validation.md): 108 tests including disposable clean-environment replay, byte/semantic/code/runtime tampering, system/public restatement split, track isolation and CLI idempotence. V1 DEMO/RESEARCH validation remains 94 metrics with zero issues. P0-08 GET purity and cross-file crash-safe publication remain pending.

## Software 0.1.4 / P0-06 independent v2 rule cadence — 2026-09-27

- Introduced locked v2 asset/rule calendars and a read-only quarterly scheduler: explicit economic/knowledge cutoffs and period-specific valuations; fiscal-quarter labels, missing-quarter and reporting grace, period age, TTM endpoint and quote freshness all fail closed with per-rule period/source evidence.
- Kept all nine legacy rule identities visible: only the source-backed v2 UNI realized burn rule is currently evaluable; the eight unmigrated rules and SECZ unverified issuer calendar remain unevaluated rather than silently claiming Healthy. Daily UNI quotes no longer perturb v2 SECZ/XLM quarterly selection. Legacy v1 thesis and two demo snapshots are unchanged and explicitly labeled not point-in-time.
- Added `thesis-cadence` CLI, `/api/thesis-cadence` and a separate v2 dashboard inspector. New tests cover synthetic trigger, cross-asset daily quote, missing/fiscal/TTM periods, stale quote, historical restatement policies, rule-lock tampering, fixture isolation and read-only boundaries. [P0-06 validation](p0-06-validation.md): 102 tests; v1 DEMO/RESEARCH validation each 94 metrics, zero issues. No real market observation or canonical snapshot added.

## Software 0.1.3 / P0-05 scope-aware UNI economics — 2026-09-26

- Introduced locked v2 UNI formulas using explicit roles and economic/knowledge/valuation times: actual-quarter realized net burn, arithmetic annualized run rate, future annual protocol revenue and standalone reverse-required market share. A forward scenario may cover a future period but must be known by the query cutoff; completed realized quarters cannot come from the future.
- No actual burn is inferred from fees. All missing inputs remain Unknown; bounds, period alignment, quote freshness, zero denominator, sources, formula signatures and transitive record IDs are checked. No real observations were added; new numeric regression data live only in disposable test packs.
- Exposed a read-only `scope-report` CLI and `/api/economics`/Dashboard scope display. Flagged mixed v1 UNI/XLM metrics as legacy; v1 current UNI thesis rules that consume modeled/legacy-mixed metrics now explicitly report insufficient evidence, not Healthy or realized burn. V1 numeric formula signatures, original 42.2% regression and both historical demo snapshots are unchanged. Remaining P0-06 rule cadence and P0-07 replay/publication are not implemented.
- Acceptance evidence: [P0-05 validation](p0-05-validation.md). Full suite: 90 tests; v1 DEMO/RESEARCH validation: 94 metrics, zero issues each.

## Software 0.1.2 / P0-04 temporal selection — 2026-09-26

- Added a separate read-only v2 ledger, strict loader/validator, and `temporal-select` CLI. Queries require economic cutoff, knowledge cutoff, valuation time, scope and explicit system-as-known or public-reconstruction policy; selection filters availability before applying revisions. No provider SDK or data key is required.
- Preserve equal-value evidence leaves, expose unresolved source conflicts, reject malformed/unknown publication times, apply date-only availability at next local midnight with IANA time zone, require source-version and acquisition evidence for system replay, and cap quote age using original venue date. Revision chains remain append-only.
- Updated design contract to `2.0-proposal.2` to specify `as_of_precision` and local quote dates; no v1 formula version, sources, historical observations, scenario or snapshots changed. v2 source/observation ledgers start empty; tests only use synthetic temporary ledgers.
- New regression cases cover original/restated Q1 across two knowledge policies, equal/conflicting sources, unknown times, DST/day boundaries, quote freshness, revision chains, CLI read-only and fixture isolation. v2 financial formulas, thesis cadence and replayable snapshots remain P0-05/06/07.

## P0-03 v2 contract design — 2026-09-26

- Added machine-readable time/scope/record contract proposal, v1/v2 compatibility matrix covering all 30 formula IDs, and ADR-0001 for append-only migration and two knowledge policies. No v2 runtime or source evidence was introduced.
- Defined period, publication precision, first-seen/ingestion, valuation time, role/classification/scope selection and missing-data policies. V1 demo fixtures and two historical snapshots remain unchanged; unknown legacy publication/acquisition times stay null. The next task is P0-04 (time-aware selector); P0-05/06 remain planned.
- Acceptance evidence: [P0-03 validation](p0-03-contract-validation.md). No formulas, market records, thesis rules or derived financial outputs changed.

## Software 0.1.1 / WP-01 — 2026-09-26

- Completed P0-02 and P0-01 in implementation commit `e8b4d55520ea71f1d626a9286fa64a30cd745f3d`; detailed evidence: [WP-01 validation](wp-01-validation.md).
- Added strict YAML parsing, v1 shape/type checks, unique identities, supersession checks and formula-cycle preflight. Errors include stable codes and file/record/field locations; CLI returns exit 1 and HTTP validation returns 422.
- Enforced research fixture isolation before calculation, event ingestion, snapshot creation/save/read and HTTP state/sensitivity. Explicit shared fixture exclusions remain visible; misplaced research rows are rejected even in DEMO. Embedded synthetic evidence and false fixture flags cannot bypass source checks.
- Preserved all equal-value corroborating evidence leaves and propagated fixture status; prevented unsaved sensitivity previews from being saved as canonical snapshots. Added an explicit global CLI `--root` for isolated projects.
- Added 41 tests: all 67 pass. DEMO and RESEARCH each validate 94 metrics with zero issues. Integration tests cover CLI, real loopback HTTP, event and snapshot boundaries, with unchanged-file checks on rejection.
- Financial specs, formula versions/locks, sources, observations, assumptions, scenarios, events, dashboard and both original demo snapshots are unchanged. Repeat demo bootstrap against a temporary copy found the existing snapshots and changed no files. No financial snapshot or live evidence was added.
- Compatibility: aliases/merge keys, unknown schema fields, unquoted dates and loosely typed values that previously slipped through are now rejected. Time/scope v2, mixed-frequency rules, snapshot replay/digest verification and crash/concurrency-safe publication remain planned. Next task: P0-03.

## Development planning v1.0 — 2026-09-25

- Added `docs/planning/`: detailed Chinese roadmap, current-state audit, proposed data/model contracts, edge validation and risk protocol, structured implementation backlog, first work package and primary-source research notes.
- Audited baseline commit `68f19531cfd77bc2c70006921a6402e7a10f04f6`. The existing 26 tests and both validation modes pass; research observations remain empty. Four in-memory probes reproduced fixture-mode isolation, knowledge-time selection, mixed-frequency thesis and duplicate-YAML-key gaps.
- Changed the recommended implementation order: repair the research boundaries (WP-01), then time/scope/replay/publication, then publish a verified research pack. Forecasting, paper evaluation and any authorized capital pilot have separate gates.
- All future functionality is PROPOSED/PLANNED. No runtime implementation, canonical financial data, formula version, assumption, scenario, event, historical snapshot or actual position was changed.
- Planning source notes are leads for future verified ingestion, not new canonical OBSERVED data. No new financial snapshot was created.

## MVP 0.1 — 2026-09-25

- Initialized four-way classification, source policy, units and period matching.
- Locked 30 expression formulas at version 1.0, with a distinct UNI standalone and incremental required-share hurdle.
- Added a **synthetic** four-period demo ledger and two immutable snapshots; changed the DEMO required yield assumption from 3% effective January 2026 to 4% effective April 2026. This is an example assumption revision, not a market update.
- Added uncertainty-preserving calculations, lineage, strict validation, sensitivity, thesis history, validated event observation ingestion/propagation and a local UI.
- No live market data or verified listing status was ingested. All generated financial figures remain fixture examples.

Future changes to formulas, assumptions, scenarios or real source evidence must identify the old/new record IDs, effective dates, rationale and whether a new snapshot was created.
