# P2-10 第五增量：獨立營運公司批次審閱入庫

2026-10-01：software **0.1.24**、plan 1.14、contract proposal.13、bundle `.12`。P2-10 **IN_PROGRESS**；工程入庫流程完成，真實來源及量測人審尚未完成。

## 合併基準

[PR #23](https://github.com/yoyoCadence/Tokenized_Capital_Markets/pull/23) head `443dcd69654b82627c801c791a5e3292c893cf19`，GitHub G0 run `36849423274` SUCCESS、非 Draft／可合併；合併 main `a1ad2ad100b2778f4878ab4ec0ed33a45e4d57f6`。

## 實際交付

- 身份表原本已包含 `securitize_inc`，本增量重用它，增加 **獨立 revenue concept、QUARTER/YTD roles 與 reported definition**。沒有新增上市 ticker/security、變更 SECZ issuer role 或金融公式。
- 新 `sec-admission-preview/stage/review/status` 以 1.1 table plan、原文 SHA-256/byte spans／正規化文字 digest、immutable mappings 建立批次提案。stage 可容納未知欄位，並不發佈 v2 observation。
- APPROVED 需要全部 supporting/table/index sources 各自批准且覆蓋新 concept、全部 basis 和 USD applicability、具名 reviewer／理由／五項 scope acknowledgements。重新核对原文與 frozen packet，來源 review 不能晚於擷取 review。
- 一次原子發布：batch review、四筆 canonical observations、content-addressed snapshot、changelog。每個發布步驟可 recover；重試核對既有 bundle／records，改動提案必須新 ID。
- 新 basis 值 `AS_REPORTED` 留存原表總数但不斷言 uniform gross/net；`ACQUISITION_SCOPE_CHANGE` 留下比較範圍疑慮。舊 normalization／valuation formulas 不接入新 operating concept，不改 expression/version/lock。

## 真實已存入 staging 的內容

[Admission plan](../research/secz/p2-10-admission-plan.yaml)、[append-only admission ledger](../data/v2/refresh/sec_tables.yaml)：

- Proposal `securitize_inc_revenue_admission_pending_20261001`：**PENDING_REVIEW**，原表四筆值 14,435,845／15,262,176／33,914,311／29,296,195；全部不縮放。
- GAAP／CONSOLIDATED／reported definition／acquisition scope 只是提議 mapping；unit、presentation、operations_basis、fiscal_calendar_id 仍 null。所有 dimensions 都需人審，不能直接將某個 null 填 NOT_APPLICABLE 來過 validator。
- Calendar interval 與原版 packet 完全相同；candidate period normalization 顯式待審，不把起日當原文字面。publication 仍 SEC index Filing Date 2026-08-13，timezone unknown，不猜 accepted-time timezone。
- 六份唯一原文及原六個 capture 原样保留。另追加四個新概念 coverage 的 `MANUAL_FILE_V1` scoped captures，使用相同外部原文 digest，**未重新下載**、未虛構 HTTP receipt。新 metadata 修正 issuer publisher qualifier，但本身仍待審。

| 新 scope capture | 既存原文 digest 前綴 | 真實新讀取 UTC |
| --- | --- | --- |
| securitize_inc_financials_scope_20261001 | 271119e0e767 | 2026-10-01T11:38:34.284485+00:00 |
| securitize_inc_index_scope_20261001 | 5ffd7893b144 | 2026-10-01T11:38:34.496776+00:00 |
| securitize_inc_mda_scope_20261001 | 7f7ae28126b2 | 2026-10-01T11:38:34.717430+00:00 |
| securitize_inc_s1_scope_20261001 | 065f5b663929 | 2026-10-01T11:38:34.980244+00:00 |

使用 metadata scopes 而非修改 capture，是因 canonical source validator 要求明示 covered concept，舊 source 只登記 secz_revenue。scopes 是新研究用途，不宣稱替代舊來源／重述原財報。first_seen 取所有新 scope 的實際較晚讀取，不冒充先前已入庫；真正 ingested_at 只在之後 extraction APPROVED 時計錄。

目前 **10 captures／6 unique artifacts、0 source reviews、1 SEC admission proposal、0 SEC admission reviews、0 canonical sources/observations/events、0 literal refresh proposals/reviews**。一個 proposal 包含四個候選，不是四個已入庫 records。

## 驗證

固定 CPython 3.12.14／PyYAML 6.0.3，`python -m scripts.g0_gate`：**247 tests in 108.217s  OK**；全部通過。DEMO／RESEARCH 各 **94 metrics、0 issues**；G0 工程 PASS，research publication BLOCKED。原新增 eight-test suite 亦通過；最終完整 gate 包含 AS_REPORTED／ACQUISITION_SCOPE_CHANGE migration。

八個 integration tests 使用 disposable synthetic originals：pending-null／stage-before-source-review、source coverage／全維度／acknowledgements、單獨 operating concept/entity 及 issuer 隔離、date-only unknown 選值、實際 ingestion、HOLD/REJECT／immutable IDs、假原文／packet／mapping tamper、strict YAML／只讀 CLI、atomic publication 的 journal/review/ledger/snapshot/changelog/finalize **六個中斷點**及 recover/retry。Synthetic APPROVED records 只存在 temporary test projects。核准測試的 bundle 可離線 replay，新的 admission ledger 在 archive 内。批次 YAML 明確複製每筆來源列表以防 serializer 生成 validator 禁止的 alias；plan hash 使用 canonical sorted JSON，與 YAML key order 無關。

真實 pending plan/packet 已從原版 artifact store 離線重現；stage retry 不變更任何檔案。原 1.0/1.1 真實 packets 和六份既存 capture records 完全相同。strict YAML 和 git diff --check 通過。v1 demo snapshot SHA-256 保持 `cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e`、`6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`。新 roles/concept 追加於清單尾端，保留既有次序與 regression。

## 尚缺的實際審阅及下一步

1. 四個 scoped source 的文件身份／日期／rights／coverage 人審；不是批准工程 PR 就完成 source review。
2. 跨文件美元定義／歷史政策對 Q2/H1 的適用性；presentation 可決議為 AS_REPORTED，但須承認不等於統一 gross/net，也不保證可比。
3. Continuing/all operations、日曆 duration normalization、獨立 operating fiscal calendar、acquisition comparability 的明示理由；不指派上市 issuer metadata。
4. 追加完整新 mapping plan/proposal 後，由實際審阅者核准 extraction；保留完整 source review IDs 和 observation lineage。

所有來源與擷取人審仍未發生；本次沒有虛構具名 reviewer。即使之後 admission 完成，未知 publication timezone 仍阻止 temporal eligibility，不宣稱資料自動進入研究決策。自動 discovery/polling、治理 receipt/事件真實驗收、G1 及研究 decision-ready publication 仍缺。外部原文 bytes 未入 git，跨機器重現須保存原版 artifact store。
