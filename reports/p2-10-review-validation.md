# P2-10 第六增量：四筆真實收入的具體量測提议

2026-10-02：software **0.1.25**、plan **1.15**；contract proposal.13／compute bundle `.12` 不變。本次是實際研究材料與 append-only 待審提案，沒有新增 runtime、schema 或 synthetic-only admission 功能。P2-10 **IN_PROGRESS**，G1／決策級發布仍 **BLOCKED**。

## 合併與工程基準

[PR #24](https://github.com/yoyoCadence/Tokenized_Capital_Markets/pull/24) head `82233402ae168889eb3c0f0ae68bfe156e6fbb71`，GitHub G0 run `36858360818` SUCCESS、非 Draft／可合併；以 exact head 合併，main `6cf2c0b7e796605fe4fd11d90762c45bcf09838e`。

## 完成的可審閱成果

- 實際查核既有外部原版 Q2 Exhibit 99.1、MD&A、SEC index、July31 S-1。沒有新下載／HTTP receipt，六份唯一原件及十個 captures 保留。
- 新 [decision plan](../research/secz/p2-10-decision-plan.yaml) 追加 14 段 supporting citations，連同原 8 段為 22 段。新增 Q2 年度交叉閱讀／政策延續、停業收入及欄位，S-1 同營運公司年度表頭／auditor 年末／歷史 fiscal year 證據；每段原文 bytes 和 normalized text SHA-256 已核對。
- [人審材料](../research/secz/p2-10-review-decisions.md) 逐項列出四個 raw values、兩種期間、五項 acknowledgement、四份 metadata／original hashes、具體提議與推論邊界。
- Append 新完整 mapping proposal `securitize_inc_revenue_measurement_proposed_20261002`，stage `2026-10-02T04:09:44.574369+00:00`，plan SHA-256 `22a00df6b023dd7089b26b9d81deb78e042da2cf69a8e3a1c1788ba781d1cdb5`。原 incomplete proposal／plan／packet 不改写，也没有指向未發布 observation 的 supersedes_id。
- 提議 USD / AS_REPORTED / CONTINUING / operating Dec31 calendar / GAAP / CONSOLIDATED / ACQUISITION_SCOPE_CHANGE。Q2 Note 2 和營運公司年度美元換算政策提供跨文件 USD 推論，並非 Q2 字面幣別宣告；Apr1／Jan1 是日曆月推導；停業 Revenue 不加入主表。所有 mappings 仍待人審。

## 執行與核對

在 CPython **3.12.14**／PyYAML **6.0.3** 的 pinned G0 環境執行：

```bash
python -m scripts.g0_gate
# Ran 247 tests in 101.387s ... OK
# Validated 94 metrics, 0 issues; mode=DEMO
# Validated 94 metrics, 0 issues; mode=RESEARCH
# g0_engineering=PASS; research_publication=BLOCKED

python -m engine.cli sec-admission-preview --plan research/secz/p2-10-decision-plan.yaml --store-dir /private/artifacts
python -m engine.cli sec-admission-stage --plan research/secz/p2-10-decision-plan.yaml --store-dir /private/artifacts
python -m engine.cli sec-admission-status
# proposals=2, reviews=0, published_records=0, decision_ready=false

git diff --check
```

後兩個命令為已 stage ID 的重試：`created=false`，ledger SHA-256 沒有變化。引用重播需要相同原版外部 store；clone repo 只有 hashes／定位，不是完整 originals 備份。

另外以 strict `read_yaml`／`prepare_sec_admission`／ledger loader 和 base git objects 核對：

| 核對事項 | 實際結果 |
| --- | --- |
| 全部四份 supporting/table/index originals | 完整原件 digest 相符；全部引用重新定位／文字核對 |
| Supporting citations | 22／22，包含新增 14 段，語義狀態全部 PENDING_REVIEW |
| 四筆主表數字及候選期間 | 14,435,845／15,262,176／33,914,311／29,296,195；各欄位／年份／Three/Six Months Ended 綁定一致 |
| 原提案 | 現 ledger 前一筆與 base 完整相等，原 review list 空白不變 |
| Preview 與 stage retry | Preview 不寫 ledger；重試不重複追加 |
| Captures／canonical ledgers／舊 research plans/packets | 對應 base bytes 完全相同；來源／觀察值／事件未入庫 |
| V1 snapshots | 兩份原 hash 分別為 `cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e`／`6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`，保持一致 |
| Runtime／spec／formula locks | 本次無修改；沒有新增金融計算或縮放 |

本次沒有新增 unit tests 來重述相同 implementation；使用既有整合／負向／recovery／scope 測試及實際原件核對，工程通過不替代語義審阅。

## 現在真正尚缺的步驟

兩個 pending proposals 參照同四筆數值，不是八筆獨立 observation；**0 source reviews、0 SEC admission reviews、0 canonical sources／observations／events**。raw packet unit 仍 null；完整 proposed mapping 不會改成 source-approved 或 publishable。

依 [AGENTS.md](../AGENTS.md) 的「All source approvals and five review acknowledgements are required; no reviewer is impersonated.」，下一步需要具名審閱者對 review packet 四份來源與五項量測決議實際接受／保留／拒絕，才能記錄 decision 並使用批次入庫。合併 PR 是工程授權，不能據此替使用者產生金融審阅紀錄。

SEC index 的 filing date 為 2026-08-13，timezone 未知；即使後續來源／入庫審閱通過，仍不符合 historical temporal selection。未知時區、上市 issuer bridge、UNI realized receipt／burn、XLM economics 與 G1 缺口分別保留。待此收入材料獲審後可完成 canonical admission；獨立治理 receipt 研究可先推進。
