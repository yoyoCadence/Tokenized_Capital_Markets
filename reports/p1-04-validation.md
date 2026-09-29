# P1-04：價格、供給、股本與 EV bridge 驗收

**2026-09-29｜軟體 0.1.12｜工程 DONE；真實報價、股數、財務及鏈上供給 OBSERVED = 0**

## 原則與公式

`spec/v2/market-bridge.yaml` 和 signature lock 對三種 underlying security 訂明價格、數量與財務概念。CLI `market-report --plan ...` 唯讀使用確切 OBSERVED ID；quote 須有 USD 單位、實際 timestamp、instrument/venue，SECZ 只接受 NYSE 的 `secz_nyse` 和 `secz_common`，不能用合併前 CEPT 或 tokenized form 報價冒充。UNI 使用 Ethereum 原生合約 ID，XLM 使用 Stellar native security ID；目前只支援主檔內明列的 ETHEREUM/STELLAR 報價 venue，其他交易所或 wrapped token 需先擴充並查核 identity。

| 資產 | 計算 | 口徑 |
| --- | --- | --- |
| SECZ | price × basic shares → basic equity；price × diluted shares → illustrative diluted equity | 稀釋股權值未扣 exercise proceeds，亦非 token FDV |
| SECZ | basic equity + interest-bearing debt + preferred + noncontrolling interest − unrestricted cash − nonoperating assets → EV | 限定可扣現金；受限／客戶資金不可替代，任一組件缺失則 EV Unknown |
| UNI／XLM | price × circulating supply → circulating market cap；price × total supply → total-supply FDV | total 不必等於 maximum supply；FDV 不是公司 EV 或持有人現金流 |

輸入必須在 economic/knowledge/valuation cutoff 前可知。政策指定 quote 最大秒數與結構資料最大天數；日期精度的存量在當日盤中不自動可用。報告顯示每個輸入的 as-of、publication、距報價天數及來源 ID。新來源修正或同口徑衝突不會被確切 ID 靜默選掉。股數稀釋值不可低於基本股數，總供給不可低於流通量。市值資料商的原始 OBSERVED cap 另行保存；輸出 computed − provider 差額、比例及兩者時間，超出容差必須填分析說明，說明標為 `ASSUMPTION`，尚非已核實原因。

`CURRENT_MARKET_REVERSE_INPUT` 只能由可查核的即時報價得出。`ASSUMED_PRICE_REVERSE_INPUT_NOT_HISTORICAL_EVIDENCE` 接受明示情境值、幣別、工具 ID 與理由，留下 SCENARIO 葉節點且不可稱為當時市場價格。這兩者仍只是 reverse underwriting 的輸入，不推論公允價值、預期報酬、可成交性或投資人交易資格。

## 驗證及限制

- `python -m unittest discover -s tests -p 'test_*.py' -q`：**156 tests OK**。新十一例涵蓋三資產合成報價及來源 lineage、基本／稀釋／EV、缺組件拒絕填零、流通／總量、錯工具／幣別／時點、受限現金、知識 cutoff、衝突、供應商差額、假設價格、CLI 只讀和公式鎖篡改。
- `python -m engine.cli validate --demo`／`validate`：各 **94 metrics、0 issues**。`python -m scripts.g0_gate` 工程 **PASS**，研究發布 **BLOCKED**，真實觀察值 **0**。
- 原 v1 DEMO 快照 SHA-256 不變：`cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e`、`6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`。v2 bundle `2.0-compute-bundle.6` 封存新登錄檔；舊 bundle 用原版環境重播。

所有數字只在隔離 synthetic fixture。P1-04 建立輸入契約和可稽核計算，尚未取得市場報價、SECZ 稀釋股數／淨債務或 UNI／XLM 供給的合格原文；也沒有把市場橋接結果接入 v2 thesis。下一項 P1-05 才建立 UNI primary evidence 最小包；SECZ／XLM 官方證據分別待 P1-06／P1-07，G1 未完成。
