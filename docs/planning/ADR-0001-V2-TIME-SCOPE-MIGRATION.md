# ADR-0001：時間、經濟 scope 與 v1→v2 遷移

**日期：2026-09-26｜決議：ACCEPTED AS DESIGN｜執行：P0-04 完成、P0-05／06 尚未開始**

**實作進度：** P0-04 已以獨立唯讀查詢完成雙時間選值，詳見[驗收](../../reports/p0-04-validation.md)；P0-05／06 仍未實作。契約補列 `as_of_precision` 與報價原時區日期，版本為 `2.0-proposal.2`。以下保留原設計決議與步驟。

## 背景與決策

v1 的 `_select` 用 `as_of_date`／`effective_date` 選取；研究事件何時公開與系統何時取得沒有欄位。v1 `canonical-schema.yaml` 把 94 個 metric 的 `class` 固定，且部分 `DERIVED` 混合情境與實現經濟。兩份既有 demo snapshot 只證明 v1 fixture 算法一致，不能證明其歷史當時已知。

採用 [機器可讀提案](CONTRACT_V2_PROPOSAL.yaml) 與 [相容矩陣](V1_V2_COMPATIBILITY.md)。v2 將 metric concept、一次 record 的 classification、formula input role、economic scope、economic period、knowledge time 和 valuation time 分成獨立維度。保持四種 classification、五種 thesis state 和 fixture 旗標。這是**契約定稿供後續實作**，不是宣稱 v2 selector 或 runtime 已部署。

## 選值與時間規則

1. 指定 query 的 `economic_cutoff`、`knowledge_cutoff`、`valuation_at`、`knowledge_policy` 和 `required_scope`，不從系統今天或最晚資料日偷偷推定歷史 cutoff。
2. 先用 metric concept／entity／security、input role、分類、scope、unit、period 對應，再按查詢模式排除當時不可知 evidence。之後才處理同一經濟期間的 supersession／衝突，最後採用符合最大資料齡的最新合法版本。
3. `AS_KNOWN_BY_SYSTEM` 用有存證的公開可用時點和實際 `first_seen_at`、`ingested_at`；三者均不晚於 cutoff。當時尚未入庫的資料不得被稱為系統當時的決策證據。`PUBLIC_INFORMATION_RECONSTRUCTION` 可事後取得有可靠原始發布時點的資料，只能聲稱當時*公開可知*，不能冒稱當時已有本系統的研究或交易。
4. 只有 publication 日期時，且可證明時區，使用該時區所記日期**隔日零點**作保守可用時點。精度或時區不明則拒絕歷史 point-in-time 使用。所有 instant 需帶 timezone，計算轉 UTC；保留原表述與精度。
5. 修正／重述資料必須用**該修正版**的公開與取得時間；先篩資格再處理 supersession。不同來源若衝突，保留所有 evidence 並回傳 CONFLICT，不靠來源層級或最大日期偷選值。同值多來源保留全部被選中的支持 ID。
6. 以 `valuation_at` 限定市場報價，不讓季度研究的時點被之後的價格代換；價格時間和股本時間各自可見。未來 P0-06 再實作各資產／規則 cadence 與 freshness。

### 實例：相同 Q1 經濟期間、不同公開時間

下表只用來界定 selector 驗收，數值是**設計範例 fixture**，不是 SECZ 的真實業績。均為同一 `secz_revenue`、相同 Q1 interval、USD、REALIZED，第二筆 `supersedes_id: original`。

| Record | Economic end | Published | First seen / ingested | Value |
| --- | --- | --- | --- | ---: |
| original | 2026-03-31 | 2026-05-10 12:00Z | 2026-05-11 12:00Z | 100 |
| restated | 2026-03-31 | 2026-08-15 12:00Z | 2026-09-02 12:00Z | 90 |

| Knowledge cutoff | System-as-known | Public reconstruction | 說明 |
| --- | --- | --- | --- |
| 2026-06-30 23:59Z | 100 | 100 | 重述未發布 |
| 2026-08-20 23:59Z | 100 | 90 | 重述已公開，但本系統尚未取得 |
| 2026-09-03 23:59Z | 90 | 90 | 已取得且納入 ledger |

**遷移個案**：demo 2026-03-31 snapshot 於後來建立、fixture source `retrieved_at` 為 2026-09-25。不得用經濟季末、source date 或 Git commit 日期冒充 `published_at`／`first_seen_at`／`ingested_at`。v1 歷史結果只作 LEGACY_DEMO 顯示，不能進 as-known 投資回測。

## 經濟 scope 與分類規則

`OBSERVED` 是證據類型，不能描述「管理層預測中的營收」為已實現營收。`REALIZED` 是經濟口徑；`RUN_RATE` 是已見收入／流量按明確頻率年化的**計算值**，需標基期、公式與適用性；`MODELED_HORIZON` 是情境期間；`REVERSE_REQUIREMENT` 是從指定估值反推條件。這四者不更改資料的 OBSERVED／DERIVED／ASSUMPTION／SCENARIO 身分。

`uni_effective_protocol_fee` 作為概念，可以有真實來源支持的季度 `OBSERVED/REALIZED` record，也可以有 analyst `ASSUMPTION/MODELED_HORIZON` record。公式以 `uni_realized_protocol_fee` 或 `uni_forward_protocol_fee` role 選取，不得修改舊紀錄的分類。「growth budget」不能直接作「realized distribution」；「v1 net_burn_yield」因混合 TAM scenario，不能以同名輸出當已實現 burn yield。分流由 P0-05 引入新 role／公式和 scope 驗證；v1 回歸維持原標籤與數字。

任何 `DERIVED/REALIZED` 經濟值須逐葉核對實現期間、來源和範圍；如果價值相關葉節點含 forward assumption 或 future scenario，必須降為 MODELED_HORIZON 或顯示不可計算。若某些分析用門檻 assumption 用於*規則判定*，保存其 classification，勿誤標實際經濟值為觀測事實。

## 遷移步驟與失敗政策

| 階段 | 工作 | 發布門檻 |
| --- | --- | --- |
| P0-03（本次） | 固定契約、矩陣和 ADR；保留 v1 路徑與 byte-identical snapshots | 只更新 planning/changelog/backlog，v1 CLI 行為相同 |
| P0-04 | 新增 v2 records/讀取器、雙時間 selector 與獨立回歸；明示 query context | 6 月／8 月／9 月範例與日期精度負例通過；v1 不退化 |
| P0-05 | 新增 scope/role/derived 分流和 regression；UI 顯示兩種結果區別 | v1 42.2% 不變；未證實 burn 不得進 realized 規則 |
| P0-06 | 每資產、每規則 cadence/period/freshness 選取 | 每日報價不打斷季度樣本 |
| P0-07/08 | replay manifest 和原子發布 | v1 snapshot 可作 legacy 檢視；v2 replay 獨立通過 |

新資料以 v2 append-only records 存放；舊 v1 ledger 和 snapshots 永不原地改寫。遷移時另立 `legacy_record_id` 連結，保留原值、分類、來源、fixture、as-of/period；新增無法從原始資料證明的時間欄一律 `null`，status `LEGACY_TIME_UNKNOWN`。**不能因欄位為 null 就拿系統遷移日回填為「首次取得」**；遷移操作的真實時間只能記在 migration journal，不能倒灌成來源首次可見時間。

v1 讀取與舊 snapshot 使用明示 `LEGACY_V1` adapter；不能將其輸出默認併入 v2 的 historical point-in-time track。對當前研究，缺歷史時間的舊 record 可顯示來源與缺口；若無法核定選值與 scope，標 unknown 並禁止 decision-ready 發布。所有 v2 生產 records 必須具備其可取得的時間與存證；未取得歷史 publication 可以留 null，但不得當作已知歷史事實。

版本號／簽章更動依 AGENTS.md：公式改變必須新 formula version/signature 並留下 changelog。此 ADR 不修改任何 v1 公式，也不承諾現有真實資料品質或投資優勢。

## 放棄的選項

- 只替 v1 observation 增加 `published_at`：沒有 first_seen、valuation、role 與 scope，無法解決歷史回放及當期收益混入未來情境。
- 把 v1 的 `as_of_date` 當公開日期：季末與財報公開是不同事件，會製造 look-ahead。
- 直接升級既有 snapshot：內容地址與來源語義會改變，破壞不可變性及既有 regression 證據。

## 後續風險

source 公開時點的原始存證、時區、動態更新頁版本與資料授權仍需逐項核驗；此契約無法自行產生缺失的證據。具體 P0-04 tests 須覆蓋相同值雙來源、晚到的更正、日期精度、時間等號邊界、timezone/DST、同時衝突、quote stale，以及 rollback 時 v1 可繼續執行。
