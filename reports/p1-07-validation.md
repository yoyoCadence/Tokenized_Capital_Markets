# P1-07：XLM 原生需求與 DTCC 里程碑證據

**2026-09-30｜軟體 0.1.15｜研究驗收 BLOCKED｜真實 OBSERVED = 0**

## 網路活動與原生 XLM 持有是不同量

官方查核線索在 [`research/xlm/p1-07-demand.yaml`](../research/xlm/p1-07-demand.yaml)，均為 `LINK_CHECKED_UNARCHIVED`。Stellar [XLM／minimum balance 說明](https://developers.stellar.org/docs/learn/fundamentals/lumens)、[sponsored reserves 說明](https://developers.stellar.org/docs/build/guides/transactions/sponsored-reserves)、[帳戶欄位](https://developers.stellar.org/docs/data/apis/horizon/api-reference/resources/accounts/object)與[交易費用說明](https://developers.stellar.org/docs/learn/fundamentals/fees-resource-limits-metering)是當前機制文件；沒有把動態文件的查閱日期冒充早期公開日期，也沒有把文件上目前的 **0.5 XLM** base reserve 用於尚未選定的歷史 ledger。

對同一 Stellar 公網 ledger，每一個原生 XLM 帳戶餘額只算一次。單一帳戶的最低餘額是 `(2 + numSubEntries + numSponsoring − numSponsored) × 該 ledger 的 baseReserve`；可用於賣出的部分另扣 native XLM selling liabilities。最低餘額和 selling liabilities 是該帳戶餘額的**占用／承諾**，不是可再加到餘額的額外 XLM。`numSponsoring` 增加贊助者的需求，`numSponsored` 抵消被贊助帳戶的相應要求；需同 ledger 的贊助者與被贊助者帳戶及完整邊界，不能只把雙方報告的 reserves 相加。`RESERVE`、`SPONSORED`、`OPERATING`、`LIQUIDITY`、`COLLATERAL` 是用途標籤：同一庫存可同時被描述為流動性與抵押，不能按標籤重複求和。

候選完整期間定為 **2026-07-01 至 2026-08-31**，目前尚未採集起迄 ledger、全網 account／contract position inventory、XLM balance、贊助 counter、實際費用或可歸因地址。因此這不是對全網 XLM 需求、DTCC 帳戶或期間活動的測量。網路中的 tokenized asset 發行／支付可在沒有同比例 XLM 鎖定增量的情況下增加；轉帳流量可反覆轉動同一批餘額，gross flow 不是某一日 demand stock。原生 XLM 轉帳也不是所有資產的 transfer volume；self transfer、內部／bridge、發行與贖回須分開。基本 inclusion fee、擁塞出價與 smart-contract resource/write fees 不可用單一「每筆 100 stroops」乘所有 transactions 推論實繳總費用。供給、費用量及 USD 價格均待可審原始數據。

## DTCC 的 chain-specific 狀態

| 命題 | 第一方原文與事件日 | 判斷 |
| --- | --- | --- |
| DTCC 與 SDF 計畫接 Stellar | [DTCC 2026-05-27 公告](https://www.dtcc.com/press-releases/2026/tokenization-service-to-connect-with-stellar-public-blockchain-as-dtc-advances-multi-chain-strategy)；預期 DTC tokenized assets 於 **2027 H1** 可在 Stellar 使用 | **PLANNED**，不是 Stellar 已上線；資產類別與實際使用待後續核對 |
| DTC tokenized assets 用於正式環境交易 | [DTCC 2026-07-15 公告](https://www.dtcc.com/press-releases/2026/dtcc-turns-tokenization-into-reality)；公告明說轉換在 **LFDT Besu 與 Canton** | **LIVE_OTHER_NETWORKS**，不能提升為 `LIVE_STELLAR` |
| DTC 在 Stellar 的 production 交易 | 此包沒有 DTCC 官方 Stellar-specific deployment、交易 hash／完整 ledger 核查 | **UNKNOWN**，需原文及鏈上實際交易證據 |
| Stellar 上 DTCC 用量對市場具 materiality | 缺預先訂明的門檻、期間、可比總體分母和 Stellar-specific 分子 | **UNKNOWN**；不能引用 DTCC 全市場保管量當 Stellar 活動 |

DTCC 的正式環境活動屬其多鏈計畫的進度，但 7 月展示不是 Stellar 上的證據。即使未來取得 Stellar 上 DTC assets 的發行與交易，仍需逐帳戶區分平台營運 XLM、贊助最低餘額、抵押、流動性來源、重複使用和替代資產；規模、增量 XLM stock 與 XLM 價格之間沒有已辨識的係數。`transmission.classification` 維持 `ASSUMPTION`，`dtcc_attributable_xlm_stroops`、`incremental_native_demand_stroops` 和 `price_effect_usd` 均是 `null`。

## 去重工具與缺口

`python -m engine.xlm_evidence` 使用 strict YAML 及共用 v2 project validation 唯讀讀取包。帳戶列必須在同一 ledger、用整數 stroops、各自有唯一 account ID 和該 ledger 的 base reserve；真實列要有已審來源 ID。合成範例中兩個帳戶分別有 100 與 25 stroops；一個帳戶同時標成 `RESERVE`／`LIQUIDITY`／`COLLATERAL`，贊助責任在另一帳戶的 `numSponsored` 抵消。兩帳戶去重後的**合成樣本**總餘額 125、最低餘額 35、native selling liabilities 15、可用餘額 75 stroops；這四個數不是可直接相加的四筆持幣，也不是實際 Stellar 主網數值。fixture 永遠標 `BLOCKED`，不可冒充實盤需求。

真實研究包的 accounts、contract positions 及期間活動全空。當前讀取結果：選定帳戶存量、全網 native demand、期間 transfers、DTCC 增量 XLM 和價格效果均為 `null`。需要：

1. 依 P1-01 擷取原始 DTCC 公告及技術文件，保留 SHA-256、實際取得時間、來源期間、人審；對動態文件保留版本／發布時間未知的限制。
2. 鎖定完整候選期間的起迄 ledger 與公網原始狀態。重建帳戶和合約中可識別的 native XLM 庫存、贊助對應、當期 base reserve；驗證全網或樣本涵蓋率與同筆 custody／claim 不重計。
3. 對活動逐 operation／transaction 去重，標記 self／內部／轉換／外部經濟轉移，分開原生 XLM 流量、其他資產流量、實繳 classic inclusion 與合約 resource 費用；不從平均費率推 total。
4. 若 DTCC 宣布 Stellar deployment 或 usage，取得鏈別、資產、帳戶權利與原始 hash；先預定 materiality 的門檻和同期間分母，再討論需求增量。價格映射另需供給、velocity、替代清算資產及持有人行為的模型與資料。

**驗收判斷：** 已定義 reserve／sponsorship／liquidity／collateral 去重帳，將流量、存量和價格效應分開，且 DTCC planned／其他鏈 live／Stellar live／material 各自有狀態。缺全網原始 ledger、人審、鏈別歸因及重大性量測，故 P1-07 `BLOCKED`，無真實 XLM OBSERVED；P1-09 G1 仍不可發布。下個獨立工程包 P1-08 可處理 freshness／coverage 報告，但不能替代 P1-05～07 的原始證據。

驗證：`python -m unittest discover -s tests -p 'test_*.py' -q` **172 tests OK**（新增五例）；`python -m engine.cli validate --demo`／`validate` 各 **94 metrics、0 issues**；`python -m scripts.g0_gate` 工程 **PASS**、研究發布 **BLOCKED**、真實 observation **0**。原 v1 DEMO 快照 SHA-256 保持 `cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e` 和 `6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`。新增五例涵蓋 sponsorship 的持有責任轉移、多標籤去重、同 ledger／唯一帳戶、DTCC 其他鏈與 Stellar 狀態隔離、真實來源及期間流量阻塞。
