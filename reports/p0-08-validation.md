# P0-08 純讀與可恢復發布驗收

**2026-09-28｜軟體 0.1.6｜P0-08 DONE**

## 發布邊界

`GET /api/state` 只驗證、計算和讀取歷史，不再隱式建立 DEMO 或 RESEARCH 快照。其他 GET 與敏感度 POST 共用專案讀鎖；CLI 的 `validate`、`compare`、v2 時間與規則查詢也在讀鎖內。明確寫入請使用 `snapshot`、`snapshot-v2`、`bootstrap-demo` 或 `apply-event`。待恢復的 journal 存在時，HTTP 返回 503、讀取 CLI 拒絕部分版本；`python -m engine.cli --root <專案> recover` 明確完成該次發布。

事件寫入於同一個跨行程專案鎖下讀取最新 ledger、驗證、重算及檢查舊快照。將 ledger 新位元組、不可變快照及 changelog 新位元組與寫前／寫後 SHA-256 保存在同步落盤的 redo journal，逐檔原子替換並同步目錄後才清掉 journal。故障發生在 journal 建立之前可保留舊版；journal 建立後重啟 `recover` 或執行下一次明確發布則補成完整版。目標已被外部修改時先檢查全部檔案並拒絕復原，不覆寫外部改動。不同事件的並行寫入在鎖中以最新 ledger 重新基準化；同一事件與相同 rows 的重試返回原快照而不新增紀錄；同一事件 ID 改變 evidence 則拒絕。

單檔 v1／v2 快照也使用同一專案寫鎖，以互斥建立及完整檔案獨佔連結寫入。v2 snapshot 仍是 audit-only 單檔；上述跨 ledger／changelog 的 journal 僅用於 `apply-event`，沒有把 v1 變成雙時間、可離線重播或可投資的研究封存。

## 驗證結果

- `python -m unittest discover -s tests -p 'test_*.py' -q`：113 tests OK。隔離複本的 GET 重複查詢及敏感度預覽對所有檔案 SHA-256 無影響。
- 故障分別注入 journal、ledger、snapshot、changelog、finalize 後：除已完成收尾的情況外 GET 返回 503；獨立 CLI `recover` 後三份資料完整、重新執行同一事件不重複入帳。未授權的外部檔案變更使 recovery fail closed。
- 同行程兩個 stale publisher 發布不同事件，兩筆 row／兩份 snapshot／兩筆 log 都保留；兩個獨立 CLI 行程同時重試同一事件，只一個回報 `created: true`。
- `python -m engine.cli validate --demo` 和 `python -m engine.cli validate`：各 94 metrics／0 issues。`node --check dashboard/app.js`、`git diff --check` 通過。兩份歷史 v1 DEMO snapshot SHA-256 分別仍為 `cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e` 和 `6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`。

## 操作界限

跨檔鎖為 advisory；所有讀寫入口必須使用此專案 API／CLI，外部工具若忽略鎖直接改檔，校驗會拒絕有衝突的復原。作業系統崩潰後可重播已落盤 journal；若儲存裝置不遵守同步寫入保證，不能宣稱跨裝置強原子性。Windows 使用檔案鎖，POSIX 使用專案目錄鎖。真正的 v2 資產品質傳播、其他八條規則的真實輸入及 SECZ 財年查核仍依 P0-09／後續研究；真實 observation 為 0，沒有交易或績效結論。
