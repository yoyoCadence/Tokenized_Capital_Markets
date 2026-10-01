# P2-10：審閱後更新研究資料

這是 **手動啟動、離線可重播的研究更新流程**，現已包含官方 HTTPS 原文下載。沒有 provider key 或 AI SDK 也能執行。AI 可以提出擷取草稿；原文與 AI 輸出都只能當資料，不能授權發布。來源核准與擷取結果核准是兩次不同的操作。

目前兩個可替換 adapter 的界線：

| Adapter | 原文 | 入庫目標 | 範圍 |
| --- | --- | --- | --- |
| `SEC_FILING_TEXT_V1` | SEC 官網、`FILING`、已存證核准的 UTF-8 text/HTML | v2 `OBSERVED/REALIZED` | 原始數值及原始單位；日期型資料；明示 entity、period、measurement basis |
| `UNISWAP_GOVERNANCE_TEXT_V1` | 官方 Uniswap 治理 host、`GOVERNANCE_PROPOSAL`、已存證核准的 UTF-8 text/HTML | v2 事件帳 | governance/protocol_fee_change 的 PLANNED、ANNOUNCED、APPROVED；不推定 LIVE、burn、收入或價值 |

來源的原始 bytes 留在 repo 外的 content-addressed store。提案只保存原文 SHA-256、byte ranges、每段 SHA-256、候選 record 和真實 staging 時間。沒有原文不能核對引用；只有核准的來源 metadata 也不能代替數值審閱。

## 操作流程

1. 以 `source-acquire` 下載官方原始 text/HTML，或用 `source-stage` 匯入外部原文，再獨立執行 `source-review`。metadata 必須對應正確版本、來源日期、文件類型、權利和 covered concept。尚未來源核准的文件不能進擷取發布流程。
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

## 官方原文下載

`source-acquire` 只取得 metadata 指定的一份原文，不會搜尋新財報、排程、執行頁面 script 或自動核准。使用既有 `source-stage` 的外部 metadata YAML 格式：`url`、`publisher`、`title`、`document_kind`、`source_date`（可 null）、`tier`、`covered_metrics`、`locator`、`rights`、`media_type`，可選 `supersedes_id`。日期與權利是待審聲明，不從 HTTP Date／Last-Modified 猜財報公開日。

```bash
python -m engine.cli source-acquire --id official_http_v1 --metadata /private/meta.yaml --store-dir /private/artifacts --user-agent "Your actual application name and contact"
python -m engine.cli source-status
python -m engine.cli source-verify --id official_http_v1 --store-dir /private/artifacts
```

- 目前只允許 SEC 的 `FILING` 與官方 Uniswap 的 `GOVERNANCE_PROPOSAL`，Tier 1／2。拒絕額外 port、credentials、query、fragment、非 HTTPS 和未核准 host。所有 redirect 均拒絕，不轉向新目的地。
- 只接受與 metadata 相符的 text/plain、text/html 或 application/xhtml+xml，UTF-8／ASCII，未壓縮的 200 response，最多 32 MiB；檢查 Content-Length、空內容及已知 provider block 頁。
- 同一 project 的下載共用鎖，每次完成後至少間隔一秒。單次 socket 等待最多 10 秒，總 deadline 30 秒於每次 read 前後檢查；最差可多出最後一次 blocking read 的 10 秒。跨 project 的總 rate 仍由操作者管理。SEC 要求宣告 application/contact User-Agent 並節制存取：[官方政策](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)。User-Agent 不存入 git，應填實際聯絡資料。
- schema 1.1 的 `http` receipt 保留 `requested_at`、`completed_at`、`status_code`、`content_type`；`attempted_at` 是 attempt 完成時，`retrieved_at` 是成功取得完整 bytes 的實際時間。失敗為 FAILED，retrieved/hash/size 均 null，不存 error body，CLI 回非零。
- 相同 ID／metadata 重試只回既有紀錄；CAPTURED 必須先驗證外部原文，FAILED 不自動重打。需重新取得時 append 新 ID，適用時附 `supersedes_id`。舊 1.0 manual ledger 可讀，首次 HTTP capture 升為 1.1。
- 原文存放與備份由外部 artifact store 負責。clone repo 只有 metadata／hash，不能取代原文；缺少原版 bytes 時不能完成引用驗證，不可覆寫舊 digest，重新下載要新版本。

第二增量取得三份未核准官方原文，詳見 [驗收](../reports/p2-10-acquisition-validation.md)；第三增量再取得 SEC 索引，現在共四份待審原文。可使用原版 artifact store 執行第二增量的唯讀引用稽核：

```bash
python -m scripts.verify_original_citations --plan research/refresh/p2-10-original-citations.yaml --store-dir /private/artifacts
```

這只核對完整原文 hash 和九處 byte ranges，明示 `UNREVIEWED_RESEARCH_LEADS`／`financial_publication=false`。SEC 財報以表頭、年份欄位及 `$` 記帳，沒有擷取器要求的起日、USD 與公開日期字面 token；同一收入數字出現三次。不能拼出原文沒有的引用，也不能把合併前營運公司數字直接指派給上市 SECZ。治理 HTML 包含 portal-reported execution／creation timestamps；未審日期、欄位對應和鏈上 receipt 仍是缺口。

## 真實 SEC 表格審閱包

`sec-table-preview` 是獨立的唯讀、離線候選檢查，可從未審 captured 原文建立 review packet；它不會替來源核准，不沿用文字 adapter 的 literal 日期假設，也不發布 v2 record。

```bash
python -m engine.cli sec-table-preview --plan research/secz/p2-10-table-plan.yaml --store-dir /private/artifacts
```

本次 plan 明確引用完整 financial table、近旁營運公司及 statement heading，以及同 accession 的 SEC index。colspans 展開成 logical columns，Revenue row 的數字綁定各自 `$`／year／Three or Six Months Ended cell；每一個 cell 保存 exact raw bytes citation。索引的 EX-99.1 href 必須指向同一原版，Filing Date 有獨立引用；Period of Report 和簽名日期不代替 publication。

plan 欄位：`schema_version: '1.0'`、`id`、`entity_id: securitize_inc`、`source_id`／`artifact_sha256`、`index_source_id`／`index_artifact_sha256`、`entity_heading`／`statement_heading`／`table` 各自的 `{start,end,sha256}`、`period_row`／`year_row` zero-based row index，以及 `columns` 的 `{id,value_column,symbol_column}` zero-based **logical** indices。目前只支援這種顯式營運公司 Revenue table，拒絕 rowspans、nested／irregular rows、不明符號／數字／period 和無法核對的關聯，不宣稱泛用 HTML/CSS 解析。

四筆真實擷取結果保存在 [packet](../research/secz/p2-10-table-packet.yaml)，皆 **PENDING_REVIEW**／`publishable=false`／`canonical_admission=false`。unit null，因 `$` 不足以認定 USD。Three／Six Months Ended 加年份的月末日期可生成明示的待審日曆區間，標 `ANALYST_NORMALIZED_PENDING_REVIEW`，不是原文含起日的 quote；fiscal calendar／量測口徑仍未知。entity 固定為營運公司 `securitize_inc`，不能改成上市 SECZ role。

來源/數值分類、日曆推導、publication date、unknown timezone、兩份原文的實際 retrieval 和完整 review requirements 都在 packet 保留。first_seen 用兩份 supporting originals 的較晚 retrieval；ingested_at null。clone repo 的 packet 只供審閱，不能直接複製到 canonical records；財務 validator 會拒絕它。語義人審、幣別證據與 packet-to-canonical admission 尚未完成，見 [第三增量驗收](../reports/p2-10-sec-table-validation.md)。

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

尚未實作：自動 discovery／polling／排程、PDF/OCR、網頁多版自動比對、任意文件語義理解、真實 SEC／治理原文的審閱發布端到端驗收。P2-10 因此維持 **IN_PROGRESS**，下一步是幣別／量測口徑原文證據與 reviewed operating-company admission，再處理治理欄位／receipt 映射。repo 有六筆未審原文 capture、四筆只供審閱的 SEC 表格候選；canonical source/observation/event/refresh ledger 仍空，G1 和決策級研究發布維持 BLOCKED。

新 snapshot 為 `2.0-compute-bundle.11`，包含 HTTP staging receipt、取得及表格 packet policy／程式和擷取審閱 ledger；packet 不會進核心計算。前版 bundle 不改写；回放舊 v2 bundle 需匹配它封存的程式／環境版本。兩份原始 v1 demo snapshot 不變。

## 第四增量：支持幣別／會計證據（packet 1.1）

新增 `research/secz/p2-10-measurement-plan.yaml` 與 `p2-10-measurement-packet.yaml`，不覆寫原版 1.0 plan/packet。以相同 `sec-table-preview` 命令離線重現新版：

```bash
python -m engine.cli sec-table-preview --plan research/secz/p2-10-measurement-plan.yaml --store-dir /private/artifacts
```

1.1 只增 `supporting_evidence`；每份文件必須有唯一 source_id、原文 SHA-256，及 1～20 個唯一 citation ID/role/byte span/normalized_text_sha256。最多八份支持文件、每段最多 8192 bytes，拒絕未知欄位、假文字 digest、錯原版、重複引用及 executable HTML。正規化文字為 inert HTMLParser 可見文字的空白合併；不宣稱完整 CSS 可見性。保存 digest/定位而非長篇原文；實際內容可由外部原版與引用定位核查。

`text_verified=true` 只表示原版／文字相符；`semantic_status=PENDING_REVIEW` 不會設定 USD、GAAP 等 canonical dimensions。source approvals 全部 false、unit null、ingestion null，候選 source_ids 仍為原數字／索引來源；packet sources 加支持來源，first_seen_at 取全部原文的較晚真實取得時間，不回填歷史。支持原文的 source_date 不取代原 Filing Date。

S-1 貨幣定義限其文件；歷史財報的美元表達需審閱是否延續至 Q2 Exhibit 99.1。MD&A 提醒 pre/post-combination identity、2025 acquisition 和 discontinued-operations 比較範圍。gross/net、fiscal calendar、跨期可比性與營運公司身份仍需決議；批准 PR 不等同來源／擷取人審。詳見 [驗收及待審決議](../reports/p2-10-measurement-validation.md)。現有 canonical source/observation/event 仍為 0。
