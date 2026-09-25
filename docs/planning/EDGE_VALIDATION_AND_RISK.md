# 投資優勢驗證、決策紀錄與資本風險計畫

**PROPOSED｜2026-09-25｜沒有下單功能或目前投資建議**

## 1. 三種不同的正確

1. **計算正確**：公式與單位符合定義，輸入可以重播。
2. **預測有資訊**：比事前選定的基準預測更準、較能校準不確定性。
3. **決策有經濟價值**：在實際價格、成本與風險下，使用預測得到更合適的資本結果。

第一項不推出第二項；第二項也不推出第三項。例如正確預測業務成長，市場可能早已給出更高要求。也可能預測正確，但買入價格太高、等待太久或成本太大。

## 2. 先登錄可被推翻的研究假說

每一個策略／判斷版本建立不可覆寫的 experiment card：

| 欄位 | 必填內容 |
| --- | --- |
| identity | experiment ID、版本、作者、建立／凍結時間 |
| claim | 哪一項資訊被錯價？為何可能持續？ |
| population | 標的、eligible dates、加入／退出規則與未交易案例 |
| decision rule | 哪些條件產生研究提案、何時允許模擬、不交易條件 |
| information set | 可用來源、knowledge cutoff、預測版本 |
| horizon | 預測與投資期間、檢視／再平衡節奏 |
| outcome | 明確解析標準、資料來源、成熟日期／延後政策 |
| benchmark | 預測與投資基準各自是什麼 |
| costs | fee、spread、slippage、FX、financing、tax treatment |
| risks | 最大暴露、流動性、集中、共同因素、失敗情境 |
| analysis plan | 主要衡量值、樣本切分、相依性處理、最小可辨識效果 |
| stop/change | 否證、資料失效、版本改動與重新驗證規則 |

先寫主要 outcome，再看結果。探索性結果可產生新假說，不能冒稱舊假說已通過樣本外測試。

### 2.1 H-UNI：淨收益是否比 gross burn 更有資訊？

- 問題：在同一資訊時點，納入 distributions／dilution 的 net accrual，是否改善下一期間實際淨收益預測？
- 預測基準：上一完整期間數值、gross-only 模型。兩者使用相同資料 cutoff。
- 投資延伸：當 forward economics 與 market-required economics 差距大時，有沒有成本後的相對價值？這是第二個實驗，不能由預測比較直接得出。
- 混淆因素：crypto beta、價格本身對 USD burn/distribution 的換算、一次性 treasury burn、fee rollout、volume regime。
- 否證：優勢主要由一筆一次性事件或最新價格換算驅動，換期間／加入分配成本就消失。

### 2.2 H-SECZ：轉換效率是否有助辨認股東經濟收益？

- 問題：收入組成、續約／維護、volume monetization、FCF bridge，是否比 AUM 成長單因子更能預測後續經濟收益？
- 不披露分項時降低模型複雜度；不能以估計分項同時作輸入與真實標籤。
- 對照：持續 last-period margin、簡單 revenue trend；加入股本與 EV bridge 後看 reverse hurdle 的穩定性。
- 混淆：收購併表、一次性收入、股權稀釋、上市／融資事件、會計範圍變動。
- 否證：AUM→FCF 的轉換路徑不可識別，或已被市場價格完全反映。

### 2.3 H-XLM：採用與 native demand 的傳導是否存在？

- 首先是機制研究：明確活動／issuer 上線是否增加經去重的 reserve／inventory／collateral？
- 提前記錄預期方向、延遲、materiality threshold、控制活動與替代解釋。
- 不能用 XLM 價格上漲倒推 native demand 增加；需求 USD 值上升須分解 token 數量和價格效果。
- 傳導未證實時，投資輸出可為不估值／不交易；這是研究結論，不是系統失敗。
- 即使傳導成立，仍須另一個實驗驗證價格與持有人收益，不直接建立 fee-only DCF。

### 2.4 H-AVOID：避免哪些提案有價值？

保存所有符合事前 discovery 條件的 candidates、拒絕理由與時間。對未交易案例保留可比較報價／基準，事後報告避免損失與錯失上漲兩邊。

反事實報酬是 DERIVED，成交可行性與成本帶 ASSUMPTION；不能把假設沒有下單的交易當真實盈虧。

## 3. Forecast journal

### 3.1 四種預測使用不同評估

| 預測類型 | 例子 | 合適衡量 |
| --- | --- | --- |
| 二元事件 | 某部署在截止日已 live 且達指定 materiality | Brier score／log loss、calibration；解析來源固定 |
| 連續量／區間 | 下一財年收入、下一期 net accrual | 誤差、interval coverage／width；有完整分布才用 CRPS 等 |
| 方向／排序 | 哪個候選的門檻差距較小 | 預先定義方向／排序評估，處理 ties 與不可比較者 |
| 投資結果 | 指定 horizon 的 net return／loss event | 淨報酬、風險、基準差、尾端與資本使用 |

Brier score 不適用直接評估一個未轉成事件機率的 CAGR 數字。百分比誤差在基期接近零或負數時不穩定，需改用有定義的尺度。對 0/1 機率產生無限 log loss 的處理需在實驗前定義。

### 3.2 每個預測記錄

prediction ID、snapshot ID、context/cutoff、metric/event、horizon、point estimate／interval／probability、classification、rationale、反證、基準預測、resolution rule、expiry、dependencies。更新就是新版本；新資料更新的預測不可取代原始預測的評分。

結果以新的 resolution record 連接原 forecast。取消、無法解析、事件延後、資料不可得都保留；不能只評分成功案例。

### 3.3 校準不是裝飾

把預測機率分組比較實際達成比例，顯示樣本數與區間；小樣本不做過細分組。區間覆蓋率要連同區間寬度，不用極寬區間換取看似高準確率。多次更新同一事件高度相關，不能當成大量獨立成功預測。

## 4. 歷史重建與樣本外協議

### 4.1 Point-in-time 的最低要求

- 每個輸入有可證明的 available time；來源晚發布，最早可用時點也要晚。
- fundamentals、assumptions、rules、universe、價格、公司行動都按當時版本。
- 事後擷取資料可以作 public-information reconstruction，但不得聲稱原系統當時持有。
- delisted／failed／被排除候選也留在 universe history；不得只選今天還存在者。
- issuer entity、ticker 改名、分拆合併、bridge 遷移等以當時 instrument 定義追蹤。
- 無可靠歷史輸入時，從今天開始做 forward journal，比填補虛構歷史更有價值。

### 4.2 切分與防止過擬合

1. development period 用於發現／調參。
2. validation period 用於有限度選型，記錄看過的模型數。
3. 最終 holdout 在實驗凍結前不可用於選型。
4. rolling／walk-forward 每次只用前面資料；若 label windows 重疊，使用 gap／purge／embargo 方案並說明長度依 horizon 決定。
5. 長期報酬、同資產多預測、重疊 TTM 都有相依性；標示 effective sample limitations，不能把每日記錄量當獨立樣本數。
6. 不同參數、門檻、asset subset 與成本組合都是 trial；所有試驗結果納入選擇偏誤說明。
7. 最終 holdout 被看過後即不再「未看過」，新版本需新的 forward 驗證。

區塊 bootstrap、按事件／資產群聚分析等方法只有在樣本結構足夠時使用；僅三資產或很少事件時，不輸出假精確顯著性。統計方法不是小樣本免責符。

## 5. 預期報酬：先描述可實現財富

### 5.1 單一情境

定義買入成本 B（含買入費用）、期間內真正可得現金分配 D、可賣出淨值 L（含賣出費用／成本）：

~~~text
HoldingPeriodReturn_s = (L_s + D_s − B_s) / B_s
ExpectedTerminalWealth = sum(p_s × (L_s + D_s))
ExpectedHoldingPeriodReturn = sum(p_s × HoldingPeriodReturn_s)
~~~

假設同一投資期、初始投入，且 D 不再投資；若要再投資，必須明確建模時間／價格，或使用完整 cash-flow path。中途大量增減資則報 TWR／MWR，清楚說明各自回答什麼問題。

不能把 scenario CAGR 直接加權平均當成由 expected wealth 推得的 CAGR；IRR 在特殊現金流可能不存在或不唯一。期望值、median、downside quantile、loss probability 分別顯示。

### 5.2 資產權利的限制

- SECZ：enterprise terminal value 經 debt/cash／其他 claims 轉 equity，再除以情境 diluted shares；interim FCFF 不等於全數付給股東的股息。
- UNI：burn 不是投資人收到的現金；供給／per-token 價格效果只能算一次。若 terminal price 依賴 accrual multiple／yield，該估值選擇仍是 assumption。
- XLM：需求存量 ratio 尚不是價格函數。price mapping 未識別時保留市場價格的情境範圍，不輸出看似基本面估值的精確 expected return。

expected return 是 SCENARIO／DERIVED with assumptions，不是 FORECAST FACT。機率未校準時明示 subjective，缺關鍵機制可拒算。

## 6. 永久損失與風險

### 6.1 永久損失需先操作化

與暫時最大回撤分開定義：

- 法律／經濟權利永久消失、持有人經濟機制被撤除或嚴重稀釋。
- business economics 不再足以支持指定 capital recovery。
- protocol/chain/security/custody 事故造成不可恢復損失。
- 在預先定義 horizon 內回收本金的經濟能力顯著毀損。

最後一項需要 horizon、折現／通膨／幣別、回收定義。市場價格一時下跌不自動符合；市場價格上漲也不證明永久風險消失。

每個情境保存 loss severity、probability 假設、evidence、可採取的 mitigation 與 recovery mechanism。尚未校準時不稱精準「破產率」或「永久損失機率」。

### 6.2 投資政策書 IPS（未填就不能進真實 pilot）

- 基準幣別、本金／可承擔試驗損失、資金用途與流動性時間表。
- 可以交易的 instrument／venue／jurisdiction；custody 與帳戶限制。
- 單一部位、整體產業、crypto beta、共同 tokenization exposure 上限。
- gross/net exposure、槓桿、融資、最大資金占用與最大流動性期限。
- drawdown review、永久損失 event、資料過期、模型故障各自的處理。
- 對誰負責、谁能批准變更、如何記錄下單與 reconciliation。

初期 pilot 可提議 long-only、無槓桿、人工下單，但只是待採用的試驗設計，不是此刻配置建議。實際比例／金額由使用者政策與流動性資料決定，本計畫不代填。

### 6.3 三種停止／檢視機制分開

| 類型 | 觸發 | 系統行動 |
| --- | --- | --- |
| 資料／模型故障 | fixture、來源衝突、壞快照、價格過期 | 停止受影響研究發布／新提案，保留最後合法版本與故障提示 |
| Thesis 變化 | economics／治理／權利與先前要求不符 | 更新 severity 與反證，要求重新研究 |
| 資本政策 | IPS 暴露、流動性、損失條件觸發 | 產生人工處理任務；是否減倉由政策與具體授權決定 |

五個 thesis states 不變，不與 BUY/HOLD/SELL 對應。資料故障也不應直接把 thesis 判成 INVALIDATED。

## 7. 可執行性與成本模型

每一筆模擬決策包含：

- 可下單時間：訊號產生之後、在可交易時段；不能用當天已不可取得的 closing price。
- bid/ask、notional、depth／participation、預計成交時間、venue。
- commissions、交易稅費、spread、impact、gas、bridge／withdrawal、FX、funding／borrow（若政策允許）。
- 交易所與鏈上成交延遲、failed transaction、halt／停牌／交易限制、partial fill。
- custody／counterparty risk 與資金可移動性；paper model 不能假設到處瞬間搬錢。

缺 depth 時用有理由的保守成本區間，不聲稱精準 fill。價格是 last trade 不等於可成交 bid/ask；TAM 大也不代表某資產流動性足夠。

稅負依使用者實際帳戶／地區與合法資料設定；未設定就標 **稅前、稅務影響未知**，不能把它叫完整稅後淨利。報告分層列 gross、交易成本後、融資／FX 後、適用稅後與研究成本後。

## 8. 模擬組合、基準與歸因

### 8.1 三個日誌不得混合

- research journal：當時知道什麼、判斷與反證。
- paper ledger：假設規則與可行成交下的持倉／現金／費用。
- actual ledger（P4 才有）：broker/venue 的真實 fills、公司行動與資金流。

禁止把某些實際成功交易與其他模擬成功交易拼成一条績效。所有帳本以 base currency 對帳；原幣與 FX 仍可追蹤。

### 8.2 預先固定基準

先依 IPS 選擇合理政策基準，再設定少數診斷基準：

- cash／適用短期無風險代理的 opportunity cost，需來源與可投資性。
- 相同可交易 universe 的簡單持有或固定再平衡策略。
- 用於解釋 equity／crypto／市場風險的參考指標。

初始 weights、rebalance、cash treatment、成本、可知性與 eligibility 全部預先登錄；不事後挑一個最弱基準。股票與 crypto 混合組合不能任意只和單一股票指數比較後就宣稱 alpha。

### 8.3 最小績效報告

period returns、cumulative net P&L、TWR/MWR（適用時）、drawdown、volatility、turnover、cash exposure、交易成本、集中與流動性；benchmark-relative return、beta／因子解釋（樣本足夠才估）、unrealized/realized 拆分。

歸因至少拆：asset exposure／持倉期間、交易時點與實際成本、FX、公司行動／分配、研究選擇。短期大漲主要由行情 beta 解釋時，據實呈現，不能全部歸功模型。

## 9. 門檻、停止、擴大

### 9.1 G3 操作驗收

- 所有 decisions 在結果前封存；每個 paper trade 可重播。
- 成本／資金／公司行動對帳通過；missing prices 不硬補。
- baseline、cutoff、horizon、模型版本不變；改版另開實驗。
- 8–12 週只檢查流程可靠性、負擔與使用價值；未成熟的長期預測留 pending。

### 9.2 優勢證據審查

主要效果量先定義，報 uncertainty、獨立樣本限制、試驗次數、成本敏感度、時間／regime 子樣本。結論只能是支持、反對或尚無法判定，而且限定在測試範圍內。

沒有通用的「20 筆交易／60% 勝率／Sharpe 大於某數」通關法。要依 horizon、effect size、相依性與資本用途先規劃所需證據。小樣本不為了湊筆數縮短持有期或頻繁交易。

### 9.3 G4 有限實證

操作通過不表示已證明 alpha。若仍不確定，使用者可另行同意以可承受的試驗預算收集執行證據；須明示不確定、單筆與整體限制、停止規則，不擴張為完整資本配置。

放大之前至少回答：

1. 成果有多少來自行情暴露、少數離群事件與運氣？
2. 新資料、較保守成本、不同 regime 下是否仍有經濟合理性？
3. 真實／模擬差異何在？容量增加會如何改變滑價與退出時間？
4. 使用者承受的尾端與集中風險是否符合 IPS？
5. 研究與營運成本有沒有超過改善的收益／節省時間？

### 9.4 專案停止與縮小範圍

若找不到可獲得資料、無法區分 holder capture、長期沒有決策價值，停止對應模型／擴展。保留引擎作可追溯研究筆記亦可。不能用「還需要更多 dashboard 功能」無限延期對經濟價值的檢驗。

## 10. 第一個驗證實驗的建議

在 G0–G2 通過後，先做 **UNI 的 realized gross vs net accrual 預測比較**，不直接開始多資產量化交易。

產物：一個凍結 experiment card、一次 primary evidence reconciliation、同資訊集的兩個簡單預測、明確解析期間、下一次到期結果。成本低、對核心命題直接、可否證；若連這一步都無法可靠做，增加估值精度與自動下單不會改善結果。
