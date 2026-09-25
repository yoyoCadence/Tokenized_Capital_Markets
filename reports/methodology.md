# Methodology and evidence contract

The fundamental path is source → dated observation → dictionary → versioned expression → derived result with transitive lineage → economic capture test → reverse hurdle → sensitivity → thesis monitoring → immutable version → UI. Derived metrics store both direct input IDs and the full set of leaf records; the inspector exposes both. A source can be superseded but never quietly removed. Freshness is per observation, not inferred from when the UI was opened.

## Models

**UNI.** Synthetic annual protocol accrual equals crypto fees + modeled tokenized equity protocol revenue + separately labeled other protocol accrual. Modeled equity protocol revenue = hypothetical equity TAM × tokenization penetration × turnover × onchain × AMM × Uniswap shares × fee in basis points / 10,000. Net holder accrual deducts UNI growth distribution valued at spot token price and other dilution. Yield divides by current market cap. The standalone required share reproduces the stipulated `(required accrual + growth distribution) / equity fee opportunity`. The incremental hurdle adjusts for existing other accrual and other dilution. These are assumptions about the capture chain, not verified flows. If actual tokens were funded from treasury or burn mechanics differ, the convention must be revised with evidence and a new formula version.

**SECZ.** Add six separately observed TTM revenue lines; compare to a matching prior TTM. Growth and operating leverage require consistent accounting periods. Required FCF = enterprise value / terminal FCF multiple; required revenue = FCF / assumed FCF margin; CAGR uses the assumed horizon. If margins or time horizon are uncertain, explore sensitivity rather than claiming a single fair value. Whether `SECZ` is directly investable remains unverified.

**XLM.** Network RWA, stablecoins, transfers and operations describe adoption. Native reserve, liquidity, collateral, settlement and other locked XLM describe possible token demand. Growth of total locked XLM relative to transfer activity growth is a descriptive capture ratio; it does not price XLM. Network fee value is shown in USD only as a diagnostic. A DTCC infrastructure relationship can become LIVE without proving XLM economic transmission.

## Time, uncertainty and provenance

Financial flow observations are TTM; stocks are SPOT. Comparable growth pairs must have matching basis, period length and year-over-year endpoints. Every thesis rule counts **consecutive quarter-end samples** and requires observation leaves fresh at each sample. Incomplete history yields an unknown state unless a rule is demonstrably triggered; all triggered rules remain visible and the most severe state wins. Initial thresholds are analyst assumptions, as recorded in `spec/thesis-rules.yaml`.

Source levels 1–5 follow `spec/source-registry.yaml`. Synthetic records use FIXTURE outside the real hierarchy. The demo pack has four quarter-end sets of wholly invented observations; its $4T scenario, 1.25 bp fee, $242M required UNI accrual and $180M distribution reproduce the 42.2% required-share regression. No fixture number is a market assertion.

`source_ids`, observation IDs, formula signatures, revisions and as-of dates travel with the snapshot. A content hash is its identity. Old snapshot files are never overwritten; mutation of a previously recorded input/source ID is rejected when a new snapshot is saved. Sensitivity overrides are transient SCENARIO leaves and never modify the canonical files.

The event command validates new sourced observations as a batch, appends their fresh IDs to the ledger, recalculates economics and thesis states, traverses graph dependencies separately from economic transmission, writes a snapshot and adds a changelog entry. Planned/announced events cannot ingest live numeric observations. Multi-file crash recovery remains a future reliability improvement.
