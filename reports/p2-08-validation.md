# P2-08：Open Universe 與晉升證據

**2026-09-30｜軟體 0.1.19｜工程稽核完成｜真實研究 BLOCKED**

## 稽核結果

`python -m engine.cli universe-report --economic-cutoff 2026-09-30 --knowledge-cutoff 2026-09-30T06:00:00Z --policy AS_KNOWN_BY_SYSTEM` 唯讀載入 [候選 ledger](../research/universe/p2-08-ledger.yaml)、v2 嚴格 source/identity loader、原始資產 registry 與假設 dependency graph。原有 **13** 個節點完整保留：UNI／SECZ／XLM 是 `LEGACY_CORE_UNVERIFIED`，其餘十個為 SECONDARY／context，包含未必具可交易證券的公司、監管、基建及交易所。原本 `initial_core` 是研究追蹤標籤，不是本契約的晉升決定；SECZ 已上市也不證明此使用者可透過指定券商、工具與法域交易。

真實 `triggers: []`、`decisions: []`、擴充 `exposure_links: []`；v2 已審真實 source 和 observation 亦為零。`promotion_count=0`、`trade_authorization=false`、狀態 `BLOCKED`。舊資產 registry 沒有原始發現時間，報告標 `legacy_seed_historical_availability=UNKNOWN`，不可用來回測當時的完整 universe。現有 dependency edges 全是 `ASSUMPTION`，經濟歸因仍待獨立實證。

## 契約與防火牆

| 層 | 記錄與資格 | 防止的錯誤 |
| --- | --- | --- |
| 發現 | 七類 `discovery_triggers` 中每筆 raw claim 保留 signal、publication（若可證）、實際 first-seen、ingestion、URL lead 或 canonical source ID；新候選須有原始 trigger。公開 instant 另需原文定位、審閱者及 `VERIFIED_INSTANT` | 後來才看到的新聞不能冒充當時已發現；未存證 URL 或只有日期的原文不能被填成分鐘級公開證據 |
| 曝險 | 全部舊圖節點與新候選邊可見，邊統一標 `ASSUMPTION`；無路徑不能晉升 | 依圖可達性直接推收入／持有人價值 |
| 決定 | 同一候選逐筆 HOLD／REJECT／PROMOTE，有 reviewer、理由、時點和唯一前版 ID；歷史查詢保留先前拒絕或未交易紀錄 | 刪除失敗候選、回填較晚決定或只評估已買的案例 |
| 四門檻 | `PRIMARY_VERIFIED`、`CAPTURE`、`INVESTABILITY`、`REVERSE` 分別 PASS 才能 PROMOTE；PASS 須引用已審存證來源、研究分析；實際證據為官方／原始 tier。個人 eligibility 還要指定 user scope、主檔中的 instrument 及路徑 | ticker、股價、AUM、宣傳聲明或 CORE 標籤直接替代經濟機制、逆向承銷與個人可交易性 |

合成 fixture 可演示拒絕後有**新**來源再審、時間切換及晉升流程；結果標 `DEMO_CORE_PROMOTED`，真實晉升數仍為 0，永不授權下單。來源 metadata、人審欄位與檔案路徑可檢驗；程式不會自行證實原文內容、某券商是否真的允許此人交易、或 reverse underwriting 已有預測力。未交易案例的報價與成本後反事實績效屬後續 P3 預先登錄、forecast/paper ledger，不在這裡編造。

新增真候選時，在 ledger append 原始 trigger，再補身分與至少一條明示假設的曝險路徑；每次決定 append 新 ID 和前版連結。原文先依 P1-01 存證、人審、發布 v2 source metadata；四 gate 要有各自的來源、定位與分析報告。`PUBLIC_INFORMATION_RECONSTRUCTION` 只顯示已存證公開時間的發現，不能聲稱本系統當時取得；內部決定仍依當時 recorded time 限制。直接手改 YAML 可繞過 Git 審查，本工作包提供嚴格唯讀驗證與版本鏈，不承諾像事件發布那樣的原子寫入。

## 驗收

`tests/regression/test_universe.py` 涵蓋全部 13 個節點、七 trigger types、未存證 lead 的公開時點拒絕、歷史拒絕與 demo 晉升、缺 gate／錯工具／缺節點、fixture 隔離與 CLI 唯讀。完整 suite **199 tests OK**；DEMO/RESEARCH validate 各 **94 metrics、0 issues**；G0 工程 **PASS**，研究發布 **BLOCKED**、真實 observation **0**。原 v1 DEMO snapshot SHA-256 仍為 `cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e` 與 `6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`。真實 trigger 和人審 promotion 均為 0，所以 P2-08 研究 **BLOCKED**；下一可獨立推進 P2-10。
