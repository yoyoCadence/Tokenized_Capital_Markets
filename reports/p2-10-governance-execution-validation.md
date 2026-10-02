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
- Full G0: **PASS**, 256 tests; DEMO and RESEARCH each validate 94 metrics with zero issues in pinned CPython 3.12.14 / PyYAML 6.0.3. Research publication stays **BLOCKED**. New CLI guards also reject malformed external objects and overflowing block timestamps without a traceback.
- Strict YAML: 61 files; local Markdown links: 84; `git diff --check`: PASS; actual packet equals two independent offline executions. New evidence is unreviewed. Canonical v2 financial/event ledgers, SEC candidate values and proposal versions, old captures, UNI period/governance notes and both v1 snapshot hashes are preserved against the main parent.
- This standalone audit adds no engine schema/runtime, financial formula, canonical decoder or snapshot archive change. Bundle `.12` and contract proposal.13 remain; the new packet carries its own checker SHA-256 and needs the external store for replay.

## Gate and next work

G0 is engineering acceptance; G1/decision-ready publication remains **BLOCKED**. Next is actual source/measurement acceptance against the prepared SEC packet and UNI contract/source review, complete receipt/finality and full 2026-Q1 coverage. An official executed proposal plus matched logs does not establish quarterly holder economics, current pool state, totalSupply reduction or USD value.
