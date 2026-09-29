# P1-05：UNI 原始證據最小包進度與阻塞

**2026-09-29｜軟體 0.1.13｜研究驗收 BLOCKED；實際期間對帳仍未完成**

## 治理、合約與實際轉移分層

可機讀查核線索在 [`research/uni/p1-05-governance.yaml`](../research/uni/p1-05-governance.yaml)。所有連結目前是 **LINK_CHECKED_UNARCHIVED**，沒有原始檔 SHA-256、人審及 canonical source ID；下表不建立 OBSERVED。查閱日期不冒充公開或鏈上執行時間。

| 階段 | 已查到的第一方資料 | 可支持的範圍與下一項原始證據 |
| --- | --- | --- |
| 治理規格 | [UNIfication #93](https://vote.uniswapfoundation.org/proposals/93) 顯示 `EXECUTED`；規格列出 100M UNI 送往 `0xdead`、v2 `feeTo`、v3 factory owner、40M UNI vesting allowance | 網頁可支持治理頁所述動作，不能代替執行交易收據、各個 log、當前或歷史 pool fee 設定；100M 是一次性 treasury burn，不列為 recurring protocol fee burn。 |
| 日期核對 | Agora 顯示 Dec 28, 2025 11:19 pm，未標明顯示時區；[DUNI Q4/2025 報告](https://vote.uniswapfoundation.org/forums/7/duni-q4-and-year-end-2025-financial-statements-and-tax-update) 敘述 Dec 27, 2025 執行與 burn | 相差一天；先用鏈上 block timestamp／receipt 與顯示時區解釋，再填唯一 UTC 執行時刻。 |
| 預算與分配 | #93 `approve(UNIVesting, 40M UNI)`；DUNI 報告說首筆 5M UNI 在 2026-01-05 由 treasury 轉至 Labs | allowance ≠ 已 vest ≠ 已 transfer ≠ 已出售 ≠ 新鑄幣。5M 是發行方披露，仍須 vesting state、UNI `Transfer`、treasury／recipient 帳戶與供給橋接；不直接發布為鏈上確認分配。 |
| 收費架構 | [官方部署地址](https://developers.uniswap.org/docs/protocols/protocol-fee/deployments) 列出 mainnet TokenJar、Firepit、v3 adapter、UNI Vesting、UNI token | 地址為查核入口，不能推定某日 pool 已啟用或費率。需治理 execution、fee controller／factory 的區塊狀態與 pool inventory。 |
| 費用／銷毀機制 | [協議說明](https://developers.uniswap.org/docs/protocols/protocol-fee/overview)、[資產餘額指南](https://developers.uniswap.org/docs/protocols/protocol-fee/guides/read-asset-balances)、[合約原始碼](https://github.com/Uniswap/protocol-fees) | v3 未收 protocol fees 可留在 pool，v2 用 LP token；TokenJar 流入／取出及 Firepit UNI 支付／確認銷毀各是一個不同會計步驟。跨鏈的 bridge initiation 不等於 L1 確認 burn。 |

## 完整期間的對帳要求與現有殘差

候選期間為 **2026-01-01 至 2026-03-31、Ethereum chain ID 1**；這只界定待採集的範圍，不代表已完成該季度或所有鏈的 UNI 經濟。`research/uni/p1-05-period.yaml` 將 start/end block、pool inventory、完整 logs、期初期末狀態及所有 ledger lanes 留空。執行 `python -m engine.uni_evidence`，會讀取 strict v2 project 和研究包，報告：

| 獨立原生單位帳 | 對帳式 | 本期殘差 |
| --- | --- | --- |
| 每 pool／資產 protocol fee | 期初未收 + 新 protocol fee − 已收至收費路由 − 期末未收 | `null` |
| 每資產 TokenJar | 期初 + 已收 − 已釋出 − 期末 | `null` |
| UNI fee burn pipeline | 期初待確認 + Firepit 支付 − L1 確認銷毀 − 期末待確認 | `null` |
| UNI vesting | 期初應付 + 已 vest − treasury 實際轉出 − 期末應付 | `null` |
| UNI ERC-20 `totalSupply()` | 期初 + 合約鑄幣 − 期末 | `null` |
| UNI 非 dead 地址合計餘額 | 期初 + 鑄幣 − fee 轉 dead − treasury 轉 dead − 其他轉 dead + dead 地址轉出 − 期末 | `null` |

原生單位在資產及位置間分帳；不同 fee token 不直接相加成 USD。`POOL_FEE` 的 protocol fee 不是 LP 收費總額；v2 LP token 的 underlying 須另有兌換／估值依據。TokenJar flow 是費用移轉，不是新增收入；Firepit 的 UNI 支付與 fee 資產釋出也不能各算一次 holder 收益。[UNI 合約原始碼](https://github.com/Uniswap/governance/blob/master/contracts/Uni.sol)的 `transfer` 只改地址餘額，`totalSupply` 在 `mint` 更新；所以送到 `0xdead` 需列在「非 dead 餘額」橋接，不能從 ERC-20 `totalSupply()` 扣除，也不能把非 dead 餘額稱作 circulating supply。這是目前原始碼的解讀，正式入庫仍須核對主網已部署合約及區塊狀態。

`engine.uni_evidence.reconcile_uni_pack` 對 Decimal 原生數量進行純讀取對帳：缺件是 null、非零殘差是 unallocated；每項真實數量必須引用已審閱、分類為 `CONTRACT_EVENT` 的 canonical source ID，治理提案或發行方報告不能充當鏈上數量，fixture 不能使研究期間通過。這不是 USD 報酬、現金股息或可直接輸入 v2 UNI realized yield 的 observation。

## 阻塞與下一次採集

1. 擷取 #93 的 Ethereum execution transaction、八項 calldata／receipt／event logs 與 UTC block time，釐清頁面時區及 DUNI 報告日期。核對 v2 `feeTo`、v3 factory owner、逐 pool 啟用及後續治理變更的候選期間區塊狀態。
2. 固定主網候選期間的起迄 block、完整 v2/v3 pool inventory、fee configuration、v3 `protocolFees()` 與 v2 LP token、TokenJar 各資產的期初／期末狀態，逐筆收費／收取／釋出 log；記錄 hash、log index、contract、版本與 native decimals。
3. 獨立核對 Firepit paid UNI 與 L1 最終接收／供給語義；另核對 UNIVesting 解鎖及 treasury→Labs 轉移、其他 treasury／供給事件。若擴至 L2，逐鏈追蹤 bridge 到 L1，避免重計。
4. 原檔透過 P1-01 staged store 留 SHA-256、來源分類／人審及完整期間覆蓋，逐資產逐位置填入 ledger；每個非零差額留下未分配原因或保持 `BLOCKED`。取得同期可查核 USD 價格後，才另建交易時點估值與 realized burn/distribution observation。

**驗收判斷：** 第一項「各階段不混淆」有可核查設計與來源線索；第二項「至少一完整期間 fees/burn/distribution 可對帳」**未通過**；第三項「官方提案不得代替當前合約執行與量測」已由阻塞政策強制。P1-05 維持 `BLOCKED`、`next_task` 不前移。真實 UNI financial OBSERVED 仍為 **0**。

驗證：`python -m unittest discover -s tests -p 'test_*.py' -q` **162 tests OK**（本項六例包括分帳零殘差、非零未分配額、缺件、未審來源、純算術需複核及不合法量綱）；`validate --demo`／`validate` 各 **94 metrics、0 issues**；`python -m scripts.g0_gate` 工程 **PASS**、研究發布 **BLOCKED**、真實 observation **0**。原 v1 DEMO 快照 SHA-256 維持 `cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e` 與 `6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`。本報告不升級任何 source 或 observation。
