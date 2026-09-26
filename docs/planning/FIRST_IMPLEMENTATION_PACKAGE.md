# WP-01：研究資料隔離與嚴格輸入驗證

**狀態：DONE｜完成日期：2026-09-26｜軟體版本：0.1.1**

對應 backlog：**P0-02 → P0-01**。Implementation commit：[`e8b4d55520ea71f1d626a9286fa64a30cd745f3d`](https://github.com/yoyoCadence/Tokenized_Capital_Markets/commit/e8b4d55520ea71f1d626a9286fa64a30cd745f3d)。[驗收紀錄](../../reports/wp-01-validation.md)：67 tests 通過、兩種模式 validation 通過、原金融資料與快照保留。原始下一項 P0-03 後已完成，最新任務見 backlog。

以下保留原始工作包的問題陳述與驗收要求，描述的是實作前基線；目前行為以驗收紀錄和程式為準。

## 1. 為什麼先做這一項

目前資料夾分流不足以阻止 fixture observation 在 RESEARCH project 被接受；YAML 重複鍵也會被靜默覆蓋。兩個問題都已重現，影響所有後續研究資料，且可以用明確負向測試驗收。

目標：使用者看到 RESEARCH 結果時，能確定參與計算的輸入沒有 synthetic fixture；錯誤資料在計算／發布前被拒絕。

## 2. 範圍與交付

1. strict YAML loader，定位重複鍵和 parse 錯誤。
2. preflight 驗證 ID 唯一、record schema、非法版本鏈、formula graph。
3. RESEARCH selected-evidence guard，涵蓋所有計算與發布入口。
4. CLI/API 一致的 error code、檔案／record／field 診斷。
5. 正常 DEMO、空 RESEARCH、synthetic 污染、malformed input 的測試。
6. README 資料隔離說明與 changelog，附真實測試證據。

不在此工作包內：即時來源導入、時點 selector v2、估值公式修改、交易、scheduler、UI 重新設計。它們留在既定依賴順序。

## 3. 預計修改位置

| 路徑 | 目的 |
| --- | --- |
| engine/storage.py | strict parse、明確模式載入政策、不要靜默接受污染 |
| engine/validation/checks.py | 唯一性／enum／field／record chain 與模式 preflight |
| engine/validation/lineage.py | selected lineage 的 fixture 傳播與拒絕 |
| engine/server.py、engine/cli.py | 共用 validation 入口與可讀錯誤 |
| engine/snapshots.py、engine/propagation/ingest.py | 發布／事件不能繞過 mode gate |
| tests/schema、tests/lineage、tests/regression | 有意義的正常與負向案例 |
| README.md、reports/changelog.md | 行為變更與驗收證據 |

實作前重新查讀程式，依當時版本調整路徑；不為符合這個表而做無必要改動。

## 4. 正確的隔離政策

- 一個 repo 可以同時保存 DEMO 和 RESEARCH；歷史 fixture 與來源不必刪除。
- shared registry 中**未被 RESEARCH 選用**的 fixture source／assumption／scenario 允許存在。
- 放入研究輸入檔的 fixture、宣稱研究依據的 fixture event、或實際選中 synthetic record，必須回傳明確 ERROR，不能偷偷過濾後繼續聲稱完整研究。
- 明確隔離的共用 demo 配置可以依宣告不選用，並在 loading policy 中記錄；這和把錯放研究資料丟掉是不同情況。
- selected graph edge 如使用 fixture evidence，不能進真實研究 graph 當已驗證關係；shared demo edge 保留在 demo context。
- fixture 的所有衍生後代仍是 fixture。source tier 為 FIXTURE 不得被強制轉成整數 tier 以繞過。
- 資料分類仍只有四種；不要發明 FIXTURE classification 或把 unknown 替換成 0。
- 一個 synthetic value 就足以阻止受影響 research publication，不以占比小而豁免。

## 5. 驗收測試矩陣

| 案例 | 預期 |
| --- | --- |
| 預設 DEMO | 原 94 metric 計算與 fixture 標示保持，regression 不漂移 |
| 預設空 RESEARCH＋共享 fixture registry | 合法；所有未有真資料的值 unknown |
| fixture observation 寫入 research 輸入 | ERROR，明確 record ID，不產生 snapshot |
| fixture event／source 綁定到研究 record | ERROR；不能依 status=LIVE 繞過 |
| 多層 DERIVED 隱含 fixture leaf | ERROR 或此前 preflight 已阻止求值；不可 research publish |
| false fixture flag 卻引用 fixture source | ERROR |
| YAML 同一 mapping 重複 key | parser error，含檔案／位置 |
| duplicate source/record ID | ERROR；不能 dict 轉換後遺失第一筆 |
| supersedes 本身／循環／missing／跨語義 | ERROR；合法追加修正版仍通過 |
| 非法 enum/date/unit、NaN/Inf、錯型別 | ERROR，不靜默 coercion |
| formula dependency cycle | preflight ERROR，指明 cycle |
| CLI、API、event、snapshot 四個入口 | 對同一污染輸入拒絕一致 |
| 所有錯誤路徑 | 原始檔案與歷史 snapshot hash 不變 |

測試在 temporary fixture project 執行，不能改 tracked demo/research ledger。驗證可以直接以 API/CLI 呼叫，不需要新增任何未要求的金融資料。

## 6. 完成定義

- 原 26 個測試仍通過，新增與邊界直接相關的負向測試。
- 以下命令正常完成：

~~~bash
python -m unittest discover -s tests -p 'test_*.py'
python -m engine.cli validate --demo
python -m engine.cli validate
~~~

- 另展示一筆 fixture 污染的失敗案例，CLI exit status 非零、錯誤可定位、無發布副作用。
- 所有既有 financial spec／observations／snapshots 沒有未解釋變更。
- 新的安全邊界寫入文件；沒有宣称其已解決 bitemporal、scope 或其他未包含風險。
- commit 與 changelog 連到 P0-01/P0-02，backlog 附 completion evidence 才可改 DONE。

## 7. 原始實作任務（已執行，保留歷史）

> 請實作 docs/planning/FIRST_IMPLEMENTATION_PACKAGE.md 的 WP-01。先讀 AGENTS.md 與現況稽核，完成 P0-02、P0-01 的驗收，不改金融公式與歷史資料。使用 temporary fixtures 重現研究模式污染和重複 YAML key，修正後執行完整現有測試與新增邊界測試，記錄測試輸出、changelog、backlog 完成證據，再依使用者當次授權提交。

上述任務於 2026-09-26 完成；勿再依此模板重做 WP-01。P0-03 設計契約亦已完成；下一項 P0-04 的依賴與驗收見 structured backlog。
