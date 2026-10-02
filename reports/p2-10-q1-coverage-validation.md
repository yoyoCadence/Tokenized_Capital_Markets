# P2-10 第九增量驗收：2026Q1 UNIVesting 查詢範圍

PR #27 exact head `66b666bab8538cc3567006a76db7c25570e0e7de` 的 G0 `37001239255` SUCCESS（267 tests、187.910 秒）後，使用 expected-head guard 合併至 main `5f4ff76224091a16b8b7b311d9bc8ebd6c478e4e`。Merge tree `9cf84e46cf0a38b300cb81ade06ba309c1a7f256` 與已測 PR tree 相同，此增量由該 main 開始。

六份真實 RPC request/response envelopes 以既有 MANUAL_FILE_V1 追加：兩家 Q1 相鄰邊界、MEV 兩次 partial-success acquisitions、Tenderly full/split success、Blast range-limit diagnostics。共 27 unique originals／31 captures；前 25 captures 逐值不變、real reviews 0。API clocks 與實際 archive clocks 分開，source_date=null；無原文公開或 financial admission。

[新唯讀 helper](../scripts/verify_uni_q1_coverage.py) 先重播原版 receipt／execution audit與 staging 全量 preflight，再核對：digest/source/provider/kind、mainnet、精確 RPC request／response IDs、closed-quarter acquisition、UTC 邊界／相鄰 hashlinks、完整無缺口／無重疊三段、full 與 split union、所有同 provider 成功重查及另一家 inventory、ABI 與已驗證 receipt 的 tx/block/log identity。MEV 的失敗仍未知；成功來源由 manifest 明確選取。Blast 10-block range errors 只作診斷，不計為零。

指定 UNIVesting + Withdrawn topic 的 Q1 blocks 24,136,053–24,781,026／644,974 blocks，兩家 full 與三段 `[1,0,0]` 相符，唯一 Jan5 event 與前版 receipts 相符。selected-contract DERIVED sum=5M UNI；**全球 UNI 全季分配、fee burn／supply／holder USD 仍 null**。沒有 provider omission／cryptographic absence、歷史配置、finality ancestry 或 trie proof。

[十個新測試](../tests/integration/test_uni_q1_coverage.py) 全部只用 disposable synthetic ledgers：

- 唯讀與雙重 replay；失敗 count=null，selected sum 與全 UNI 未知分開。
- UTC off-by-one、錯 parent／block／chain；segment gap／overlap／end missing／bool。
- 明確成功選取不可指向 failed／foreign／wrong ID／missing response；成功 retries、full/split 或 provider 不一致拒絕。
- 雙家同時漏掉 receipt 或改 amount／recipient／uint48／timestamp 仍拒絕；removed／duplicate／foreign／out-of-range logs。
- 錯 filter／clock／bool／digest、prior plan pin、缺原文／tampered bytes、duplicate YAML／JSON、NaN／missing fields；CLI 非零且無 traceback、檔案不變。

新 packet 雙重 replay 相同；原 governance／receipt plans 和 packets、canonical ledgers、SEC proposals 及兩份 v1 snapshots fingerprints 與 base 相同。原 `p1-05-period.yaml` 也保持不變。新 helper separately hash-pinned；engine runtime／canonical formula locks／schema／contract proposal.13／bundle .12 不變。

本機完整 G0 PASS：277 tests，143.065 秒；CPython 3.12.14／PyYAML 6.0.3 鎖定；DEMO／RESEARCH 各 94 metrics、0 issues。strict YAML／本地 Markdown links／git diff check 通過。保留 300 秒單一 subprocess 與 workflow 10 分鐘上限。research_publication=BLOCKED，遠端 exact-head CI 另行核對。P2-10 IN_PROGRESS，P1-05／G1 BLOCKED；下一步為來源／金融語義具名接受與完整 UNI distribution universe 查核。
