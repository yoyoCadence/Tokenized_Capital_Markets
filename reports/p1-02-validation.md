# P1-02：Entity/security master 與交易資格查核

**2026-09-29｜軟體 0.1.10｜身分主檔工程與連結查核 DONE；財務 OBSERVED 仍為 0**

## 實體、權利與工具

`spec/v2/identity-master.yaml` 區分 Uniswap protocol／Uniswap Labs、Stellar network／Stellar Development Foundation、Securitize Inc.／上市發行人 Securitize Corp.／前身合併對手 CEPT。UNI 是 Ethereum chain ID 1 的合約代幣；XLM 是 Stellar 原生資產，不以同名 ERC-20 或基金持有量取代；SECZ 是 Securitize Corp. 普通股，NYSE 股票與發行人 tokenized form 為**同一 underlying class 的不同工具**，後者沒有核准的鏈上合約地址或已驗證的台灣投資人入口。CEPT 的普通股是另一證券，不能把合併前價格直接當 SECZ 歷史價格。

已核對 [CEPT 8-K](https://www.sec.gov/Archives/edgar/data/2034269/000121390026076435/ea0297280-8k_cantor2.htm) 記載 2026-07-01 合併完成與 07-02 SECZ 於 NYSE 開始交易；[Securitize Corp. 8-K/A](https://www.sec.gov/Archives/edgar/data/2094496/000162828026056811/secz-20260708.htm) 記載 CIK 0002094496、普通股、`SECZ`／NYSE；[發行人公告](https://investors.securitize.io/news/news-details/2026/Tokenizing-SECZ-Securitize-Brings-Its-Own-Public-Stock-Onchain-at-Listing-Day/default.aspx) 說明 tokenized form 的持有人資格限制。故原本 `listing_status: unverified` 已過時；更正為 NYSE 已上市，`investable` 仍為 unknown，因券商、司法管轄區與用戶身分未查核。這不構成價格、股數、EV 或業績的觀察值。

[Uniswap 官方 token list](https://github.com/Uniswap/default-token-list/blob/main/src/tokens/mainnet.json) 顯示 UNI chain 1 合約 `0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984`、18 decimals；[Stellar 官方技術文件](https://developers.stellar.org/docs/learn/fundamentals/stellar-data-structures/assets) 區分原生 lumen 與有 issuer 的資產，使用七位小數。這兩個動態文件未取得可靠的原始 publication 日期，因此 ticker 與 UNI 合約的有效起始日期留 null，歷史日期查詢回 Unknown，不用後來查看的頁面推定當時本系統已知。所有 URL 為查閱過的 **LINK_CHECKED_UNARCHIVED** 研究參考；尚未依 P1-01 留原文 SHA-256 和人審，不能當作 canonical financial source。

## 可驗證的邊界

`python -m engine.cli identity --asset SECZ` 顯示研究核心、上市、value capture、資料 readiness、用戶交易資格五個維度；用戶資格為 null／UNKNOWN，發表門檻仍 false。`python -m engine.cli identity --namespace NYSE --symbol SECZ --as-of 2026-07-02` 可依交易所和生效日期定位證券；07-01 為 Unknown。此查詢是 **PUBLIC_RECONSTRUCTION_ONLY**，不聲稱系統在 07-02 已擁有該證據。issuer tokenized form 的有效起始未驗證，因此同日查詢保持 Unknown。CLI 只讀、載入使用 strict YAML、未知欄位或模糊 alias／不一致外鍵會拒絕，不能直接把研究核心或上市狀態改成個人可交易。v2 audit bundle `2.0-compute-bundle.4` 收錄主檔位元組並離線重播；舊 bundle 需其原版本程式環境。

回歸：`python -m unittest discover -s tests -p 'test_*.py' -q` **136 tests OK**；`validate --demo`／`validate` 各 94 metrics、0 issues。測試涵蓋同名跨 venue、合併前後與未知開始時間、沒有個人交易資格、重複 alias／錯誤連結／URL query／直接升級資格拒絕及只讀行為。舊 DEMO snapshots 不重寫；v1 計算和金融來源未修改。

## 尚待處理

特定投資人的券商可用性、法域／KYC、NYSE 股份與 tokenized 持有方式、正式稀釋股數／企業價值、UNI 的已實現持有人價值、XLM 的實際需求均未核實。P1-03 數據 normalization、P1-04～07 三資產真實研究證據、P2-08 promotion workflow 待實作；G1 與決策級研究仍 BLOCKED。跨鏈同名代幣或第三方標成 SECZ 的合約不得以 ticker 自動對應本主檔。
