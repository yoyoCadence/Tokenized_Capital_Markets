# 規劃使用的官方來源與後續查核任務

**查閱日期：2026-09-25｜僅研究筆記，尚未寫入 canonical source/observation registry**

本次用少量 primary sources 核對規劃方向，沒有進行完整市場／財報更新。以下 metadata 是待入庫線索；未保存原檔、hash、完整擷取與 reviewer 核對，所以不能直接當成可重播的已驗證資料包。

來源層級按原專案政策判斷；官方公司／協議發布通常 Tier 2，SEC 與可驗證 onchain 原始紀錄為 Tier 1。網頁何時被查閱與它何時公開分開。

## S-PLAN-01：Uniswap UNIfication 原始提案

- Publisher：Uniswap Labs／共同提案人。
- Title：UNIfication。
- Source date：2025-11-10。
- Retrieved on：2026-09-25。
- Tier：2（官方提案；仍需對照 governance、執行合約）。
- URL：[官方提案](https://blog.uniswap.org/unification)。
- 覆蓋：protocol fee、TokenJar/Firepit、growth budget、Unichain accrual 的設計。

**可支持**：該提案描述 fee 與 burn 的連結，並提出每年 20M UNI、按季透過 vesting contract 分配的 growth budget。

**不能由此單獨支持**：截至現在所有 fee rollout 均已實施、預算已全部轉出、實際 burn 金額、分配等同新增鑄幣，或未來 holder return。

下一次需核對治理最終版本、投票與 timelock execution、chain/contract address、實際 vested／transferred／burn logs、後續修改。目前程式中的 20M 仍維持原有 fixture assumption；本次查閱沒有把它升級成 realized distribution observation。

## S-PLAN-02：Securitize 業務合併完成公告

- Publisher：Securitize Investor Relations。
- Title：Securitize Completes Business Combination with Cantor Equity Partners II。
- Source date：2026-07-01。
- Retrieved on：2026-09-25。
- Tier：2。
- URL：[公司 IR 公告](https://investors.securitize.io/news/news-details/2026/Securitize-Completes-Business-Combination-with-Cantor-Equity-Partners-II/default.aspx)。
- 覆蓋：公司聲明的合併完成、預期掛牌安排、實體與投資工具辨識。

**可支持**：公司在該日發布「合併完成」聲明；同頁交易起始仍以預期 2026-07-02 表述。這兩個命題的證據狀態不同。

**不能由此單獨支持**：正式收盤股價、最終稀釋股數、完整 EV、收入分項、broker 可交易性或後續持續上市。

2026-09-25 當時下一次仍需依 AGENTS.md 的 completion 標準，核對相關 SEC completion filing／exchange security master、CIK、share class、資本結構與最近正式財報。下方為後續更新，保留本段原始查核狀態。

**2026-09-29 更新：** [CEPT 正式 8-K](https://www.sec.gov/Archives/edgar/data/2034269/000121390026076435/ea0297280-8k_cantor2.htm) 證明 07-01 交易完成、07-02 SECZ NYSE 開始交易；[Securitize Corp. 正式 8-K/A](https://www.sec.gov/Archives/edgar/data/2094496/000162828026056811/secz-20260708.htm) 佐證 CIK 2094496 與普通股／NYSE。已在 P1-02 身分主檔更正 listing；個人 investability、資本結構及真實財務 OBSERVED 仍未完成，網頁連結仍待 P1-01 原文存證與審閱。詳見 [P1-02 驗收](../../reports/p1-02-validation.md)。

## S-PLAN-03：DTC／Stellar 連接計畫

- Publisher：Stellar Development Foundation。
- Title：DTC's Tokenization Service to connect with the Stellar public blockchain。
- Source date：頁面未明示，**unknown**。
- Retrieved on：2026-09-25。
- Tier：2；需另取得 DTCC 第一方文件。
- URL：[官方 case study](https://stellar.org/case-studies/dtcc)。
- 覆蓋：計畫性 integration、預期時程與資產範圍。

**可支持**：查閱時頁面描述計畫，並表示 DTC-tokenized assets 預計於 2027 上半年在 Stellar 可用。

**不能支持**：2026-09-25 已 live、已有 material volume、任何 XLM reserve／liquidity 需求增量或 token fair value。

下一次查 DTCC 原公告、正式監管文件、部署與交易證據、首次商用／materiality；發布日期未知，需補齊或留 staging，不能用本次查阅日代替公開日。

**2026-09-30 更新：** [DTCC 2026-05-27 原公告](https://www.dtcc.com/press-releases/2026/tokenization-service-to-connect-with-stellar-public-blockchain-as-dtc-advances-multi-chain-strategy)預期 Stellar 於 2027 上半年可用；[DTCC 2026-07-15 正式環境交易公告](https://www.dtcc.com/press-releases/2026/dtcc-turns-tokenization-into-reality)明列使用 Besu 和 Canton，不能當作 Stellar 已 live。兩份仍為未存證的連結線索；Stellar-specific ledger／資產、實際 XLM demand 與 materiality 均未知。詳見 [P1-07 進度](../../reports/p1-07-validation.md)。

## S-PLAN-04：Stellar sponsored reserves

- Publisher：Stellar developer documentation。
- Title：Sponsored reserves。
- Source date：頁面未明示，**unknown**。
- Retrieved on：2026-09-25。
- Tier：2（官方技術文件）；具體帳戶與 ledger 值另以 onchain Tier 1 取得。
- URL：[Sponsored reserves](https://developers.stellar.org/docs/build/guides/transactions/sponsored-reserves)。
- 覆蓋：reserve 的承擔者、sponsorship 對 minimum balance 的作用。

**可支持**：sponsorship 可以將 reserve requirement 由受益帳戶移到 sponsor 的計算；這要求研究者辨認負擔者並避免重複計數。

**不能支持**：某個現有 issuer 實際使用量、全網淨增需求、目前價格合理性，或 sponsorship 讓全網 reserve 需求變成零。

下一次保存文件版本／更新時間、protocol version、相關 ledger entry 的原始資料；不要只用 addresses 數乘一個固定常數。

## S-PLAN-05：SEC EDGAR 資料 API

- Publisher：U.S. Securities and Exchange Commission。
- Title：EDGAR Application Programming Interfaces (APIs)。
- Source date：2024-06-06；頁面標示 last reviewed/updated 2025-04-08。
- Retrieved on：2026-09-25。
- Tier：1。
- URL：[SEC API 文件](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)。
- 覆蓋：submissions、XBRL 資料、原始文件索引與存取方法。

**可支持**：data.sec.gov 的公開資料 API 不需要 API key，提供 filings history 與 XBRL 資料；適合未來 local-first ingestion。

**不能支持**：所有想要的公司 KPI 都有標準 XBRL tag，或抓到公司 facts 就完成會計口徑核對。文件也提醒 frame 的期間可能不同。

後續 adapter 需遵守當時官方存取規範，保存 accession／context/unit／期間／發布時間；自訂 tags、segment、收入附註仍需原始申報。這裡未承諾 endpoint 永遠可用或無頻率限制。

## 尚未查核完成的優先資料

**2026-09-29 UNI 更新：** [#93 最終治理頁](https://vote.uniswapfoundation.org/proposals/93)顯示執行及八項規格，[官方部署表](https://developers.uniswap.org/docs/protocols/protocol-fee/deployments)給出主網地址，[DUNI 2025 Q4 報告](https://vote.uniswapfoundation.org/forums/7/duni-q4-and-year-end-2025-financial-statements-and-tax-update)敘述一次性 100M UNI 及首筆 5M UNI 轉出。治理頁與 DUNI 對 2025-12-27/28 日期有待 UTC 收據核對。詳細治理／帳務對照與阻塞原因見 [P1-05 進度](../../reports/p1-05-validation.md)；這些連結仍未存原文、未審閱，也沒有升級為 realized OBSERVED。

| 優先 | 任務 | 需要完成的核對 |
| --- | --- | --- |
| 1 | UNI 治理到執行 | 提案版本、execution、fee-enabled pools、TokenJar/Firepit、growth vesting |
| 2 | 三資產 security/price | 工具／權利、exchange/contract、bid/ask／時間、circulating／diluted supply |
| 3 | SECZ 財報與資本結構 | 正式 entity、完成申報、revenue、EBITDA reconciliation、FCF inputs、shares／claims |
| 4 | XLM demand measurement | reserve ownership、liquidity／collateral 去重、fees、供給、活動分母 |
| 5 | DTCC/SEC／exchange milestones | 正式原文、狀態、適用範圍、部署／live／material 證據 |
| 6 | TAM 底層 | issuer／security 名冊、權利類型、eligible float、可服務交易活動 |

未來研究應以單一研究問題圈定資料包；不要因為有官方網址就一次建立大量沒有 extraction／時間核對的 OBSERVED。
