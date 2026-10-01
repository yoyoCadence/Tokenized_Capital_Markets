# P2-10：審閱後更新研究資料

這是 **手動啟動、離線可重播的第一個工程增量**。沒有 provider key 或 AI SDK 也能執行。AI 可以提出擷取草稿；原文與 AI 輸出都只能當資料，不能授權發布。來源核准與擷取結果核准是兩次不同的操作。

目前兩個可替換 adapter 的界線：

| Adapter | 原文 | 入庫目標 | 範圍 |
| --- | --- | --- | --- |
| `SEC_FILING_TEXT_V1` | SEC 官網、`FILING`、已存證核准的 UTF-8 text/HTML | v2 `OBSERVED/REALIZED` | 原始數值及原始單位；日期型資料；明示 entity、period、measurement basis |
| `UNISWAP_GOVERNANCE_TEXT_V1` | 官方 Uniswap 治理 host、`GOVERNANCE_PROPOSAL`、已存證核准的 UTF-8 text/HTML | v2 事件帳 | governance/protocol_fee_change 的 PLANNED、ANNOUNCED、APPROVED；不推定 LIVE、burn、收入或價值 |

來源的原始 bytes 留在 repo 外的 content-addressed store。提案只保存原文 SHA-256、byte ranges、每段 SHA-256、候選 record 和真實 staging 時間。沒有原文不能核對引用；只有核准的來源 metadata 也不能代替數值審閱。

## 操作流程

1. 從官方來源取得原始 text/HTML，依既有 `source-stage`／`source-review` 流程存證。metadata 必須對應正確版本、來源日期、文件類型、權利和 covered concept。尚未來源核准的文件不能進本流程。
2. 在 repo 外準備 `draft.yaml`，其中 `candidate` 為待審的 v2 record template，`tokens` 是原文中的**字面文字**。有多次同文出現時不能自動猜欄位，須改成明確的 byte span plan。
3. 產生 plan、預覽、檢查語義與來源定位，再 stage。前三個讀取操作不發布 canonical observation 或事件。
4. 審閱者核對實際 entity、營運公司／殼公司／pro forma、會計口徑、期間、單位、原文版本、來源權利和語義關係，再明確 APPROVED、HOLD 或 REJECTED。
5. APPROVED 以實際 UTC 時間入庫，原子發布 review、canonical record/event、audit snapshot、changelog；中斷後用 `recover` 恢復同一 intent，重試不重複入帳。

```bash
python -m engine.cli source-stage --id official_v1 --metadata /private/meta.yaml --file /private/original.htm --store-dir /private/artifacts
python -m engine.cli source-review --id official_v1 --review-id source_review_v1 --decision APPROVED --reviewer "Reviewer name" --reason "Original version, source date and rights checked" --store-dir /private/artifacts

python -m engine.cli refresh-plan --draft /private/draft.yaml --store-dir /private/artifacts > /private/plan.json
python -m engine.cli refresh-preview --plan /private/plan.json --store-dir /private/artifacts
python -m engine.cli refresh-stage --plan /private/plan.json --store-dir /private/artifacts
python -m engine.cli refresh-status

python -m engine.cli refresh-review --id refresh_v1 --decision APPROVED --reviewer "Reviewer name" --reason "Original entity, accounting basis, period and units checked" --store-dir /private/artifacts --economic-cutoff 2026-09-30 --realized-quarter-end 2026-06-30 --horizon-end 2027-12-31
python -m engine.cli recover
python -m engine.cli replay-v2 --file /path/to/published/content-addressed.json
```

`APPROVED` 是審閱者对擷取結果的明確判定，不等於交易指令；`HOLD`／`REJECTED` 保留在 append-only review ledger。重新考慮須 append 新 proposal ID；修正版觀察值須新 record ID 和 `supersedes_id`。原 bundle 和既有 record 不修改。

## 草稿格式

以下是**合成格式範例**，不是 SECZ 真實營收，不能當真實證據使用。字面 token 必須存在於你已核准的原文；工具會拒絕不存在、重複、值不符或錯單位的 token。

```yaml
schema_version: '1.0'
id: refresh_v1
adapter: SEC_FILING_TEXT_V1
source_id: official_v1
candidate:
  schema_version: '2.0'
  id: revenue_v1
  concept_id: secz_revenue
  entity_id: SECZ
  classification: OBSERVED
  economic_scope: REALIZED
  value: 1250
  unit: USD
  fixture: false
  economic_period: {basis: QUARTER, start: '2026-01-01', end: '2026-03-31'}
  as_of_at: null
  as_of_precision: DATE
  measurement_basis:
    definition_id: reviewed_revenue_definition
    accounting_basis: GAAP
    presentation: GROSS
    consolidation: CONSOLIDATED
    operations_basis: ALL
    fiscal_calendar_id: reviewed_fiscal_calendar
    comparability: STANDARD
tokens:
  value: '1,250'
  unit: USD
  economic_period.start: 'January 1, 2026'
  economic_period.end: 'March 31, 2026'
  publication: '2026-05-01'
  context: 'Revenue USD 1,250'
```

JSON plan 可由 strict YAML loader 讀取。每個 `citations` 欄位是 `{start: <int>, end: <int>, sha256: <64 hex>}`，以完整 UTF-8 原始檔的 **zero-based 半開 byte range** 定位，不以畫面文字索引或字元數代替。計畫也保留 adapter ID、source ID、artifact SHA-256 和 candidate。原文相同 token 出現多次時直接提供確定的 `citations`，不可用「第一個找到的數字」猜所屬欄位。

財報日期支持 ISO、MM/DD/YYYY、英文月份日期；金額不允許自行乘一千／一百萬、換幣或把百分比當 bp。`USD_MILLION` 的原文 token 必須是對應 million 單位，後續轉換使用既有有 formula lock 的 normalization。原文中的零是數值；未披露不能填零，本增量不接受缺值候選。

只有日期且沒有存證時區時，`publication_timezone=null`，歷史選值維持 Unknown。若原文提供明確 IANA 時區文字，可在 draft/plan 加 `publication_timezone`，並提供同名的 exact token/citation；不得自行猜 SEC 日期的時區。已核對日期和時區的可用時點依原 v2 契約採隔日零點；`first_seen_at` 用實際原文取得時間，`ingested_at` 用實際擷取核准發布時間，避免把待審資料冒充先前已入庫。

治理候選模板只含 `id`、`thread_id`、`type`、`status`、`finding`、`affected_nodes: [UNI]`、`fixture: false`，可選 `supersedes_id`；tokens 只有 `publication`、`status`、`context`。publication 必須是原文中帶 offset 的 ISO instant，status 要精確符合原文與 adapter 狀態；finding 是待審摘要，不是自動驗證的經濟結論。新 thread 只能從 PLANNED／ANNOUNCED 開始，APPROVED 須有效前版和新來源。未具備精確 instant 的治理頁仍留待審，不偽造公開時間。

## 驗證能力與尚缺的部分

精確引用、原始數字、單位和期間校驗能拒絕一類擷取錯誤；它們不能證明被引數字真是該公司、该季度或該會計概念。context span 保存定位與 digest，語義仍須審閱。instruction marker 的負例只是有限模式偵測，不是通用 prompt injection 分類器；核心防線是原文永不執行、候選 schema 嚴格、明確人工審閱和經濟 scope 限制。

尚未實作：自動 polling／排程與 provider acquisition、PDF/OCR、網頁多版自動比對、任意文件語義理解、在真實 SEC／治理文件上端到端操作驗收。P2-10 因此維持 **IN_PROGRESS**，下一步仍是 P2-10 的取得與真實原文驗收。repo 的真實 source/observation/event/refresh ledger 仍空，G1 和決策級研究發布維持 BLOCKED。

新 snapshot 為 `2.0-compute-bundle.8`，包含擷取提案及審閱 ledger。前版 bundle 不改写；回放舊 v2 bundle 需匹配它封存的程式／環境版本。兩份原始 v1 demo snapshot 不變。
