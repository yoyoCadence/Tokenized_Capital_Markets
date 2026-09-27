# P0-07 驗收與 v1 快照遷移報告

**2026-09-27｜軟體 0.1.5｜P0-07 DONE（v2 audit-only compute bundle）｜P0-08 發布事務尚未實作**

## 自包含重播契約

`snapshot-v2` 在資料及規則驗證通過後，同時計算 v2 UNI 四種 scope 與逐資產 thesis cadence。單一 content-addressed JSON 封存 query、兩套結果、選用 record/source IDs 及其內容雜湊、每個角色／季度的知識與估值時點、v2 原始 ledger 與 source metadata、所有 YAML 規格、v1 dictionary/graph 作為版本索引、完整 `engine/*.py` 實作、requirements/pyproject 及 Python/PyYAML 精確版本。`code_revision` 是封存程式檔內容的 SHA-256，而非猜測的 Git commit。來源 ID 可以在封存的來源版本中解析為 URL／publisher／日期；外部原文檔案尚未入庫，故 URL 不等於來源原文位元組已封存。

檔名是**整份 canonical JSON 位元組**的 SHA-256；另外逐檔驗證歸檔位元組的長度與 SHA-256。相同查詢、相同輸入、相同實作生成相同 ID，檔中沒有另造的提交時間。`replay-v2` 先驗檔名、內容、runtime 與正在執行的程式碼位元組，再從暫存目錄裡解出的規格／ledger 重算；原始研究目錄已刪除時仍可用封存程式碼在相同版本 runtime 的乾淨環境重播。任何一處驗證不符即拒絕結果。SHA-256 是完整性與版本辨識，**不是作者身分簽章**；重新編寫全部內容並重新算雜湊的人可建立另一份新 artifact，不能藉此證實外部來源真實性。

`HISTORICAL` 要求明示 economic／knowledge／valuation cutoff 及 AS_KNOWN_BY_SYSTEM 或 PUBLIC_INFORMATION_RECONSTRUCTION。`CURRENT` 在建立時直接捕捉 UTC 系統時間，只用 AS_KNOWN_BY_SYSTEM；兩種 track 分開放在 `data/snapshots/v2/{research|demo}/{historical|current}/`，replay 保留原 track 與凍結時點，不用重播時鐘改寫歷史。所有 selected record 都再次核對當次 cutoff 之前的已驗證 publication，system track 另要求 first_seen／ingested；選中報價不晚於各自的 valuation。全 ledger 可以保留「尚不可用」的候選紀錄以重播排除與衝突，**selected_evidence 清單不得含 cutoff 後的紀錄**。空 RESEARCH 的結果保持 Unknown，標 `AUDIT_ONLY`，不形成可投資發布。

在測試的隔離合成包，UNI q2 realized yield 為 1%，兩季規則觸發 WATCH；manifest 含 10 筆被引用的 record 與其來源。來源目錄移除後，在只帶這份 artifact 及從其解出的程式碼的新目錄重播一致。改動一個 JSON 位元組、某個歸檔公式位元組、重算外層檔名後竄改結果、變更本機程式碼或 runtime lock 全被拒絕。已公開但系統後來才取得的重述只進 public-reconstruction 的 selected manifest，不倒灌 system-as-known。CURRENT／HISTORICAL 路徑與 provenance 不可只靠改一個標籤混用。CLI 重試同內容不重複發布，replay 不寫入原檔。

## v1 → v2 遷移對照

| v1 demo 檔名 | 原檔 SHA-256 | v2 用途 |
| --- | --- | --- |
| `306a92aa32ab33431b82.json` | `cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e` | LEGACY_DEMO，僅原樣顯示／既有比較 |
| `df1d2ede420426dc1ad1.json` | `6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808` | LEGACY_DEMO，僅原樣顯示／既有比較 |

兩份舊檔都有 v1 選值、公式指紋和 fixture，但缺原始 source 版本位元組、公開與首次取得時間、v2 scope/role、完整 expression 與計算程式封存；`created_at` 不能補作當時已知時點。因此不轉成 `HISTORICAL`／`CURRENT` v2 快照，也不回填臆測時間。`snapshot`／`compare` 和既有 42.2% regression 仍屬 v1 legacy。任何未來 v1 record 遷移須另建 v2 ID，缺時點留 null 並記 `LEGACY_TIME_UNKNOWN`；這次沒有新增真實 observation 或 canonical snapshot。

## 重現及剩餘邊界

```bash
python -m unittest discover -s tests -p 'test_*.py' -q    # 108 tests OK
python -m engine.cli validate --demo                       # 94 metrics, 0 issues
python -m engine.cli validate                              # 94 metrics, 0 issues
# 以下建立一份明示空 RESEARCH 的 audit bundle；正式庫不自動執行
python -m engine.cli snapshot-v2 --track HISTORICAL \
  --economic-cutoff 2026-09-26 --realized-quarter-end 2026-06-30 \
  --horizon-end 2027-12-31 --knowledge-cutoff 2026-09-26T12:00:00Z \
  --valuation-at 2026-09-26T12:00:00Z --policy AS_KNOWN_BY_SYSTEM
python -m engine.cli replay-v2 <上一步輸出的路徑>
```

測試僅在暫存包產生並重播檔案；正式 research/demo v2 ledger、兩份 v1 快照保持原位與原值。P0-08 尚須處理 GET 不寫入、跨 ledger/snapshot/changelog 的鎖、事務及故障恢復；P0-09 尚須品質傳播。程式重播一致不等於來源真實、其他八條規則已遷移，或投資策略具優勢。
