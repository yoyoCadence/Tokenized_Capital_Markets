# 資料、經濟模型與重播規格 v2 草案

**PROPOSED｜2026-09-25｜本文件欄位與 API 尚未實作**

目的：使「某個數值在什麼時候、基於什麼證據、代表哪個經濟範圍」具有可執行的契約。四種分類、Canonical Principles 與現有歷史保留。

## 1. 資料模型：分類與上下文是不同維度

| 維度 | 擬議值／欄位 | 用途 |
| --- | --- | --- |
| classification | OBSERVED / DERIVED / ASSUMPTION / SCENARIO | 唯一四種資料分類 |
| fixture | true / false | synthetic 品質旗標；true 不能進研究發布 |
| economic_scope | REALIZED / RUN_RATE / MODELED_HORIZON / REVERSE_REQUIREMENT | 防止現在、年化與未來混用 |
| economic_period | basis、start、end、fiscal_year、fiscal_quarter | 存量／流量、財年與比較期 |
| knowledge_time | published_at、first_seen_at、ingested_at、availability_basis | 防止 look-ahead |
| valuation_time | quote timestamp、venue、timezone、cutoff policy | 市價與資本結構對齊 |
| quality | completeness、freshness、conflict、measurement、mechanism | 不用單一 confidence 掩蓋缺口 |
| eligibility | research-ready / valuation-ready / executable 的獨立結果 | 不是 classification 或 thesis state |

scope、quality、eligibility 的擬議名稱可以在 schema 設計時調整，但語義與限制須保留。UNKNOWN 是值／品質狀態，不新增為第六個 thesis state。

### 1.1 Metric 與 record

- metric concept：描述「什麼量」，例如 protocol fee USD、總收入、流通供給。
- record：一次證據／假設／情境版本，具唯一 ID、classification、日期、unit、value。
- input role：模型指定使用 realized effective fee 或 scenario effective fee；不能把同一 assumption record 改成 observed。
- derived result：保存 formula ID/version/hash、實際選用 record IDs、context、computed_at、quality、完整 DAG。
- 同一數字由不同來源提供仍保留各 record，不能只留下其中一個值相等的來源。

### 1.2 Unknown 的語義

區分 NOT_DISCLOSED、NOT_YET_RETRIEVED、NOT_APPLICABLE、STALE、CONFLICT、INCOMPATIBLE_PERIOD、MODEL_NOT_IDENTIFIED。它們是 missing reason，不是新資料分類。

0 必須有真實的零值證據。未披露收入分項、未測得需求或未實現的計畫，不能填 0。若一個公式無法計算，顯示最小缺失依賴集合，並說明可做哪些有條件敏感度。

## 2. 雙時間與歷史可知性

### 2.1 至少保存的時間

| 欄位 | 意義 |
| --- | --- |
| period_start / period_end | 金融事實涵蓋期間 |
| as_of_at | 存量量測、鏈上 block 或報價時間 |
| published_at | 來源公開時間；不可用 quarter-end 代替 |
| first_seen_at | 本系統第一次取得該版證據的時間 |
| ingested_at | canonical ledger 接受時間 |
| effective_from | 假設／規則／合約政策開始適用時間 |
| supersedes_id | 哪個同語義、同經濟期間版本被新證據修正 |
| knowledge_cutoff | 本次研究允許使用資訊的最晚時間 |

所有 instant 使用帶 timezone 的 ISO 8601，內部 normalize 到 UTC；同時保留原 timezone 與日期精度。只有日期的來源不得假造分鐘級時間；使用明示的保守可用時間政策或禁止 intraday 回放。

### 2.2 兩種查詢模式

1. **AS_KNOWN_BY_SYSTEM**：published_at（若可驗證）及 first_seen_at 都不得晚於 cutoff；回放真實研究／決策。
2. **PUBLIC_INFORMATION_RECONSTRUCTION**：以可證明的發布時間重建「公開可知」，允許事後下載，但必須有原始歸檔／申報 timestamp；不聲稱本系統當時真的看過。

兩者不得混合計算同一樣本外績效。首次取得時間永遠不回填成歷史日期。缺可靠 availability 時，不能進歷史策略樣本；可留在當前研究。

### 2.3 版本選取

先依查詢模式與 cutoff 篩選「可知」版本，再對相同 metric/entity/period/scope 處理 supersession；保留尚未解決的同時有效衝突。價格用最近一筆符合最大陳舊期限的合法 quote；不把過期價格默認為現在。

**必測案例**：Q1 原始申報在 5 月、重述在 8 月。6 月 as-known 查詢只可用原始申報；9 月可以用重述；兩次 snapshot 各自可重播。

## 3. Source 與 evidence archive

每一版來源要求：

- source ID、supersedes source ID、URL／可解析鏈上 locator、publisher、title、source date、retrieved_at、tier、covered metrics。
- document kind：filing／order／contract event／official release／governance proposal／analytics 等；tier 不代替內容性質。
- raw artifact content hash、MIME、檔案大小、encoding、原文 locator（頁／表／cell／段落／tx log）。
- fetch status、HTTP metadata（若可用）、parser version、extraction method、reviewer、review outcome。
- data license／可否存全文／可否再散布／存放位置。未確認時用 metadata 與允許的短摘要，不將受限全文放公開 GitHub。
- source publication date 不明時留在 staging，記 unknown；不得為了滿足 required field 填 retrieved date。

### 3.1 來源與 observation 不是同一層

發布稿說「預計推出」可以支持 OBSERVED 的「某公司曾在某日公告」這個事件事實；不能支持「服務已 live」或「產生某收入」的 observation。

SEC、exchange、chain 是高優先來源；其中的 forward-looking statements 依然是 forward-looking。Tier 1 不自動使每個內容為 realized fact。

### 3.2 來源衝突

衝突組包含所有 record、定義／時間／範圍差異、差值、解決政策、reviewer 與resolution ID。可以以更適合的 audited／同口徑資料作選用，但須留下理由及未選資料；不靠「較新」或「較高 tier」一律覆蓋。

## 4. Normalization、unit 與 accounting basis

原文直接量測存 OBSERVED；縮放、FX、年化、四季加總等計算存 DERIVED，保留 normalization formula/version。不要在 parser 裡做不可追蹤的財務計算。

- USD、native token、shares、operations 分開；percent/fraction/bp 必須明示 conversion。
- 金額明示 currency、scale、nominal basis；跨幣別需 FX quote 來源／時點。
- AUM／reserve／供給是 stock；收入／費用／交易量是 flow，指定完整期間。
- TTM 必須由兼容四季或官方 TTM 提供；若從 YTD 相減取得季度值，完整保存依賴，不與完整年度重複加總。
- 同公司變更 fiscal year、53 週年度、合併前後範圍，都需 period/comparability flags。
- GAAP／IFRS／管理層調整、consolidated／segment、gross／net、continuing operations 分開。
- issuer AUM、managed AUM、serviced AUM、tokenized assets、流通市值不可互換。
- 公式做 dimensional validation 與 scope validation；合理數值不代表量綱正確。

## 5. 可交易實體與市場輸入

建立 entity/security master：法律實體、協議、網路、股票／token、交易工具與持有人權利分開。ticker 只是帶有效期間的 alias。

股票需 CIK／exchange／share class／幣別／corporate action／基本與稀釋股數；token 需 chain ID／contract／decimals／bridged representation／circulating 與 total supply 定義。避免同名資產或 wrapped 代幣重複計數。

市場輸入：

- price、bid/ask、venue、timestamp、可用交易時段、延遲與資料 license。
- market cap = price × 對應股數／流通量；資料商 market cap 與自己推導值分別保存並對帳。
- 股票 EV bridge：equity value + debt + preferred + noncontrolling interest − 可扣除現金／非營運資產；明示每一項與日期，不能把受限／客戶資金一律當可用現金。
- equity fully diluted valuation 與 token FDV 的概念不同，UI 名稱不得混淆。
- 報價與股本資料日期不同，顯示使用的最近可知結構與 gap，而非假造同日值。
- 缺價格時只能做「假設價格」的 SCENARIO reverse；不得標 current market reverse。

## 6. UNI 模型 v2

### 6.1 四張必備表

1. **已實現 fee／burn ledger**：期間、chain/version/pool、LP fees、protocol portion、TokenJar 入帳／取出、burn transaction、對帳殘差。
2. **供給與分配橋接**：期初 total/circulating、鑄幣、銷毀、treasury→流通、vesting/unlock、其他調整、期末。
3. **forward scenarios**：各資產類／venue 的 volume、effective protocol fee、capture routing、成本、growth distribution。
4. **reverse requirements**：由當前市場分母反推 required accrual/share，區分 standalone 與 incremental。

### 6.2 經濟定義

- 預算授權額、已 vest、已轉出、已出售、增加 total supply 是不同事件。20M UNI/year 不能直接被標成實際已分配或新鑄幣。
- LP fee ≠ protocol fee；Protocol revenue ≠ 已 realized burn；contract 中的 accrual 也不等於 holder 已收到現金。
- 同筆 TokenJar inflow、取出與 burn 對應的 economic value 只算一次。對帳不平則保留 unallocated/residual，不能硬湊。
- burn／分配同時保存 native units 與 USD 的計價政策。用交易時點價格估 realized USD，與用 current price 評估 budget 的情境分開。
- treasury 轉出未增加 total supply 也可能增加可交易供給；經濟分配成本假設與 supply accounting 分列，不把兩者重複扣款。
- sequencer gross fees、L1 成本、其他分成、net accrual 分開；未實現 MEV／新版本 fee 只在 scenarios。

### 6.3 公式與版本策略

保留 v1 standalone regression：

~~~text
RequiredShare_standalone =
  (MarketCap × RequiredYield + GrowthDistributionValue)
  / (ModeledEquityAUM × Turnover × OnchainShare × AMMShare × EffectiveProtocolFee)
~~~

新版本另列：

~~~text
RequiredShare_incremental =
  (RequiredNetAccrual + GrowthDistributionValue + OtherDilutionCost − OtherNetAccrual)
  / EquityFeeOpportunityAt100PercentShare
~~~

分子／分母需同一 forward horizon 與幣別。required share > 1 顯示該情境不可能由該收入來源單獨滿足；分母 0 為不可求解；分子 < 0 表示其他收益已覆蓋要求，不顯示「負的可達市場占有率」。可另外呈現 raw hurdle 與 floor-at-zero 的 remaining need，兩者各有定義。

REALIZED net accrual 計算與分類須先通過對帳；RULE 的 net_burn_yield 只取指定實現期間。future opportunity 不能被加到 realized burn yield。

### 6.4 UNI 預期報酬擴充的邊界

若未來採用 accrual/yield 估值，只能作清楚標註的 SCENARIO：治理能否持續、fee 可分配性、要求收益率、供給分母與終值假設均需獨立。burn 可能影響 per-token 分母或供給模型，不能又當現金股息加一次。沒有可信 price mapping 時，只輸出反向門檻與收益強度。

## 7. SECZ 模型 v2

### 7.1 Revenue decomposition 與 disclosure limits

六個分析 bucket 保留：Tokenization、Asset Servicing、Transaction、Issuer SaaS/Maintenance、Fund Administration、Other。增加「官方總收入」與 reconciliation：

- 如果六分項均有同口徑證據，可以 sum 並對帳。
- 如果只披露總收入，觀察總收入可用，未披露分項為 unknown。不能任意分配百分比。
- 官方 segment 與六 bucket 無法一對一時，保存 mapping assumption 和未分配額；不強稱唯一分解。
- recurring／one-off、客戶集中、價格／量、organic／收購併入，能取得多少就支持多少。

### 7.2 從成長到股東收益

~~~text
Revenue → GrossProfit → OperatingProfit
        → CashTaxes + WorkingCapital + Capex + OtherCashAdjustments
        → FCFF

EnterpriseValue → EquityValue bridge → FullyDilutedShares → PerShareOutcome
~~~

EBITDA 到 FCFF 的每個調整有來源或假設。SBC 的現金流處理、未來 share count 與回購政策必須一致；避免把同一稀釋成本扣兩次或完全忽略。

資本結構包含適用的 warrants、convertibles、earnouts、options、lockups、redemption／merger 時點；它們是否適用仍要查實際申報，不預設存在或數量。

### 7.3 Reverse underwriting 的兩層

v1 簡化式保留作「未折現終值門檻」：

~~~text
RequiredFCF_v1 = CurrentEV / TerminalMultiple
RequiredRevenue_v1 = RequiredFCF_v1 / TargetFCFMargin
~~~

v2 使用有時點的現金流定義，例如 forward terminal multiple：

~~~text
EV_0 = sum(FCFF_t / (1+r)^t, t=1..N)
       + [M_forward × FCFF_(N+1)] / (1+r)^N
~~~

以 root solver 反推 revenue growth／margin path；不要把 FCFF_N 與 FCFF_(N+1) 混用。若改用 trailing multiple，另立公式版本。把 terminal value 的 equity bridge 與當期 EV 的 bridge 都說清楚。

檢驗 r、M、margin、growth、稀釋、現金需求共同變動。計算沒有唯一解時顯示可行集合／邊界，不把其中一個解稱為市場唯一預期。負現金流／負基期不得硬算 CAGR 或套正倍數估值。

## 8. XLM 模型 v2

### 8.1 兩層各自有證據

Network layer：RWA 類型、stablecoin supply、外部經濟 transfers、operations、issuers、addresses、DTCC activity。

Native layer：reserve demand、liquidity inventory、collateral、settlement operating balances、其他可識別鎖定 XLM、fees、供給／分配。

Stellar 的採用與 XLM 持有人價值之間保持一條待驗證的經濟傳導邊。

### 8.2 需求口徑

- 以唯一 ledger entry／account balance 的權利與用途對需求存量去重；一筆 XLM 同時被稱為 collateral 和 liquidity 不能加兩次。
- sponsored reserves 改變誰持有／承擔 reserve；不必然消滅全網需求，也不能把 sponsor 與被贊助帳戶需求重複相加。官方機制來源見 [來源筆記](RESEARCH_SOURCES.md)。
- locked stock 的變動與轉帳 gross flow 分開；同一庫存可以服務很多流量，velocity 是假設或可測 ratio。
- network fee USD 用作操作成本診斷。需指定 classic operations 與 smart-contract resource fees 的覆蓋，不能把簡單平均 fee 模型套到所有活動。
- NetworkFeeValue = Operations × AverageFeeXLM × XLMPrice 的適用操作集合與 period 明示；有直接 fee totals 時先對帳。
- NativeDemandGrowth / NetworkActivityGrowth 只在兼容期間與明確分母時報告。分母近 0 或為負需警告／另作分解，不能用極端 ratio 當強烈訊號。
- DTCC planned/live/material 各自需要證據；materiality 須先定義可量測門檻、期間與總體分母。

### 8.3 Price mapping 的研究門檻

reserve／流動性需求增加不能直接乘上某倍數變成 fair value。未來模型至少要描述庫存需求、可用供給、持有人流動性偏好、velocity、替代資產與價格回饋。若參數不可識別，標「估值不可識別」，依然可完成 adoption／capture monitoring。

## 9. Bottom-up TAM 與可服務交易量

建立 security/issuer cohort，不用全球股票市值一次乘上假設就得到 fair value：

~~~text
Eligible underlying assets
→ legally/operationally tokenizable subset
→ issued tokenized ownership/exposure
→ available float
→ eligible venues and holders
→ economically meaningful traded volume
→ captured protocol/company revenue
~~~

各階段的限制可受司法管轄、轉讓許可、custody、distribution、liquidity、issuer economics 影響；這是研究問題，不預設法規結論。橋接／wrapped representation、基金持有股票與股票本身需防 double count。Transfer volume、mint/burn、內部移轉、wash/self activity 與 genuine trading volume 分開。

TAM、可服務市場、實際捕獲流量與資產價值永遠是不同欄位。

## 10. Sensitivity、rules 與 graph

### 10.1 Sensitivity

保持所有既有參數。新增兩類輸出：

- local one-at-a-time／雙參數 matrix：定位最敏感假設，固定基準與 horizon。
- joint scenarios：處理 fee 與 share、成長與成本／稀釋、margin 與競爭之間的相關性。初期手工一致情境即可，不用假精確 Monte Carlo。

未校準的機率均為 ASSUMPTION；seed、sampling method、dependency constraints 與 rejected draws 可重播。超過資料支持的精度少顯示小數位。

### 10.2 Thesis rules

沿用五種 severity states，另存 evidence status。資料不足不能 HEALTHY；部分規則觸發時顯示該最高 state，並清楚列出未評估規則。

rule v2 需 ID/version、expression、threshold assumption IDs、scope、cadence、period requirement、freshness、event evidence、materiality definition、rationale、effective/knowledge time。INVALIDATED 必須有明確規則或有來源的人工判定流程，不以跌價自動推論。

### 10.3 Event 與 graph

event 支援原先全部類型；把 announcement、approval、deployment、live usage、economic materiality 視作不同可溯源里程碑，非必然線性成功。失敗／取消／延期可追加新狀態，不改舊事件。

graph edge 保存原 transmission/status/source，新增經濟條件、預期 lag、measurement、counterevidence 與 exposure definition。重新計算只傳播依賴，不能把 assumed economic edge 自動升級為 observed revenue。

## 11. Snapshot 與發布設計

snapshot manifest 至少含：

- schema version、mode、selected contexts／cutoffs、valuation market inputs。
- selected observations／assumptions／scenarios 與完整 immutable record references。
- formulas 完整 expression/version/signature、rules、graph、dictionary、normalization versions。
- code commit、runtime/dependency lock、seed、執行環境識別。
- source versions、可取回 artifact hashes、原文定位；不必每快照複製所有大檔。
- results、quality、issues、triggered/unevaluated rules、事件與 propagation report。
- deterministic content digest，與非 deterministic published_at／publisher journal 分離。

完整 ledger 的保全 hash 可以另存；不得把 cutoff 後資料當成該次 selected evidence。snapshot 讀取要驗證 digest。current 和 historical reconstruction 使用不同 publication tracks，last_changed 定義按研究脈絡計算。

發布流程擬議為：staging → validation → preview diff → reviewed acceptance → atomic publication → immutable snapshot/changelog manifest。使用者已授權的批次可一次核可；這是研究品質流程，不代表每次工具動作都要重問許可。

## 12. AI Agent 的角色與界線

Agent 可以找來源、擷取候選 record、指出衝突、解釋變動、提出假說。deterministic engine 驗證、選取與計算。

AI 輸出先進 staging；需要 schema、evidence locator、extraction confidence、反對證據與檢查結果。來源原文是資料而非 Agent 指令；不得依網頁中的指令更改規則、讀取秘密或提交程式碼。記錄使用的模型／prompt 版本與 provenance，核心不綁 provider。

對 prompt injection、錯單位、捏造引用、過期來源、誤把計画當完成，建立專門負向案例。Agent 分數不能替代原始來源。

## 13. 遷移與回歸

1. 先新增 v2 schema 與 migration ADR，明列 v1 的不能補出的資訊。
2. 不能把舊 record 的 first_seen_at 編造成當年日期；legacy fixture 仍是 fixture，真資料缺欄位保持 unknown／限制用途。
3. 新公式以新 ID／version 入 registry，保留舊 expression 可取回；scope 改變也是 material model change。
4. 現有 UNI 42.2% 與 SECZ/XLM regression 保留，另增新模型 fixture。每個 expected result 需獨立手算或對帳來源。
5. 新舊兩套結果差異說明 calculation、time-selection、scope、source、rule 哪些改變。遷移後不能只說「tests passed」。

驗收由 [backlog](IMPLEMENTATION_BACKLOG.yaml) 各任務定義；本文件不是已上線的資料格式。
