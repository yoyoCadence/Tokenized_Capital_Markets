# P0-06 驗收：資產／規則各自的期間及 freshness

**2026-09-27｜軟體 0.1.4｜P0-06 DONE（唯讀 v2 規則路徑）｜v1 thesis/snapshot 仍為 legacy**

## 原則與實作界線

`engine/thesis/cadence_v2.py` 依 `spec/v2/rule-cadence.yaml` 的**每條規則 anchor role**選季度，不讀全域 observation 日期。只有 OBSERVED／REALIZED 的完整季度、已公開且符合指定 knowledge policy 的來源才能成為候選；每季選值另經 P0-04 selector。新日報價只能用於明示的歷史 valuation time，不會變成 SECZ 或 XLM 的新季度。

規則 policy 與三資產 calendar 各有版本及簽章鎖。每季須有相容的 `fiscal_year`／`fiscal_quarter`、月份季度尾及完整起始日；缺季、53 週或不同財年口徑、期間過期與報告超過 grace 都不自動補齊。TTM (trailing twelve months，滾動十二個月) 若作規則輸入，需 350–380 天且終點對準該規則季度；SPOT 資料另受 role 報價期限與政策最長持有天數約束。每個可評估季度需要使用者明示的歷史 valuation instant，當次知識截止為此 instant 與總截止較早者；當時系統已知和公開資訊重建不混用。

現行九條 v1 規則在 v2 registry **全部保留其 ID／資產／窗口／狀態**。只有 `uni_low_net_burn` 能使用 P0-05 已驗收的 v2 `uni_realized_net_burn_yield`，且仍須有兩季 burn／distribution／dilution、供給與各季價。其餘八條因 v2 對應經濟輸入、財年或事件證據尚未驗證，明示 `UNMIGRATED_INPUT`；SECZ 財年末月目前未知，另明示 `FISCAL_CALENDAR_UNVERIFIED`，不能默認 12 月結年。UNI／XLM 的 12 月月底 anchor 為內部 analyst cadence policy，**不是發行人的財年證據**。此任務修的是「不製造跨頻率假訊號」；SECZ／XLM 完整 v2 unit economics 與 rule migration 留待各自的研究包／模型工作。

結果保留所有 `triggered_rules`、`evaluated_rules`、`unevaluated_rules`，並附 rule/calendar signatures、選定季度、財年標籤、各季估值／知識時點、選用 record/source IDs 與未評估原因。只要無觸發且任一規則未評估，asset state 為 null 而非 HEALTHY。新 `thesis-cadence` CLI、`/api/thesis-cadence` 與 Dashboard v2 面板僅查詢，不寫快照。原 Dashboard thesis 標示 LEGACY V1：既有 v1 的全域日期缺陷沒有被回溯重寫，**不能用該路徑做 point-in-time 或當期可靠訊號**；舊 snapshot 及 42.2% fixture regression 不變。

## 合成驗收

- 四個季度僅使用測試記憶體／暫存專案：UNI 每季 burn $10、distribution／dilution $0、100 UNI × $10 價格 → 1% realized yield；兩季低於 2% 的 analyst 門檻，v2 UNI WATCH。沒有真實 financial observation 或假造首次取得時間。
- 另設**僅測試用**的 XLM 季度 activity 規則，先確認其季度觸發；新增 2026-07-07 UNI 日報價後，XLM 觸發、SECZ 季度選取及 UNI 舊季估值全部不變。該測試規則未加入 canonical 投資 thesis。
- 移除一季 → GAP；錯誤 fiscal year → mismatch；報告寬限期內沿用上季，寬限期外缺季 → `MISSING_QUARTER`；issuer calendar 未知 → Unknown；TTM 末日錯位、過期 quote、超時發布、缺歷史估值皆不形成觸發。
- 同季晚取得重述：system-as-known 仍選原始 record，public-information reconstruction 依當時有存證的公開時點選重述版；兩種輸出分離。改動 rule/calendar 而未同步鎖版被 `RULE_LOCK` 拒絕，跨資產 role、缺少任一 v1 rule disposition 亦拒絕。
- CLI 與本機 HTTP 在暫存 DEMO 包可回放，同查詢的空 RESEARCH 仍 Unknown；前後檔案 SHA-256 集合一致。

重現：

```bash
python -m unittest discover -s tests -p 'test_*.py'    # 102 tests OK
python -m engine.cli validate --demo                  # 94 metrics, 0 issues
python -m engine.cli validate                         # 94 metrics, 0 issues
python -m engine.cli thesis-cadence \
  --economic-cutoff 2026-09-26 --knowledge-cutoff 2026-09-26T12:00:00Z \
  --policy AS_KNOWN_BY_SYSTEM --valuations '{}'
# 研究 ledger 空，所有資產 null；不寫入任何快照
```

下一步 P0-07 為 snapshot 自包含 manifest／digest／離線 replay；P0-08 的 GET 不可寫、發布事務，P0-09 品質傳播，P1/P2 真實來源與未遷移的資產模型，仍是獨立門檻。軟體通過 102 個測試不等於投資模型已具備有效性或 alpha。
