# P2-10 第四增量：幣別／會計原文支持證據

日期：2026-10-01；software 0.1.23，plan 1.13，contract proposal.12，bundle `.11`。P2-10 **IN_PROGRESS**；新增真實研究證據與可重現審閱包，尚未發布 canonical 財務觀測值。

## 合併及完成範圍

[PR #22](https://github.com/yoyoCadence/Tokenized_Capital_Markets/pull/22) exact head `f037e3a07e7b31f7fbaf0536582f9a726a06ae17`：非 Draft、可合併、無 review，GitHub G0 run `36846674585` SUCCESS，合併 main `f68ad1daf182d24c10f628b9099be0a770d15d14`。

從官方 SEC 取得並在 repo 外存證兩份新原文，未冒充人審：

| Capture | 原文 SHA-256 | Bytes | 實際取得 UTC |
| --- | --- | ---: | --- |
| secz_operating_mda_20261001 | 7f7ae28126b26c8f3716d01e91213412b3b200a12bc66cab6ca3f888a042ab9a | 356493 | 2026-10-01T10:18:09.296248+00:00 |
| secz_s1_currency_20261001 | 065f5b66392946775efc368726896c902ed7e239bbb4edc8d12de08d53fc439d | 5790137 | 2026-10-01T10:19:23.829551+00:00 |

HTTP 200／text/html；originals 不在 git，重新取得不能假設 bytes 相同，跨機重現需保存原版備份。metadata 的 source date、publisher/title 和 RESTRICTED rights 仍為待審；S-1 取得 metadata 沿用 operating-exhibit publisher qualifier，應在人審核對其文件身份，不能當已核准分類。

## 真實證據及待審決議

[Measurement plan](../research/secz/p2-10-measurement-plan.yaml) 保存三份文件共 **8 citations**，連同原 SEC 表格與索引形成四來源 packet。保存 byte span、原文／正規化文字 SHA-256，不重印長段原文。

| Citation | 支持事項 | 尚待決議 |
| --- | --- | --- |
| gaap_consolidation | EX-99.1 的 US GAAP、子公司合併及內部交易抵銷附註 | 正式 accounting_basis / consolidation / definition_id 映射 |
| reclassifications | 比較期重分類揭露 | 不將同一數字或同比直接認作相同口徑 |
| tokenization_revenue_policy | Tokenization revenue 的多種認列時點 | 不能因此將總收入指定單一 gross/net 口徑 |
| reporting_entity_transition | MD&A 的合併前後公司範圍 | 四筆 Q2/H1 報告主體仍是 operating Inc.，不能填上市 SECZ role |
| acquisition_comparability | 2025-04-15 MG Stover 收購後納入合併 | 2025/2026 revenue 可比性及成長解讀不可默認 STANDARD |
| discontinued_operations | 2025 停業部門的比較期表達 | continuing/all operations 的明示 mapping |
| document_currency_definition | July 31 S-1 對美元符號的明確定義 | 定義限 S-1 文件，是否可支持後續 Q2 Exhibit 99.1 需要人審 |
| historical_currency_presentation | S-1 歷史營運財報轉換成美元表達的附註 | 歷史 accounting policy 是否延續至四筆 Q2/H1 候選 |

四筆候選原文數值仍為 14,435,845／15,262,176／33,914,311／29,296,195。支持文本存在不等於適用性已核准；**unit=null**、publishable=false、canonical_admission=false。日曆起日仍 analyst-normalized pending review，fiscal calendar 與 gross/net 未解決。Publication 仍同 accession 索引 Filing Date 2026-08-13，timezone unknown；S-1 日期不能替代收入發布日。

## 實作邊界

- plan/packet **1.1** 增 supporting_evidence；1.0 schema 和原 packet 保持完全可重現。
- 每份支持原文經 staging ledger／SHA-256 核對；唯一文件與 citation ID、1～8 documents、每份 1～20 citations、每段上限 8192 bytes；引用與 inert HTML 正規化文字 digest 都必須吻合。未知欄位、錯原版、假文字、重複引用與 script 拒絕。
- `text_verified` 僅證明文本符合指定原版；semantic_status 始終 PENDING_REVIEW。role 是審閱提示，不是已驗證語義。HTMLParser 不模擬任意 CSS 可見性。
- Packet sources 含全部支持版本，first_seen_at 取全部原文的最晚真實 retrieval；此新 packet 為 2026-10-01T10:19:23.829551+00:00。候選 numeric source_ids 仍原財報／索引，supporting evidence 另列，不能偽裝新來源報告了同一數字。ingested_at null。
- 現為 **6 captures，0 source reviews，0 canonical sources/observations/events/refresh proposals/reviews**。bundle `.11` 存 code/config/ledgers，不包含外部原文或把 packet 送入金融計算。

## 驗證

固定 CPython 3.12.14／PyYAML 6.0.3，`python -m scripts.g0_gate`：**239 tests OK，82.149 秒**；DEMO／RESEARCH 各 **94 metrics、0 issues**，工程 G0 PASS，研究發布 BLOCKED。三個新增 integration tests 覆蓋 supporting version/span/text tamper、嚴格欄位／空值／重複／script、只讀性、first_seen 與美元文本不自動核准／不入庫邊界；SEC table suite 現共 16 tests，均在完整 gate 通過。

原版 1.0 與新版 1.1 真實 packet 均使用外部原文離線重現，與保存 YAML 完全相同；strict YAML 文件驗證及 git diff --check 通過。v1 snapshots SHA-256 不變：`cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e`、`6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`。未改既有金融公式、canonical observations 或核心 SECZ roles。

## 下一步

以本 packet 作具體 source/extraction 人審材料，決議美元定義的跨文件／期間適用性、會計／gross-net／operations／fiscal／comparability，必要時 HOLD 並指定所缺原文。然後建立獨立 operating-company identity/concept/role 及 packet-to-canonical reviewed admission，不借用上市 SECZ 身份；治理端再補 receipt/事件證據。自動 discovery/polling、真實財務／治理端到端驗收與 G1 尚未完成。工程 PR 合併不是上述研究核准，P2-10 和決策级研究發布仍未完成。
