# P0-09 品質傳播與衝突選取驗收

**2026-09-29｜軟體 0.1.7｜P0-09 DONE**

## 契約與資料流

v2 的選值輸出將來源層級、資料新鮮度、來源所宣稱的涵蓋、原始量測核實、經濟機制，以及衝突狀態分為六個欄位，不再把 tier 變成整體的「可信分數」。沒有原文量測查核時 `measurement=UNVERIFIED`；機制未核實時 `mechanism=NOT_ASSESSED`，情境／假設依賴則為 `ASSUMED`。宣稱涵蓋的 source metadata 只標 `coverage=DECLARED`，不表示量測口徑已核對。報價顯示實際 age 與角色最大容許秒數；其他 role 沒有資料齡上限時顯示 `NO_ROLE_LIMIT`，不擅自判定新鮮。

UNI v2 公式沿完整依賴鏈聯集最上游 assumption／scenario record ID、缺值角色、source tiers 及逐角色 freshness；季度 rule evidence 同樣保留每個輸入的 quality。v1 的 `confidence` 修復只看直接 DERIVED 的缺陷，改用既有 transitive lineage 葉節點；dashboard 同時明示 v1 沒有知識時鐘或核實量測，舊計算與兩份快照仍是 legacy。

新增 `data/v2/resolutions/{research,demo}.yaml` 嚴格 ledger。每筆決定需 ID、role、完整候選／所選 record ID、理由、審核者、實際審核時間與 fixture 旗標；所有候選需同一角色及期間、已驗證發布並已在系統入庫，審核不能早於取得。選值只接受**剛好匹配當時 active candidate set**、且 `reviewed_at` 不晚於查詢 knowledge cutoff 的決定。新的候選出現會使舊決定不適用；同值多來源仍全部保留。每個候選的數字、分類、source ID/tier、被選與未選 ID、reviewer 和理由可在 v2 Inspector 查閱。這是明確記錄人的選擇，並非根據較高 tier 自動決定；目前兩份正式 resolution ledger 均空。

計算快照改為 `2.0-compute-bundle.2`，封存 research/demo resolution ledger、品質欄位與結果，離線 replay 對新合約檔案逐位元組檢查。v2 proposal 更新為 `2.0-proposal.3`；已存在的舊 v2 bundle 仍是不可變舊版本，需在其原程式/runtime 環境重播，不能假稱以新版程式位元組重播。兩份 v1 DEMO 快照保持原樣。

## 重現

- `python -m unittest discover -s tests -p 'test_*.py' -q`：119 tests OK；新增測試覆蓋多層 scenario／assumption 傳播、高 tier 不能把預測升格觀測、同值支持、未解及已解衝突、時點門檻、新候選使舊決定失效、錯誤 ID／scope／review time 拒絕、檔案讀取純讀及新 ledger 的離線 replay。
- `python -m engine.cli validate --demo`、`python -m engine.cli validate`：各 94 metrics、0 issues；`node --check dashboard/app.js` 與 `git diff --check` 通過。
- v1 DEMO snapshot SHA-256 仍為 `cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e`、`6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`。

## 界限

本工作包沒有新增真實 observation 或審核完成的 resolution。`reviewer` 是 ledger 所記文字，並非身分簽章；來源網址及 metadata 也不能替代原文或核證會計定義。尚無足夠 evidence 的 measurement/mechanism 維持未核實，不能因軟體品質欄位完備而得出可投資結論。G0 整合驗收為下一項 P0-10。
