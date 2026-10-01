# P2-10 第三增量：真實 SEC 表格與多來源審閱包

日期：2026-10-01。軟體 0.1.22，plan 1.12，contract proposal.11，bundle `.10`。P2-10 **IN_PROGRESS**；完成真實數字的表格／索引關聯和可重現審閱包，未完成正式財務觀測值發布。

## 合併基準

[PR #21](https://github.com/yoyoCadence/Tokenized_Capital_Markets/pull/21) exact head `98ae4fbb48e16d161819985127bdd7d0a35a1da2`：GitHub G0 run `36841706220` SUCCESS、非 Draft、可合併、無 review，合併為 main `37e96d011002563920cd95fc4ad813ff011821a6`。本增量從此 main 建立。

## 實際完成

- `sec-table-preview` 離線讀取 strict plan／policy 和兩份 digest-verified 原文，生成 **PENDING_REVIEW** packet，不寫 canonical ledger，不核准來源、不回填 ingestion，不執行網頁 script。候選不是可直接送入 v2 的 records。
- Explicit entity／statement／完整 table byte spans 限定營運公司損益表；展開 colspans 後，Revenue row 的數字、相鄰 `$`、年份欄與 Three／Six Months Ended 欄都綁到實際 logical column。重複字面數字不再靠「第一個找到」選值。rowspan、nested／irregular table 和 ambiguous mapping fail closed；不宣稱支援任意 HTML/CSS 的視覺語義。
- 新下載 SEC 官方索引原文 `secz_filing_index_20260813_20261001`，HTTP 200、10,979 bytes，SHA-256 `5ffd7893b144a5561073ad15dae18ab3e20f2944708e3921fe102faee5b446d9`。索引與 Exhibit 99.1 的 URL 必須是同 accession `0001628280-26-056811`，原表 EX-99.1 link 須精確指向該原文。
- Publication 取索引的 **Filing Date = 2026-08-13**，不是 Period of Report = 2026-07-08，也不是 parent signature date。Accepted 顯示的時間沒有本原文時區證據，不推定其精確可用時點；timezone null／historical availability UNKNOWN。

## 真實審閱候選

資料：`research/secz/p2-10-table-plan.yaml`、`research/secz/p2-10-table-packet.yaml`。原版 artifact store 配合下列命令，已重現與保存 packet 完全相同的結果：

```bash
python -m engine.cli sec-table-preview --plan research/secz/p2-10-table-plan.yaml --store-dir /private/artifacts
```

| 原表期間欄 | Logical value column | 原文數值（幣別未核准） | 待審日曆期間 |
| --- | ---: | ---: | --- |
| Three Months / 2026 | 4 | 14,435,845 | 2026-04-01～2026-06-30 |
| Three Months / 2025 | 10 | 15,262,176 | 2025-04-01～2025-06-30 |
| Six Months / 2026 | 16 | 33,914,311 | 2026-01-01～2026-06-30 |
| Six Months / 2025 | 22 | 29,296,195 | 2025-01-01～2025-06-30 |

四筆都標 OBSERVED／REALIZED 的**原文擷取候選**、reporting entity `securitize_inc`／OPERATING_COMPANY，**unit=null、publishable=false**。日期起点是明示的 `CALENDAR_MONTH_DURATION_PENDING_REVIEW_V1` 日曆推導，不是原文含有該日期的假引用；fiscal calendar 未核准，不指派上市 SECZ issuer role。`$` 不能單獨證明 USD。會計量測口徑、幣別、期間規則和 source rights 尚待審；不計算估值或將 GAAP 當貨幣證據。

兩份 source 的實際 acquisition 都保留；packet `first_seen_at` 取這次索引與財報的較晚實際 retrieval，`ingested_at=null`。現在有 **4 unreviewed captures、0 source reviews、0 canonical sources/observations/events/refresh proposals/reviews**，決策級研究發布仍 BLOCKED。

## 驗證

- 13 個新 integration tests 使用 disposable synthetic originals：colspan／year／duration／currency／value binding，跨原文 publication link，duplicated scalar／index／row、錯 accession/entity/headers、錯 symbol/scale、假 citation／artifact tamper、rowspan/nesting/irregular width、過遠 heading、future/non-month-end/non-YTD period、unknown/duplicate YAML、unit policy override、script rejection、CLI/read-only/reproduction 和 canonical admission boundary。
- 固定 CPython 3.12.14／PyYAML 6.0.3：`python -m scripts.g0_gate` **236 tests OK，84.227 秒**；DEMO／RESEARCH 各 **94 metrics、0 issues**，G0 工程 PASS，決策級研究發布 BLOCKED。
- 新 table integration suite **13 tests OK**；真實 CLI output 與保存 packet 完全相同，canonical source/observation count 均 0。
- 新 policy／plan／packet 和 proposal／backlog 共五份 YAML 以 strict loader 通過，`git diff --check` 乾淨。原 v1 snapshot SHA-256 不變：`cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e`、`6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`。沒有修改原金融公式、角色或既有 observations。

## 剩餘工作

這份 packet 解決原始數字與哪個表格欄位相連、哪份索引支持 Filing Date、營運公司與上市公司必須分開的問題。它不代替人審，更不將未知幣別或日曆假設變成 VERIFIED metadata。

下一項仍 P2-10：取得明確幣別／量測口徑的原文證據，建立審閱後 operating-company observation 的獨立 admission，再處理 governance receipt/event 原文映射。來源與擷取審閱、真實 canonical admission、G1、自动 discovery/polling 和治理端到端驗收尚未完成。原文 bytes 仍在外部 store，跨機器重現需要其原版備份；repo 的 metadata／packet 不能取代原文。
