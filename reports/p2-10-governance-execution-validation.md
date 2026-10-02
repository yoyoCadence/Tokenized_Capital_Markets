# P2-10 seventh increment — real governance execution validation

Date: 2026-10-02. Software 0.1.26; planning 1.16. PR #25 merged at exact head `5e22697fe2ac2b2e27f163079136a3626cdf1b37`, G0 run `36964157648` SUCCESS, main merge commit `3ba3adba838a6b99182b0ced0713bd5fa9c46047`. P2-10 remains **IN_PROGRESS**.

## Scope and research result

Six actual JSON responses (95,905 bytes total) were added using existing MANUAL_FILE_V1 capture. No network API transaction, wallet signature, reviewer approval or canonical admission was made. Existing ten capture rows and SEC plans/proposals remain unchanged; total twelve unique originals / sixteen captures, zero reviews/sources/observations/events.

[Original-linked findings and review limits](../research/uni/p2-10-execution-review.md), [seven-role plan](../research/uni/p2-10-execution-plan.yaml) and [saved packet](../research/uni/p2-10-execution-packet.yaml): exact transaction/block relationship, 15 matching raw logs, ProposalExecuted(93), eight ordered calldata/target matches, 100M treasury transfer to dead and distinct 40M vesting allowance. The RPC block and indexer agree on December 27 UTC; the portal is 96,972 seconds later. Full receipts and historical state remain unavailable. Quantitative quarterly economics stay null and the December action is outside 2026-Q1.

## Reproduction

```bash
python -m scripts.verify_uni_execution --plan research/uni/p2-10-execution-plan.yaml --store-dir /private/artifacts
python -m unittest tests.integration.test_uni_execution_audit -q
python -m scripts.g0_gate
git diff --check
```

The external store must contain the digest-named originals. The read-only audit verifies their exact size/hash and provider/kind identity before parsing, retains every capture's actual first-seen, and reports null ingestion plus false financial_publication/canonical_admission/decision_ready. Repeat execution must equal the saved packet and modify no ledger.

## Engineering acceptance

- Nine offline integration tests exercise wrong chain, transaction, governor, selector, block inventory and portal block; duplicate/removed/missing/foreign logs; raw provider disagreement; jointly agreed bad ABI/recipient/amount/proposal events; changed/ambiguous portal actions; positive/failed/incomplete receipt responses; duplicate JSON keys/nonfinite/bool IDs/invalid UTF-8; inert source instructions; unknown plan fields; missing/tampered originals; incomplete indexer pagination; safe CLI errors and no publication.
- Initial local G0: **PASS**, 256 tests; DEMO and RESEARCH each validate 94 metrics with zero issues in pinned CPython 3.12.14 / PyYAML 6.0.3. Research publication stays **BLOCKED**. New CLI guards also reject malformed external objects and overflowing block timestamps without a traceback.
- Strict YAML: 61 files; local Markdown links: 84; `git diff --check`: PASS; actual packet equals two independent offline executions. New evidence is unreviewed. Canonical v2 financial/event ledgers, SEC candidate values and proposal versions, old captures, UNI period/governance notes and both v1 snapshot hashes are preserved against the main parent.
- The standalone audit adds no financial schema/formula or canonical decoder. The CI follow-up below optimizes engine source validation only; bundle format `.12` and contract proposal.13 remain. New compute bundles freeze the optimized engine bytes in their existing content-addressed archive; prior snapshots remain unchanged. The standalone packet carries its own checker SHA-256 and needs the external store plus this repository version for replay.

## Remote CI timeout and validation cost

First GitHub run `36970333952` at head `a1892af985986aaddb22d55fd763d9c8b6093494` failed: G0's unittest subprocess exceeded its existing 180-second timeout. This run is not an accepted gate. Local full execution took 123.228 seconds. A profile identified sixteen repeated strict reads of the same metric-concepts dictionary in one source ledger validation; each added capture increased this cost throughout source/admission tests.

Reuse one strict dictionary read **within each ledger validation**, still validate every capture, and re-read the dictionary on every later invocation. No process/global cache or timeout change. A regression verifies the one read and rejects formerly valid coverage after the dictionary changes. Profiled `_ledger` reads fall from 32 to 17; the same local sample falls from 0.655 to 0.270 seconds (profiling samples, not a timing assertion).

Final local G0 after optimization: **PASS, 257 tests in 96.773 seconds**, DEMO/RESEARCH each 94 metrics / zero issues; publication remains BLOCKED. The actual seven-source packet is unchanged and still replays exactly. The updated PR head must also pass GitHub CI before merge; the first failed run remains visible.

## Gate and next work

G0 is engineering acceptance; G1/decision-ready publication remains **BLOCKED**. Next is actual source/measurement acceptance against the prepared SEC packet and UNI contract/source review, complete receipt/finality and full 2026-Q1 coverage. An official executed proposal plus matched logs does not establish quarterly holder economics, current pool state, totalSupply reduction or USD value.
