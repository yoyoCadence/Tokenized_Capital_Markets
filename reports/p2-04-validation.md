# P2-04：Bottom-up TAM 與可服務成交量

**2026-09-30｜軟體 0.1.18｜工程橋接完成｜真實研究 BLOCKED**

## 口徑及來源線索

SEC 工作人員的[證券代幣化說明](https://www.sec.gov/newsroom/speeches-statements/corp-fin-statement-tokenized-securities-012826-statement-tokenized-securities)區分發行人自己代幣化、第三方託管權益及合成曝險；同一證券可有不同記錄形式，第三方產品的權利可能不同。這是分類線索，該工作人員聲明並非法規或具法律效力的指引。[SEC Form N-PORT](https://www.sec.gov/investment/new-form-n-port)分別記載基金投資標的的識別、單位和金額，因此研究須保留「基金股份」與「基金所持股票／債」的兩層權利。既有 [SECZ 發行人公告](https://investors.securitize.io/news/news-details/2026/Tokenizing-SECZ-Securitize-Brings-Its-Own-Public-Stock-Onchain-at-Listing-Day/default.aspx)提供一個待驗證的股票 cohort 候選，不能藉公告填入發行餘額、可交易流通量或成交。上述連結均為 **LINK_CHECKED_UNARCHIVED**，未被當作 canonical 數值證據。

| 層 | 精確口徑 | 不得作的推論 |
| --- | --- | --- |
| Claim | 發行人＋證券 ID 對應唯一法律 claim；EQUITY／FUND／CREDIT 分列，直接權利／entitlement／synthetic／基金股份分明 | 不以 token 數量增添底層證券；不同權利不混稱同一股票 |
| 表示形式 | NATIVE/TRADITIONAL 為 root，WRAPPED/BRIDGED 有同 claim 的 parent；鏈上轉形不生新 claim | 不累加同一權利的 wrapped 或跨鏈映射餘額 |
| 基金重疊 | FUND_SHARE 是獨立證券，引用底層 claim；可查重疊但不產生跨類股票存量總和 | 不把基金份額資產值和其持股加成「市場總值」 |
| 存量階梯 | `eligible_usd ≥ issued_usd ≥ float_usd ≥ serviceable_float_usd`，同一 as-of 的整數 USD；每步有 classification、來源 ID、fixture 及理由 | 不由 issuer AUM、股價或週轉率直接填空；unknown 保持 null |
| 成交流量 | 同一完成期間內，完整交易帶、唯一 economic execution、不同買賣方、權利人變更、wash 審核 CLEARED 的 OBSERVED 成交才計入 | mint、burn、bridge、internal、普通轉移、自成交與疑似 wash 不計；部分 tape 不是全量成交 |
| 收入 | 已實現收入單獨輸入 `realized_revenue_usd`，來源／分類獨立 | 成交額不自動變協議費或股東價值；沒有費率與 capture 證據不反推收入 |

`python -m engine.cli tam-report` 使用 [嚴格研究 pack](../research/tam/p2-04-cohorts.yaml) 及 v2 source loader，只輸出 audit report，不改 canonical ledger／snapshot。`--plan` 可指定另一份相同契約。全集的 `universe_scope` 與三類 `universe_coverage` 須各自界定，不能從少數樣本外推。真實非 fixture 的數值 OBSERVED 行需能對到已存原文 digest、審閱 ID 和 locator 的 v2 source；已取得／公布日期不得在報告 as-of 之後。假設要明示理由，並僅列於 `conditional_scenario_by_asset_class`；`by_asset_class` 只加總 observed 值。`realized_revenue_usd` 不接受假設。完整 tape 也須另有覆蓋憑據；有一筆交易不代表全市場的完整量。系統驗證的是結構、來源關聯和計數，原文內容與 wash 實質仍需人工核對。

## 目前結果與缺口

真實 pack 的 cohort／交易陣列是空的，v2 實際 source/observation ledger 亦空。EQUITY、FUND、CREDIT 的五項存量／收入及成交量全部 `null`；`cross_class_stock_total_usd` 和 `asset_value_usd` 始終 `null`。現階段沒有 TAM 金額或可服務交易量。若以合成完整 tape 跑三類別，三個法律 claim 的 issued 分別為 1,000／800／200 USD，原生及 wrapped/bridged 映射未令股票 1,000 重複；有效成交 30／10／20 USD，mint 900、internal 500、自成交 300 與疑似 wash 400 不入交易量。這些全是 **fixture**，不能發布為市場事實。

使研究可驗收尚須：定義覆蓋的司法管轄與發行人／證券全集、各類合法及操作資格、發行及即時餘額、可轉讓流通與合格 venue/holder、全期間去重且審查 wash 的成交記錄、capture 合約與收入對帳；每項均需原始檔存證、人審、期間與單位校對。合成測試只證明算式與拒絕條件。P2-04 維持 **BLOCKED**，後續不依賴它的 P2-08 可先行。

## 驗收

- `tests/regression/test_tam.py` 驗證空資料 unknown、三類／基金底層重疊、wrapper/bridge 與成交排除、重複 claim/同筆 execution、跨期、存量階梯、無來源真實數及假設／實際分流。
- 完整 suite **194 tests OK**；DEMO/RESEARCH validate 各 **94 metrics、0 issues**；G0 工程 **PASS**、研究發布 **BLOCKED**、真實 observation **0**。原始 v1 DEMO snapshots SHA-256 維持 `cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e` 和 `6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`。沒有公式版本、研究觀察值或存量經濟結論變更。
