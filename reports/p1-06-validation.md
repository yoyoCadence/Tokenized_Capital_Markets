# P1-06：SECZ 財務與資本結構原文對照

**2026-09-29｜軟體 0.1.14｜研究驗收 BLOCKED｜真實 OBSERVED 仍為 0**

## 來源與會計實體

可機讀的逐項查核線索在 [`research/secz/p1-06-filings.yaml`](../research/secz/p1-06-filings.yaml)，狀態是 `LINK_CHECKED_UNARCHIVED`。2026-08-13 的 [8-K/A](https://www.sec.gov/Archives/edgar/data/2094496/000162828026056811/secz-20260708.htm) 把營運公司 Securitize, Inc. 2026 年 Q2／H1 未經審計的合併財報放在 [Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/2094496/000162828026056811/exhibit991securitize-q22026.htm)，MD&A 放在 [Exhibit 99.2](https://www.sec.gov/Archives/edgar/data/2094496/000162828026056811/exhibit992securitizemdaq22.htm)，交易後假設性合併表放在 [Exhibit 99.4](https://www.sec.gov/Archives/edgar/data/2094496/000162828026056811/exhibit994securitizecorppr.htm)。99.4 取代 2026-07-08 原 8-K 的舊 pro forma；8-K/A 沒有全面重列原始 [8-K](https://www.sec.gov/Archives/edgar/data/2094496/000121390026076444/ea0297239-8k_securitize.htm)。

同日 [SECZ Form 10-Q](https://www.sec.gov/Archives/edgar/data/2094496/000162828026056788/secz-20260630.htm) 自述截至 **2026-06-30** 的報表是當時尚未營運、資本額名義性的 PubCo／合併前控股殼公司，**2026-07-01** 才完成交易；不可把該 10-Q 的 Q2 當作營運公司季度收入。舊 Securitize 是反向資本重組的會計收購方。這些文件 8 月申報，不構成 6 月底當時已知的資料；`checked_on` 也不是歷史首次取得時間。

## 官方收入與六分項的界線

以下皆是 **舊 Securitize, Inc. 及子公司、美元、未經審計的歷史營收**。來源為 99.1 的損益表及收入附註；「Tokenization」和「Asset Servicing」是申報的兩個類別，並非本專案的六個分析 bucket 完整拆分。

| 期間 | 官方總收入 | 官方 Tokenization | 官方 Asset Servicing | 對帳殘差 |
| --- | ---: | ---: | ---: | ---: |
| 2026 Q2（4/1–6/30） | $14,435,845 | $7,839,139 | $6,596,706 | $0 |
| 2025 Q2（4/1–6/30） | $15,262,176 | $8,874,393 | $6,387,783 | $0 |
| 2026 H1（1/1–6/30） | $33,914,311 | $18,974,344 | $14,939,967 | $0 |
| 2025 H1（1/1–6/30） | $29,296,195 | $20,136,056 | $9,160,139 | $0 |

99.1 說 Tokenization 涵蓋整合、交易、分銷及持續支援，Asset Servicing 包括記錄、轉讓處理、基金會計等。**六個分析 bucket 全部維持 `null`**：不能把名稱相似的官方兩類直接填成同義 bucket，也不能從總額任意切出交易／基金管理收入。99.2 將 2026 H1 asset servicing 的增長主要歸於 **2025-04-15** 併入 MG Stover；這不是純有機成長的證據。季度與半年不可混成 TTM。

## GAAP、adjusted EBITDA 與現金流

99.2 的 **2026 Q2** 非 GAAP 調節由 continuing operations GAAP net loss **−$21,689,202** 開始，逐筆採用申報的有號調整：

| 調整（美元） | 對 adjusted EBITDA 的有號影響 |
| --- | ---: |
| 折舊及攤銷 | +517,497 |
| 預期信用損失 | +1,315,134 |
| 股權報酬 | +537,186 |
| 所得稅 | +39,191 |
| 利息收入／費用 | −176,391／+1,105,915 |
| 股利收入 | −87,581 |
| 投資數位資產損失 | +512,615 |
| 其他淨收益 | −1,145,805 |
| SAFE、嵌入衍生品與選擇權負債公允價值變動 | +11,733,000 |
| 收購相關交易成本 | 0 |
| 一次性上市準備專業費 | +1,879,717 |
| **申報 adjusted EBITDA／重算殘差** | **−5,458,724／0** |

99.1 的 **2026 H1** 營業現金流為 **−$13,731,531**、購置設備及其他長期資產現金流出 **$557,138**；僅機械相減得 **−$14,288,669**，標為「CFO 減申報設備購置」，**不是 FCFF**。它是半年流量，不能當第二季單季或未來年度自由現金流。99.2 說 adjusted EBITDA 排除了持續性股權報酬、資本支出及營運資金需求；FCFF 的稅、營運資本、其他投資、SBC 與稀釋政策仍須完整橋接。

99.1 **2026-06-30 合併前**現金及約當現金 **$33,599,243**；客戶 escrow 資產 **$18,106,706**，對應應付 **$18,103,958**，不得整筆作 EV 可扣現金。舊公司的可轉債淨額 **$74,948,845**、SAFE 負債 **$16,127,000**、mezzanine equity **$125,984,750** 也是合併前帳面項；附註說可轉債和 SAFE 在 7 月 1 日轉股。99.4 的 **$352,566,531** 合併現金是「假定 6 月 30 日已交易」的未經審計 pro forma，不是實際 6 月 30 日舊公司現金，也不是已核定的合併後當期 EV 現金。不可把合併前負債、pro forma 現金與合併後市值任意拼接。

## 普通股與潛在稀釋

| 申報與量測時點 | 基本普通股股數 | 限制 |
| --- | ---: | --- |
| 2026-07-08 原 8-K 所述 7/1 closing | 163,218,683 | 已發行流通的 closing claim |
| 2026-08-13 10-Q 所述同一 7/1 closing | 163,265,685 | 比原 8-K 多 **47,002**，尚未釐清 |
| 2026-08-13 10-Q 封面截至該日 | 163,265,685 | 日期不同，不能當 7/1 衝突的自動修正 |
| 8-K/A 99.4 假設性 6/30 合併表 | 163,265,685 | pro forma，不是實際 6/30 basic count |

原 8-K 還列出 **835,216** 個交換權證，其可認購 **3,711,653** 股；較晚 10-Q 的對應可認購股數為 **3,711,658**，差 **5** 股。10-Q 另列交換選擇權／RSU 所涉 **3,681,510** 股、條件成立才可能新發的公司 earnout **6,250,000** 股，以及股權激勵計畫預留 **16,321,869** 股。Sponsor 的 **1,800,000** 條件歸屬股已發行且含在基本股數，不能重複加上。權證「個數」、權證 underlying「股數」、尚未發行 earnout、計畫預留容量、已發行且受限的股份和 lockup／轉售登記各有不同含義。**未提供 fully diluted 股數**；須釐清兩項同日口徑衝突、行權／歸屬／重疊、行權所得款及合併後財務後，才可計算股權值／EV bridge。

## 阻塞、驗收與下一步

`python -m engine.secz_evidence` 透過 strict YAML 與共用 v2 project validation 唯讀查核四期兩類收入、Q2 EBITDA、H1 現金橋接及股數衝突。結果是 `BLOCKED`：三項數學殘差均為 **0**，closing 股數差 **47,002**、權證 underlying 差 **5**；`diluted_shares`、`fcff`、`postclose_ev_cash` 都是 `null`。研究包不在 canonical `sources/v2` 或 observations，沒有 OBSERVED、來源人審或歷史 snapshot 變動。

1. 將上述 SEC 原文和必要附註依 P1-01 人工 staged store 擷取原檔、SHA-256、取用時間、權限、覆蓋期間及人審，才可考慮以獨立來源版本發布官方 total revenue；不能倒填申報前可知時間。
2. 查核是否有正式勘誤／後續申報釐清同日股數與權證差額；保留原 8-K 與 10-Q 各自的 claim，不以「較晚」或 pro forma 自動消除衝突。
3. 擷取合併後同日現金、債務、少數股權、優先請求權、非營運資產與可扣除性；完成獨立稀釋方法、營運資金／稅／capex／SBC 處理後，再做 FCFF 與 SECZ 市價 reverse underwriting。

**驗收判斷：** 官方總收入與兩類數字可分開對帳、六項未披露值維持未知，會計實體與期間、EBITDA 逐項調節、現金和潛在稀釋工具均明示。但原文尚未存證及人審、股數衝突待釐清、合併後 EV／FCFF 無完整同時點輸入，因此 P1-06 保持 `BLOCKED`。P1-05 亦仍 `BLOCKED`，下一個可獨立推進的包為 P1-07。

驗證：`python -m unittest discover -s tests -p 'test_*.py' -q` **167 tests OK**（本項新增五例）；`python -m engine.cli validate --demo`／`validate` 各 **94 metrics、0 issues**；`python -m scripts.g0_gate` 工程 **PASS**、研究發布 **BLOCKED**、真實 observation **0**。原 v1 DEMO 快照 SHA-256 維持 `cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e` 和 `6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`。本項新增五例涵蓋錯實體／期間、虛構六分項、數學失配、股數選邊及未審來源冒充入庫。
