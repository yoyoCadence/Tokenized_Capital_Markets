# Permanent project instructions for every research/coding agent

Read `spec/` and this file before editing calculations, evidence or UI. A UI display is never the source of financial truth.

## Planning versus implemented behavior

Read `docs/planning/README.md`, `docs/planning/CURRENT_STATE_AUDIT.md` and the relevant work package before continuing this project. The planning directory records proposed work; it does not replace canonical specs or assert that future fields, APIs or safeguards already exist.

- Use `docs/planning/IMPLEMENTATION_BACKLOG.yaml` for task dependencies and acceptance evidence. WP-01 and P0-03/P0-04 are complete; read their validation reports and `docs/planning/ADR-0001-V2-TIME-SCOPE-MIGRATION.md`. The next task is P0-05, scope-aware calculation. The v2 temporal selector is a separate read-only route; v1 financial calculation/snapshots remain legacy and have no point-in-time guarantee.
- A task becomes DONE only with its implementation/research evidence, tests or reconciliation, commit and changelog. Keep discovered defects visible until fixed.
- Planning source notes are not canonical observations. Verify, archive, classify and review evidence before research publication; do not promote an official proposal into realized economics.
- Preserve v1 snapshots and fixture regressions during any v2 migration. Never invent historical publication or first-seen timestamps.
- For v2 historical queries explicitly specify economic cutoff, knowledge cutoff, valuation time, scope and either system-as-known or public reconstruction. Validate all v2 files with the strict loader; filter evidence by knowledge time before supersession. Never feed legacy v1 records with missing times into a historical selection or pretend a public reconstruction was an actual earlier system decision.
- Calculation correctness, forecast quality and profitable execution require separate evidence. Thesis states remain research states. Future capital use requires the user's concrete investment policy and authorization; this plan authorizes no trading.

## Canonical principles

1. TAM is not asset value. Protocol adoption is not holder value. Business growth is not automatically equity or token capture.
2. Market price/capitalization/enterprise value is an input to **reverse underwriting**, never evidence that a thesis is true.
3. Maintain OBSERVED, DERIVED, ASSUMPTION and SCENARIO as distinct classifications through every storage, calculation, chart and export. Synthetic fixtures must also carry `fixture: true`.
4. Every derived result needs a formula ID, version, dependencies and transitive lineage through every input to any observed source. Unknown data remains null.
5. Store every observation's source ID, unit, period basis and as-of date. Never edit or delete an old observation, assumption, scenario, source or snapshot; append a new ID and `supersedes_id` where applicable.
6. Change a formula's version, signature lock and `reports/changelog.md` entry together. Do not reuse the previous version after changing an expression.
7. A planned or announced event remains planned or announced until **new evidence** supports a valid transition. Acquisitions require sourced completion evidence; a press release alone is not completion.
8. Do not infer UNI value from turnover without protocol fees, burn and growth distribution. Do not infer XLM demand from Stellar/DTCC use without a documented economic mechanism. Do not value SECZ from AUM alone.
9. Keep the open universe open. Promote an asset to CORE only after primary source verification, mapped value capture, investability check and workable reverse underwriting. A marketing label is not evidence.

## Source policy

Prefer Tier 1 filings, regulators, exchanges, audited accounts, DTCC and onchain contracts. Tier 2 is official investor/governance/industry data; Tier 3 is major reporting; Tier 4 is aggregators; Tier 5 is social, blogs and crypto media. Tier 5 cannot be the sole support for a core observation. Keep conflicting sources and block ambiguous selection. A source record requires URL, publisher, title, source date, retrieval timestamp, tier and covered metrics. `FIXTURE` is a separate synthetic provenance, never a source tier for actual financial evidence.

## Validation and versioning gates

- Run `python -m engine.cli validate --demo` and `python -m unittest discover -s tests -p 'test_*.py'` after code/spec changes. Run `python -m engine.cli validate` for research mode.
- Reject schema, classification, unit, source, date, period, formula-lock and lineage errors; do not silently coerce bad inputs. Division by zero is an error; required UNI share above 100% is a warning.
- Use the strict loader and shared project validation before calculation, ingestion or publication. Do not bypass them with `yaml.safe_load` or ad hoc dictionary conversion. YAML duplicate keys, aliases, merges, nonfinite numbers, unknown fields and incorrect types are errors; v2 fields require an explicit contract migration.
- Reject fixtures misplaced in research ledgers, including when running DEMO. Shared fixture assumptions/scenarios/edges may be explicitly excluded by the recorded loading policy; unused fixture sources may remain. Never silently drop polluted research rows. Preserve all corroborating evidence leaves and propagate any fixture dependency.
- Snapshot only after validation. Content-addressed snapshots are write-once; compare prior vs current and report whether an observation, source, assumption, scenario or formula changed. Do not save a sensitivity override as research evidence.
- Event propagation must distinguish graph dependencies from economic-transmission hypotheses. Thesis states are HEALTHY, WATCH, STRESS, BREAK_CANDIDATE, INVALIDATED; incomplete evidence yields an *unknown* display, never a fabricated state. These are not recommendations.
- Before admitting a new observed number, verify the original primary source and accounting period. If there is no trustworthy source, leave the field unknown and open a research task.

## Research refresh procedure

Append a new source/version record; append observation rows with the real as-of and reporting period; validate; inspect conflicts and lineage; recalculate; run tests; write a snapshot; compare; document changed assumptions/formulas/events in `reports/changelog.md`. Do not treat the synthetic `--demo` pack as a live baseline.
