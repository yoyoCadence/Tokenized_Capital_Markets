# P2-10 第八增量驗收：完整 receipt 與第一笔实际 vesting

PR #26 最新 head `ec16b137f27d5b31f3fd01cf97e018dbd3ddd7c1` 的 G0 `36971227592` SUCCESS 後合併到 main `032e073121803f35f5a4a6efc6aa07d97a6966bd`，確認 merge tree 與已測 PR tree 一致，再開始此增量。

九份新原文以既有 MANUAL_FILE_V1 追加：兩家 positive receipt envelopes、PublicNode Jan5 transaction/block envelope、indexer Jan5 transaction/log envelopes、indexer contract/source context、兩份 pinned official Solidity files 與 DUNI report HTML。共 21 unique originals／25 captures，0 real reviews；前十六筆 captures 和舊治理／SEC proposals 不變。

[新唯讀 helper](../scripts/verify_uni_receipts.py) 嚴格核對 digest、source role／URL／kind、request／response context、clocks、mainnet identity、完整標準成功 receipts／gas／bloom shape、全部 raw logs、indexer pagination 與 ABI。兩家治理 receipts 的 15 logs 相同，且與上一增量原版 logs 相同；原 checker 繼續驗證八個 timelock calls。Jan5 的 Approval／Transfer／Withdrawn 三筆 raw logs 一致；5M raw transfer 和 quartersPaid=1 可重播。這是 payload consistency，不是 trie proof／finality ancestry。

[十個新負例／整合測試](../tests/integration/test_uni_receipt_audit.py) 使用 disposable synthetic ledgers：

- 唯讀、兩次 replay 相同；caller／recipient、一次轉帳／全季度、舊 null／新 positive 證據分開。
- 錯鏈、failed／null receipt、tx／block／from／to／index／type／selector／value／period 關係；錯 block inventory。
- 缺漏、removed、duplicate、reordered、跨 provider 和舊治理 raw logs 不一致；indexer 分頁未完。
- 即使兩家 provider 与 indexer 同時一致，錯 event topic、Transfer／Withdrawn 金額／recipient、ABI padding／uint48 溢位仍拒絕。
- request hash／method／ID／bool 參數、response digest、source clock／endpoint、原文變更、duplicate JSON／YAML keys、NaN、錯 UTF-8、來源／interface／ABI／constructor 不一致。
- decoded instructions 保持 inert；缺欄位與 malformed 原文的 CLI 回非零、安全 error，無 traceback，拒絕前後檔案相同。

原版 governance plan／packet 逐值 replay 相同，新版 packet 重跑兩次相同。canonical source／observation／event、SEC proposal ledger、兩份原 v1 snapshots 的 hashes 與 base 保持相同。所有資料是 PENDING_REVIEW；沒有 financial publication、source approval、human review 或 canonical admission。

本版僅新增 separately hash-pinned audit helper 與研究原文；engine runtime、formula locks、canonical schema、contract proposal.13、bundle .12 均不變。clone repo 仍需原版 checkout 外 artifact store 才能驗證原文；缺失或變更會拒絕。

G0 在鎖定 CPython 3.12.14／PyYAML 6.0.3 完整通過：267 tests，118.973 秒；DEMO／RESEARCH 各 94 metrics、0 issues。`g0_engineering=PASS`，`research_publication=BLOCKED`。strict YAML、Markdown local links 與 `git diff --check` 通過。P2-10 IN_PROGRESS；P1-05／G1 研究發布仍 BLOCKED。下一步為 real source／semantic acceptance、finality ancestry、Q1 完整 UNI coverage、supply／USD basis，而非把本次 5M 轉帳當成全季總量。

遠端第一個 run `37000361200` 在 G0 unittest subprocess 的 180 秒硬上限觸發 TimeoutExpired。此非成功驗收，失敗記錄保留。將 G0 的單一子程序有界預算改為 300 秒，保留全部 tests、兩種 validation、鎖定環境與非零退出，並明設 workflow 10 分鐘外層上限；不跳過斷言，也不改 engine runtime。修正後本機完整重跑：267 tests，118.142 秒；DEMO／RESEARCH 各 94 metrics、0 issues，G0 PASS／research BLOCKED。最新遠端 head CI 另行核對，不能沿用原失敗 run。
