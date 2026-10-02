# UNI proposal 93 — real execution evidence, pending review

Checked 2026-10-02. This appends evidence to the historical [P1-05 governance note](p1-05-governance.yaml); that note and the [incomplete 2026-Q1 period](p1-05-period.yaml) remain unchanged. [Audit plan](p2-10-execution-plan.yaml) / [reproducible packet](p2-10-execution-packet.yaml) / [engineering validation](../../reports/p2-10-governance-execution-validation.md).

## Principle

Official proposal text, provider execution assertions and financial admission are separate. All seven referenced captures remain unreviewed. No source reviewer, accounting acceptance, canonical observation or event is created.

## Logic and original evidence

The archived [official proposal](https://vote.uniswapfoundation.org/proposals/93) contains the expanded proposal object in serialized Next.js Flight JSON. Parse it as inert JSON; do not execute scripts. Extract its transaction hash, explicit block number and eight action arrays. Match those against mainnet RPC transaction, block and raw log responses and a separate Blockscout indexer. Artifact versions and provider endpoints are pinned in the plan.

| Field | Actual archived result |
| --- | --- |
| Transaction | `0x091f0083242a777d55821c1189e568d6d033d9da501b75087dc736fa143d2c1e` |
| Block / hash | 24,106,378 / `0xdffacec5530523a39bbb539d65518cdcb754b67369477767586f1ad66d596f14` |
| RPC block timestamp; indexer agrees | 2025-12-27 20:33:11 UTC |
| Portal literal `$D` execution timestamp | 2025-12-28 23:29:23 UTC |
| Retained timestamp conflict | Portal later by 96,972 seconds = 26h 56m 12s; both already UTC |
| Raw logs | 15, indices 9–23; address/topics/data/transaction/block match independently retrieved indexer items |
| Governance event | Governor `ProposalExecuted(93)`, log 23 |
| Receipts | PublicNode returned null twice; Flashbots returned null once |

RPC `eth_getLogs` request pins the exact block hash and five emitters (Governor, timelock, UNI, v3 factory, EAS). The indexer transaction logs endpoint returns 15 items with `next_page_params: null`; its full returned log set equals the RPC set. This is provider corroboration, not a receipt-trie or consensus/finality proof. Null receipts do not establish pending, failed or absent execution when the transaction and logs are independently returned.

| Ordered timelock log | Matched raw proposal action |
| --- | --- |
| 10 | EAS indemnification attestation |
| 12 | UNI `transfer(dead, 100M UNI)` |
| 14 | v3 factory `setOwner(fee adapter)` |
| 15 | v2 setter `setFeeToSetter(timelock)` |
| 16 | v2 factory `setFeeTo(TokenJar)` |
| 18 | UNI `approve(vesting, 40M UNI)` |
| 20 | EAS services agreement attestation |
| 22 | EAS second indemnification attestation |

The eight target addresses and calldata bytes match exactly in order. Values and signature strings are zero/empty; dynamically encoded calldata bounds/padding and the common ETA are checked. Matching calls do not verify every pool's subsequent fee state or EAS legal validity.

## Example: separate quantities and periods

UNI log 11 is a Transfer from timelock `0x1a9c8182c09f50c8318d769245bea52c32be35bc` to `0x000000000000000000000000000000000000dead`, raw `100000000000000000000000000`. Log 17 is an Approval from the same owner to vesting `0xca046a83edb78f74ae338bb5a291bf6fdac9e1d2`, raw `40000000000000000000000000`. Each is checked against its corresponding calldata recipient and amount. The existing UNI identity's 18 decimals yield audit display quantities of 100M and 40M; these display conversions are DERIVED and are not canonical observed records or formula outputs.

The 100M transfer is a one-time treasury action in December 2025, outside the proposed January–March 2026 research period. Calling a transfer to dead a treasury burn does not prove ERC-20 totalSupply fell; actual before/after totalSupply is unknown. The 40M approval is spending authority, not proof of 40M transferred or vested. Actual vesting distributions, recurring fee-funded burn and USD value remain null.

## Action and unresolved review

1. Review the seven original versions, provider/source classifications, rights and contract identities/ABI. Source dates on new transaction/block/log captures are explicitly **block context dates**, not original API publication times; the null-receipt capture has no source date. Manual capture clocks are actual October 2 archive times; no HTTP receipt or historical first-seen is invented. The old portal source date stays null.
2. Obtain a full matching transaction receipt from another archival provider and address finality/receipt inclusion. A positive receipt requires a new audit version with explicit status checks; this 1.0 contract deliberately rejects changed receipt availability.
3. Retain and resolve the portal timestamp conflict against primary chain evidence. Do not overwrite the old portal or rewrite system history.
4. Retrieve historical UNI contract identity/state and actual vesting transfers. The attempted historical `eth_call` batch returned HTTP 403, leaving no original state response; decimals come from the existing identity master, not newly verified historical state. Other unavailable retrievals (Etherscan 403, Llama RPC POST 405) add no proof.
5. Complete P1-05's 2026-Q1 block bounds, pool inventory, logs, balances and fee/burn/distribution reconciliation before quarterly financial admission. The publisher-reported January 5 tranche remains a lead, not an independently verified transfer.

Replaying requires the seven original digest-named files in an external artifact store. Originals are absent from git. The standalone packet pins the checker SHA-256; it is not an engine bundle or a financial snapshot. G1 and decision-ready publication remain BLOCKED.
