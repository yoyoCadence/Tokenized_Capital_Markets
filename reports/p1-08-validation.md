# P1-08：freshness、coverage 與來源失效

**2026-09-30｜軟體 0.1.16｜工程 DONE｜真實 readiness BLOCKED**

`engine/readiness.py` 以共用 strict loader、v2 project validation 和 point-in-time selector 產生唯讀 `readiness-report`。每項 requirement 顯示 `status`、`reason`、證據及來源 ID、age／limit、來源檢查 age／limit、衝突候選與 fixture；`queue` 保留所有非 READY 項。整體 `coverage.ready/required` 僅供盤點；任一 critical 非 READY 即 `BLOCKED`，`decision_ready=false`。自訂 `LABEL_STALE` 只明示過期，不能自動放行。

| Cadence（分析師假設） | 輸入最大 age | 來源人審再查最大 age | 計時起點 |
| --- | ---: | ---: | --- |
| UNI price | 24 小時 | 24 小時 | 原始 quote instant 到 valuation instant |
| UNI burn／SECZ revenue／XLM operations 季度證據 | 150 天 | 14 天 | 完成期間的 period end 到 economic cutoff |
| UNI governance | 7 天 | 7 天 | 已審來源的最後人工查核到 knowledge cutoff |

所有門檻位於 [`research/readiness/p1-08-policy.yaml`](../research/readiness/p1-08-policy.yaml)，是可調的 **ASSUMPTION**，不是監管、交易所或發行者承諾。季度 150 天是初始資料檢查閾值，不代替各公司財年核對、申報期限或期間完整性；XLM/UNI 的季度證據也不冒稱 SEC filing。每筆人工查核須帶 `source_id`、`checked_at`、`status`、`reviewer`、`method: MANUAL_ASSERTION` 與 fixture 旗標；真實來源須先完成來源人審，未見查核、查核過期、宣告 unreachable 或歷史 cutoff 後才查核均不算健康。人工 `REACHABLE` 只表示審閱者在該時點的聲明，不證明沒有其他新事件。此報告不執行網路擷取、文件判讀或投資發布。

執行範例：

```bash
python -m engine.cli readiness-report \
  --economic-cutoff 2026-09-30 \
  --knowledge-cutoff 2026-09-30T23:00:00Z \
  --valuation-at 2026-09-30T23:00:00Z \
  --policy AS_KNOWN_BY_SYSTEM
```

當前真實 v2 ledger 無已審來源或觀察值。上述查詢回傳 `BLOCKED`、`decision_ready=false`、`coverage.ready=0/5`：UNI_PRICE、UNI_BURN、SECZ_REVENUE、XLM_OPERATIONS 各為 `NO_ELIGIBLE_RECORD`，UNI_GOVERNANCE 為 `SOURCE_NOT_ASSIGNED`；age 因沒有證據維持 null。這五項是最小監控樣本，非 G1 三資產全部所需資料的完整列舉。P1-05／06／07 證據缺口和 G1 發布阻塞不變。

驗收涵蓋單項季度新鮮但其他關鍵資料缺失、季度過期、報價／治理獨立時鐘、未解衝突保留候選、來源 unreachable、未來來源查核不能回填歷史、stale label 不給 decision-ready、錯誤角色／來源拒絕、CLI 在副本唯讀。`tests/regression/test_readiness.py` 共 **7 tests**。完整套件 **179 tests OK**；`validate --demo`／`validate` 各 **94 metrics、0 issues**；`scripts.g0_gate` 回報 G0 工程 **PASS**、研究發布 **BLOCKED**、真實 observation **0**。原 v1 DEMO snapshots SHA-256 維持 `cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e`、`6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`；研究觀察值未修改。
