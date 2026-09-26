# P0-03：v1／v2 相容矩陣與對應政策

**設計狀態：PROPOSED；v1 程式與 2 份 demo snapshot 仍是唯一執行版本。** 以 v1 `spec/canonical-schema.yaml` 的 94 metric（47 OBSERVED、30 DERIVED、16 ASSUMPTION、1 SCENARIO）、`engine/formulas/runtime.py` 和 `engine/snapshots.py` 核對。v2 實作不在本任務內。

## 1. 資料與 API 邊界

| v1 欄位／行為 | v2 對應或缺口 | 遷移／相容性政策 |
| --- | --- | --- |
| `metric_id` 同時定義 concept 與固定 `class` | `concept_id` 不固定分類；`input_role` 指定可用分類和 scope | 複製概念 ID 或明示新 ID；舊 record 分類不變，不能將 ASSUMPTION 改 OBSERVED |
| `as_of_date` + `period.{basis,start,end}` | `economic_period` + `as_of_at`／日期精度 | 保留原字串與期間；**不得**把 as-of 當 published 或 first_seen |
| `effective_date`（assumption/scenario） | `effective_from` + knowledge_time | 可映射生效日期，knowledge_time 未知仍未知；版本後見不應回寫過往決策 |
| `source.date`, `retrieved_at` | 來源版本的發佈存證、擷取時間與 record 自己的 knowledge_time | `source.date` 只有日期；`retrieved_at` 可證明一次擷取，不能自動證明 first_seen；逐版本查證 |
| `supersedes_id` | 相同 concept/entity/security/class/scope/unit/period 的版本鏈 | 保留舊鏈；先以 knowledge cutoff 排除未來版本，才套 supersession |
| OBSERVED + fixture flag | OBSERVED/REALIZED + fixture flag + source version | 188 筆 demo 仍是 fixture；research 0 筆，不升格成真實 evidence |
| DERIVED output + lineage | DERIVED + formula signature、roles、scope、context、eligible selected records | v1 output 永久保留原解釋；v2 若時間或 scope 不符，另存新結果而不覆寫 |
| `calculate(as_of=...)` | economic、knowledge、valuation 各自的 cutoff 與政策 | 舊 API 僅允許 LEGACY_V1 語義；v2 需顯式 query context，不承諾隱式推定 |
| `--demo`／RESEARCH | 模式仍分離，fixture transitive propagation | 研究 ledger 中 fixture 依 WP-01 繼續拒絕；v2 歷史資料還受時間門檻約束 |
| v1 `snapshot.id`, `created_at`, selected metrics | v2 snapshot 有 schema/context/selected evidence/knowledge policy/runtime manifest | v1 JSON 不移動、不修改；read adapter 明示 legacy，禁止進 v2 as-known 樣本 |
| v1 rule `cadence: QUARTER` + 全域日期 | 每資產／每條 rule 期間、freshness、valuation cutoff | P0-06 實作；本次契約不修復 v1 規則 |

## 2. v1 公式到 v2 scope 的研究映射

此表涵蓋全部 30 個 v1 formula；只是**待實作的 output/role 決策**。任何一個 v1 計算通過測試，也不會自動證明其 scope 合法。`CONDITIONAL_REALIZED` 指需比對經濟期間、真實來源、valuation/currency/stock-flow，未通過時輸出 unknown；`LEGACY_MIXED` 指先不可當作真實已實現指標。

| v1 formula IDs | v2 目標 scope／對應條件 |
| --- | --- |
| `tokenized_equity_penetration` | CONDITIONAL_REALIZED：AUM 和市場分母需同 as-of、同定義，不能用不一致價格日 |
| `model_tokenized_equity_aum`, `tokenized_equity_protocol_revenue` | MODELED_HORIZON：TAM scenario、假設滲透／交易份額，非已實現收入 |
| `gross_uni_accrual`, `growth_distribution_value`, `net_uni_accrual`, `net_burn_yield` | LEGACY_MIXED → MODELED_HORIZON 或拆開：現行公式混入情境費率、假設分配與當期 fee；不得稱 REALIZED burn yield |
| `required_uni_accrual`, `required_uniswap_market_share`, `incremental_required_share` | REVERSE_REQUIREMENT：須限定 market-cap quote 的 valuation time，分子／分母同未來 horizon；原 v1 standalone 42.2% fixture 保留 |
| `secz_revenue`, `secz_revenue_growth`, `secz_aum_growth`, `secz_volume_growth` | CONDITIONAL_REALIZED：6 分項是否全揭露及各自期間／實體口徑要對齊；缺分項不補零 |
| `secz_revenue_efficiency`, `secz_volume_monetization`, `secz_operating_leverage`, `secz_ebitda_margin`, `secz_prior_ebitda_margin`, `secz_ebitda_margin_change` | CONDITIONAL_REALIZED：同口徑 period growth、TTM／季頻、可比 EBITDA；零分母與不可比較保持 unknown |
| `secz_required_fcf`, `secz_required_revenue`, `secz_required_revenue_cagr` | REVERSE_REQUIREMENT：現行 EV/terminal multiple 是簡化門檻；不叫現值 intrinsic valuation |
| `xlm_rwa_growth`, `xlm_institutional_growth`, `xlm_network_activity_growth` | CONDITIONAL_REALIZED：同類存量或同期間流量對比；仍只代表 network adoption |
| `xlm_locked_demand`, `xlm_native_demand_growth` | CONDITIONAL_REALIZED：不同 demand bucket 必須去重、可辨識權利與來源；現行 fixture 求和不證明真實總需求 |
| `xlm_network_fee_value` | LEGACY_MIXED：operations×平均 fee×spot XLM 價格可能跨不同期間；依明示 valuation/as-of 改成期間實現值或 MODELED_HORIZON |
| `xlm_economic_capture_ratio` | CONDITIONAL_REALIZED：native 與 network 同比較期間、分母可識別且非近零；不由比率直接推價格 |

UNI 的已實現 fee、burn、realized supply、distribution 及 scenario fee 應各自有新 concept/role；不能只在 UI 將舊 `net_burn_yield` 加上一個 `REALIZED` 標籤。`effective_protocol_fee_bp` 的 v1 assumption 仍是 assumption；未來實際費率建立**新的 observed record**，可共用概念，但 role/scope 不同。SECZ AUM 不直接變現為收入，XLM network adoption 不直接變成 holder value。

## 3. 缺失資訊：可直接轉入與必須拒絕推論

| 原資料 | 可保留或明示映射 | 必須 null／阻擋的用途 |
| --- | --- | --- |
| 188 demo observations | ID、fixture=true、單位、period、來源 ID、value | published_at、first_seen_at、ingested_at 無直接證據；所有真實研究與歷史績效禁用 |
| 17 shared demo assumptions、1 scenario | ID、class、rationale／name、effective_date、fixture=true | 不可變成已採用的真實 fee、growth budget 或市場預期 |
| 2 demo snapshots | v1 digest、內容、as_of_date、created_at 全部維持 | 不能稱作 2026-03／06 當時可知的研究快照；未知 formula/input scope 不能由 `created_at` 推導 |
| future externally sourced v1 record（目前 0） | 若原始檔明確有可核實時間和精度，建立 v2 新 record 連結 legacy ID | 不可拿 filing 的經濟期間末日推 publication；source retrieval 不等於實際首次取得 |
| v1 formula lock + 30 regressions | 原 expression/version/signature 用於 legacy replay | 新 scope 改變任何經濟意義要另版公式，不靜默更動 v1 regression |

## 4. 資料選取與版本決策案例

角色 `uni_realized_protocol_fee` 只讀 OBSERVED/REALIZED；`uni_forward_protocol_fee` 只讀 ASSUMPTION 或 SCENARIO/MODELED_HORIZON。概念可相同，record 不能因選取角色而改 classification。同 value 的兩個已知觀察值保留兩份來源；同一期間不同 value 的來源即使 tier 不同也標 CONFLICT，待人工留下 resolution。修正值若在 cutoff 後發佈，該 cutoff 不得用它壓掉原值。

另有一個例子：同一筆 SECZ 年報披露的全年 revenue 應為 ANNUAL/REALIZED；下一年收入成長 30% 是 analyst scenario 時應為 SCENARIO/MODELED_HORIZON。兩者數字若恰好相同也不得互換。此類明確 role 與 period 校驗由 P0-04/05 實作。

## 5. 驗收與遷移防線

P0-03 通過代表規則和例子**可供實作**，不代表現有 engine 已有歷史可知性。P0-04 的必測條件在 [ADR](ADR-0001-V2-TIME-SCOPE-MIGRATION.md)；P0-05 必須對本表所有 LEGACY_MIXED 公式在 demo／research 做 scope gate，保留既有 regression。任何一個真實 observation 的來源公開時點未知時，可以在 staging 保留 `null`，但不能用零或估算時間令歷史查詢通過。
