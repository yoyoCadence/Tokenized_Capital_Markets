# Implementation plan

1. Use Python 3.11+, PyYAML and the standard library. Canonical YAML and an append-only observation ledger feed a pure calculation and validation engine. A local HTTP server exposes its outputs to a dependency-free dashboard.
2. Define metric units, classifications, formulas and versions in `spec/`. Keep market evidence, scenario inputs, event records and immutable snapshots in separate files. The initial runnable data pack is synthetic and prominently marked DEMO; the research pack remains empty until a primary source is checked.
3. Evaluate formula dependencies in topological order, attach transitive lineage to every result, reject ambiguous/conflicting observations, and validate dates, periods, bounds and source references. Recompute all downstream results for sensitivity overrides.
4. Persist content-addressed snapshots without overwriting history; compare versions by input, source, assumption, scenario and formula changes. Evaluate thesis rules against fresh historical periods, keeping every triggered rule and the most severe state.
5. Provide a local dashboard, a CLI, deterministic regression fixtures, unit and integration tests, agent rules, methodology, change log and a scoped backlog.

Runtime entry point: `python -m engine.cli serve --demo` (explicit demo mode). No API key, database, npm or AI SDK is needed. Python package requirement: `PyYAML>=6,<7`.
