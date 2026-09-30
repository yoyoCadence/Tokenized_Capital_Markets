# P2-07：事件里程碑與經濟傳導監控

**2026-09-30｜軟體 0.1.17｜工程 DONE｜真實事件與經濟效果仍 UNKNOWN**

v2 在 `data/v2/events/{research,demo}.yaml` 保留 append-only 的事件版本。`PLANNED`、`ANNOUNCED`、`APPROVED`、`DEPLOYED`、`LIVE`、`MATERIAL`、`COMPLETED`、`DELAYED`、`CANCELLED`、`FAILED` 各需明示查核；沒有「日期到了自動上線」或「上線了自動重大」。原有 **13** 個 event types 全數可用。`MATERIAL` 額外需要同一線索先有獨立 `LIVE` 版本，以及已完成期間的量、門檻、單位、分母與分析師理由。這是有來源的人工聲明，不等於模型已辨識 holder value。延期、取消、失敗是新版本；後二者終止該線索。跳過中間里程碑可由新證據直接支持，但跳過的狀態不會出現在 `verified_milestones`。

真實聲明須引用 v2 已審、存證來源版本與原文定位；新的版本須用不同來源 ID。每版記 `event_at`、`published_at`、`first_seen_at`、`ingested_at`、`reviewed_at`，時序嚴格驗證。歷史選取先按公開或系統知悉時點過濾，再套用 supersession；公開重建不會冒充當時系統決策。人工定位與來源登錄只代表審閱者的可追查聲明，程式不解析或證實外部原始內容。真實事件 ledger 現在是空的。

圖的每條邊在 [假設政策](../spec/v2/event-monitor.yaml) 均有條件、預期 lag、待量測項、反證和曝險定義。`event-monitor` 顯示到期查核與來源 lineage；連 `economic_transmission: true` 的邊都保留 `classification: ASSUMPTION`、`economic_effect: null`。v2 thesis cadence 同 bundle 重新計算，但事件關聯規則目前仍 `NOT_WIRED_TO_V2_RULES`；沒有完整原生需求／holder capture 的 OBSERVED 輸入，絕不從 DTCC 的 planned 或其他鏈 production 推出 XLM 需求。

唯讀範例：

```bash
python -m engine.cli event-monitor --economic-cutoff 2026-09-30 \
  --knowledge-cutoff 2026-09-30T02:00:00Z --policy AS_KNOWN_BY_SYSTEM
```

明確發布範例（`--event` 指向 `event: {...}` 的 strict YAML，其他時點按實際證據填寫）：

```bash
python -m engine.cli event-publish-v2 --event /path/to/reviewed-event.yaml \
  --economic-cutoff YYYY-MM-DD --realized-quarter-end YYYY-MM-DD \
  --horizon-end YYYY-MM-DD --knowledge-cutoff YYYY-MM-DDThh:mm:ssZ \
  --valuation-at YYYY-MM-DDThh:mm:ssZ
```

此命令在專案寫鎖內驗證事件及模式，先在暫存專案組合新 ledger 並重算 v2 economics、cadence、events，然後以單一 redo journal 發布 ledger、content-addressed v2 audit snapshot、changelog。離線 replay 會核對凍結的程式、規格、事件帳、來源及重算結果；中斷後 `recover` 續寫，同 ID 同內容重試不重複寫入。公開研究目前仍無真實事件及觀察值，不會因工程通過而升成 G1。

合成整合測試覆蓋所有 13 型別、歷史公開與系統時點差、LIVE/MATERIAL 分離、量化門檻、延期取消、來源與 fixture 拒絕、圖上自迴圈、兩次發布、離線 replay、中斷恢復及冪等重試。`tests/integration/test_event_monitor_v2.py` **8 tests OK**；完整套件 **187 tests OK**；DEMO／RESEARCH validate 各 **94 metrics、0 issues**；G0 工程 **PASS**、研究發布 **BLOCKED**、真實 observation **0**。原 v1 DEMO snapshots SHA-256 保持 `cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e` 和 `6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`；新版 v2 audit bundle 契約升至 `2.0-compute-bundle.7`。
