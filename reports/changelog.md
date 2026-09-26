# Research/software changelog

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
