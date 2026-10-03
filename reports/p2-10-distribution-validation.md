# P2-10 第十增量：UNI 分配全集規劃驗收

PR #28 exact head `5310571f65a79499a03bbccc8d87b7c13fa32e3a` 的 G0 `37004994192` SUCCESS、可合併、無 reviews／review threads。以 expected-head guard 合併 main `6ddb78561c4a3a7a0c38be46491ae2e9543eff3b`，merge tree 與該 head tree `4102d42c174cd3b6f1b695c2c3165d75b153dfd2` 一致。本增量由此主線開始。

## 工程交付與可驗證範圍

- 新 [strict plan](../research/uni/p2-10-distribution-plan.yaml)、[只讀 helper](../scripts/plan_uni_distribution.py)、[scope／取證與去重待辦](../research/uni/p2-10-distribution-review.md)。六 lane 全部必須存在，控制帳戶全集 OPEN；first-exit policy 保持 ASSUMPTION，不是修改 canonical 金融概念。
- 驗證舊三份 plan/packets digest、checker pins、staging manifest／取得時點、單一 withdrawal 與 treasury transfer 的原 packet context。無 originals 時明確 metadata-only；提供 store 才重播 prior Q1 helper，缺原版或 packet 不一致拒絕。
- 兩 providers、五個 UNI Transfer filter families、65 個相鄰分段與 full window、670 個 bounded deterministic requests。Budget 超限拒絕整個 plan，沒有 partial-success 宣稱，也沒有 network 或 provider key。
- 舊 5M 子集保持 DERIVED / FROZEN_UNREVIEWED_PACKET、語義待審；不稱季度總數／下界。Transfer 167 與 Withdrawn 168 只描述同一 movement，Approval 166 不作支出。全球／供給／USD 全部 null。

`requests_sha256=bb2abe0706c18d97fe115c26a2e11c76e5d861290f8558893f14ce831510b9dd`；`plan_sha256=e90a51fb7d85df88bee044968c64ff40397695f0c937a7d1d14e7125cd3c98e7`。Helper 自行输出 SHA-256；不是 engine compute bundle 中新增的 runtime。舊 helpers 未修改，因此舊 packets pins 仍有效。重複執行結果相同且無 evidence mutation。

## 測試

[14 個新 integration/negative tests](../tests/integration/test_uni_distribution_plan.py)：只使用 disposable metadata copies，不取得新鏈上資料。原版 replay 邊界的 match/mismatch 使用明示 mock；真實原始 byte 檢查沿用既有 Q1／receipt／execution suites，**不將 mock 算成新的真實原文 replay**。

涵蓋 deterministic／readonly／no-network、完整無 gap/overlap 分段、indexed sender/receiver filters、summary digest、日期/block/chain/bool 錯誤、lane 缺漏／重複／假 completed、scope/classification/fixture/closed roots、query budget/provider 上限、reference digest/path/checker、staging 改值、重新 hash 的 fake economics／movement、duplicate YAML／size bound、缺 originals 不 fallback、CLI 非零且無 traceback。

14 tests PASS。本機完整 G0 PASS：**291 tests，143.106 秒**；CPython 3.12.14／PyYAML 6.0.3 鎖定；DEMO／RESEARCH 各 94 metrics、0 issues。66 份 strict YAML 通過，protected paths 與 base 無 diff，兩份 v1 snapshot SHA-256 不變。`research_publication=BLOCKED`。遠端 exact-head CI 於 PR 核對，不在此宣稱已通過。

## 證據與未完成範圍

沒有新增 originals／captures，仍 **27 unique originals／31 captures、0 source reviews／canonical sources／observations／events**；兩個 SEC proposals 引用同四筆收入，五項量測決議仍未接受。前版 packets／period、v1 snapshots、canonical schema/formulas／engine／contract proposal.13／bundle .12 不變。

此次是真正的查詢規劃／fail-closed engineering increment，**不是補齊全季 evidence**。未發送 670 requests、未實作新 response importer／transfer aggregation、未審閱帳戶控制或金融語義，沒有 finality／provider absence proof／USD price policy。今日官方网页只是 research leads，沒有 source approval。P2-10 IN_PROGRESS，P1-05／G1 BLOCKED；下一包為實際 immutable acquisitions 與 full/split/provider 對帳。
