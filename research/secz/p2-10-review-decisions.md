# Securitize Inc. 四筆收入：具體待審決議

2026-10-02，狀態 **PROPOSED / PENDING_REVIEW**。本文件是分析者提出的審閱材料，沒有來源批准、擷取批准或 canonical observation。

提案 `securitize_inc_revenue_measurement_proposed_20261002`，stage 時間 `2026-10-02T04:09:44.574369+00:00`，plan SHA-256 `22a00df6b023dd7089b26b9d81deb78e042da2cf69a8e3a1c1788ba781d1cdb5`。完整 [plan](p2-10-decision-plan.yaml) 與 frozen packet 存於 [append-only ledger](../../data/v2/refresh/sec_tables.yaml)。舊 `securitize_inc_revenue_admission_pending_20261001` 原樣保留；它沒有發布觀察值，因此新 record IDs 不填指向不存在 observation 的 supersedes_id。兩個待審提案不是八筆獨立收入。

## 一次需要審查的數值與期間

主表為 **Securitize, Inc. and subsidiaries** 的未經審計合併損益表，Exhibit 99.1 第 3 頁。數字與原表單位尺度一致，沒有乘除一百萬。

| Candidate | 原表 Revenue | 提議單位 | 提議期間 | 期間依據 |
| --- | ---: | --- | --- | --- |
| q2_2026_revenue | 14,435,845 | USD | QUARTER，2026-04-01～2026-06-30 | Three Months Ended June 30 + 2026 |
| q2_2025_revenue | 15,262,176 | USD | QUARTER，2025-04-01～2025-06-30 | Three Months Ended June 30 + 2025 |
| h1_2026_revenue | 33,914,311 | USD | YTD，2026-01-01～2026-06-30 | Six Months Ended June 30 + 2026 |
| h1_2025_revenue | 29,296,195 | USD | YTD，2025-01-01～2025-06-30 | Six Months Ended June 30 + 2025 |

**起日是日曆月期間推導，不是原文字面起日。** Quarter 與 YTD 不能相加；此批次不生成增長率、TTM、估值或 SECZ 上市公司收入。

## 五項量測決議

四筆採相同的提議 basis：`SECURITIZE_INC_REPORTED_REVENUE / GAAP / AS_REPORTED / CONSOLIDATED / CONTINUING / securitize_inc_calendar_dec31_v1 / ACQUISITION_SCOPE_CHANGE`。所有欄位均仍待審，填完整不等於通過。

| Review acknowledgement | 提議決議 | 原文與推論邊界 |
| --- | --- | --- |
| CURRENCY_APPLICABILITY | USD，原表金額不縮放 | Q2 Note 2 要求併讀 2025/2024 年度報表並說明重大會計政策的延續；同營運公司年度 Note 2 將海外業務換算為 U.S. dollars 作報表表達。這是跨文件適用性的**分析者推論**，Q2 附註沒有獨立字面 USD 宣告。S-1 的全文件美元符號定義僅限該 S-1；其較前段殼公司 USD 表達段落不能代替營運公司證據。若不接受連續性推論，應 HOLD 並取得直接 Q2 幣別證明。 |
| ACCOUNTING_SCOPE | GAAP / CONSOLIDATED / AS_REPORTED / CONTINUING | Q2 Note 2 指明 Inc. 及全資子公司的 GAAP 合併。AS_REPORTED 保存主表 aggregate，不斷言所有收入服務都是 gross 或 net。Note 4 將 Securitize for Advisors 的 2025 Revenue 另列於 discontinued operations；其 Q2 60,682、H1 71,319 不加入主表四筆。這兩個附註數字只是本次口徑的支持證據，沒有另入庫。 |
| PERIOD_NORMALIZATION | 日曆年末 Dec31；Three/Six Months Ended June30 正規化為 Apr1/Jan1 起日 | S-1 年度 auditor opinion 指明 Inc. 2025/2024 年度截至 Dec31；歷史 auditor-change 段落明列 Inc. 2024/2023 fiscal years ended Dec31。Q2 又併讀 2025/2024 年度。現有 calendar-month duration method 據此提出起日；這些歷史／年度證據不自動核准上市公司 fiscal calendar，也不保證未來年度不改制。 |
| COMPARABILITY | ACQUISITION_SCOPE_CHANGE | MD&A 說明 MG Stover 於 2025-04-15 收購後開始合併。2025 Q2／H1 的納入期間少於 2026，因此保留 scope-change 標記。主表是當期文件重列的 2025 comparatives；Note 2 已提示 prior-period reclassification。不可標 STANDARD、organic growth，也不可替換為 Note 3 假設較早收購的 pro forma 收入。 |
| OPERATING_ENTITY | entity=securitize_inc，concept=securitize_inc_revenue，無 security_id | 表頭、Note 2 與 MD&A 分別核對營運公司及合併前後語境；上市 Securitize Corp.／原 CEPT 殼公司／hypothetical pro forma 保持各自範圍。既有 SECZ issuer valuation roles 不取用本 concept。 |

## 原文定位，供實際審閱

下列 byte ranges 為 `[start,end)`，指向外部 content-addressed 原版，不是網頁顯示字元或行號；每段 raw SHA-256 與 normalized-text SHA-256 都在 plan。新增 14 段，連同既有 8 段共 **22 段 supporting citations**；主表數值、表頭、索引引用另計。

| Source / citation IDs | 原版定位 | 用途 |
| --- | --- | --- |
| financials: gaap_consolidation | 688666～689173 | GAAP 與合併範圍 |
| financials: annual_statements_cross_reference / accounting_policy_continuity | 693887～694639 / 694694～695180 | 年度交叉閱讀與政策延續 |
| financials: reclassifications | 695834～696101 | 當期文件比較欄位重列 |
| financials: discontinued_sale_and_presentation / discontinued_table_context | 752865～753447 / 753502～753757 | 停業分類與另表語境 |
| financials: discontinued_quarter_header / discontinued_quarter_year | 755549～755782 / 756362～756572 | 2025 Q2 停業欄位 |
| financials: discontinued_ytd_header / discontinued_ytd_year | 755952～756183 / 756742～756952 | 2025 H1 停業欄位 |
| financials: discontinued_revenue_label / discontinued_quarter_revenue / discontinued_ytd_revenue | 756961～757197 / 757601～757855 / 758460～758714 | 停業 Revenue 60,682／71,319 |
| financials: tokenization_revenue_policy | 1107478～1108464 | 收入認列時點，不當成單一 gross/net 證明 |
| mda: reporting_entity_transition / acquisition_comparability / discontinued_operations | 666～2496 / 28088～28758 / 46935～47450 | 身份、收購比較範圍及停業交叉核對 |
| s1: document_currency_definition | 415035～415356 | 文件內符號定義，不能單獨延伸至 Q2 |
| s1: annual_operating_entity_heading / historical_currency_presentation | 4684645～4684839 / 4698755～4699533 | 同營運公司年度 Note 2 的美元表達 |
| s1: annual_audit_year_end / historical_fiscal_year_end | 4122638～4123557 / 2219006～2219486 | Inc. 年度年末及歷史 fiscal year corroboration |

## 四份來源的獨立審阅

以下四個 metadata captures 全為 CAPTURED、Tier 1、FILING、HTML、publisher `SEC EDGAR / Securitize Corp.`、covered_metrics `[securitize_inc_revenue]`、rights `RESTRICTED`。權利分類只保留來源使用限制，不宣稱取得再散布原文的授權；原版留在外部 store，git 僅保存定位及摘要。來源審阅需核對 metadata 與原件、日期、權利分類及 concept coverage。

| Source ID | 文件／來源日期 | 完整原文 SHA-256 |
| --- | --- | --- |
| securitize_inc_financials_scope_20261001 | [EX-99.1](https://www.sec.gov/Archives/edgar/data/2094496/000162828026056811/exhibit991securitize-q22026.htm)，2026-08-13 | 271119e0e767211e69179cba9e8a30e24f4b15877918ea1402eb42b02cae3e31 |
| securitize_inc_index_scope_20261001 | [SEC filing index](https://www.sec.gov/Archives/edgar/data/2094496/000162828026056811/0001628280-26-056811-index.html)，2026-08-13 | 5ffd7893b144a5561073ad15dae18ab3e20f2944708e3921fe102faee5b446d9 |
| securitize_inc_mda_scope_20261001 | [EX-99.2](https://www.sec.gov/Archives/edgar/data/2094496/000162828026056811/exhibit992securitizemdaq22.htm)，2026-08-13 | 7f7ae28126b26c8f3716d01e91213412b3b200a12bc66cab6ca3f888a042ab9a |
| securitize_inc_s1_scope_20261001 | [July31 S-1](https://www.sec.gov/Archives/edgar/data/2094496/000162828026051182/secz-20260731.htm)，2026-07-31 | 065f5b66392946775efc368726896c902ed7e239bbb4edc8d12de08d53fc439d |

使用原有十個 captures／六份唯一原件，沒有新下載或新 receipt。packet first_seen 仍是四個既有 scoped captures 的最晚實際讀取 `2026-10-01T11:38:34.980244+00:00`；不是本次新增引用的發現時間。這次審查才補充的 span/mapping 由新 proposal 的 stage 時間保留。SEC index 確認 EX-99.1 關係及 filing date **2026-08-13**；timezone 仍 null，Accepted 字串不被猜成有 offset 的發布時間。

## 審閱完成後的具體操作

目前四份 source reviews 與五項 acknowledgements 均為零。具名審閱者應先對四份來源各自決定 APPROVED/HOLD/REJECTED，再對上述提案決定；來源 APPROVED 只發布 metadata，不直接發布收入。可在對話中逐項記錄接受／保留／拒絕、真實 reviewer 與理由，或由審閱者使用 [CLI 操作說明](../../docs/RESEARCH_REFRESH.md)。單純合併程式 PR 不是這五項決議。

若全部接受，使用本提案 ID 與五項 acknowledgements 完成 `sec-admission-review`；需明示本次 audit economic/model cutoffs。若 mapping 需修改，append 新 proposal ID／record IDs，再 stage；原版與舊提案不覆寫。只有實際 admission 才有 ingested_at、四筆 canonical records 與 audit snapshot。

即使這五項通過，未知 publication timezone 仍阻止 temporal selection；仍需另行取得可核對的公開可知時間證據。收入入庫也不補齊 listed issuer bridge、現金流、股數、UNI/XLM economics 或 G1。下一個可獨立推進的研究題是 UNI governance chain receipt，不能將 portal 的 Executed 標籤當作實際 burn。
