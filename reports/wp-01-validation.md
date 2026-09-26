# WP-01 驗收紀錄：研究資料隔離與嚴格輸入驗證

**日期：2026-09-26｜軟體：0.1.1｜P0-02、P0-01：DONE**

- 實作基線：`650cfdff4b025c48dfed3b98c7a56aa8face3caf`。
- Implementation commit：[`e8b4d55520ea71f1d626a9286fa64a30cd745f3d`](https://github.com/yoyoCadence/Tokenized_Capital_Markets/commit/e8b4d55520ea71f1d626a9286fa64a30cd745f3d)。本報告由其後的文件 commit 記錄，以免使用尚不存在的提交編號。
- 原始範圍：[WP-01](../docs/planning/FIRST_IMPLEMENTATION_PACKAGE.md)；任務狀態：[structured backlog](../docs/planning/IMPLEMENTATION_BACKLOG.yaml)。

## 1. Principle：研究模式必須在計算與發布前拒絕 synthetic 證據

同一 repository 可以保存 DEMO 與 RESEARCH。模式隔離須涵蓋實際使用的 record、source、graph evidence、衍生 lineage 與 snapshot；分類仍然只有 OBSERVED、DERIVED、ASSUMPTION、SCENARIO。Fixture 是品質旗標，Unknown 保持 null。

這次沒有新增真實市場資料，也沒有修改任何金融公式或 canonical 財務輸入。完成的是資料入口與發布前驗證，並非整個 G0 或真實研究發布門檻。

## 2. Logic：共用驗證管線

`strict YAML → v1 structure/type → unique IDs / revision chains → semantic validation / formula DAG → mode isolation → calculation / lineage → publication gate`

| 實作 | 具體行為 |
| --- | --- |
| Strict loader | 拒絕重複 mapping key、aliases、merge key、非 mapping 根節點、NaN／Infinity／溢位浮點數；parse 錯誤有檔案、行、列 |
| Structural preflight | 驗證必要／未知欄位、集合型別、exact boolean／integer、有限 numeric 值，先檢查再取值，避免 malformed input 造成 traceback |
| Identity / revisions | dict 建立前檢查重複 source／record／event／rule IDs；拒絕 missing parent、自循環、多節點循環及跨語義替換 |
| Formula preflight | 驗證 expression 語法、非有限常數、既有 signature lock、dependency DAG 循環；沒有修改公式版本 |
| Mode isolation | 研究 ledger 中的 fixture 即使在 DEMO 也拒絕；false fixture flag 無法覆蓋 fixture source；混合真實型別／fixture source 的事件不能隱藏 synthetic evidence |
| Evidence / lineage | 相同數值的多筆支持證據全部保留；任何 fixture leaf 影響後代；核對嵌入來源、record、formula 與 dependencies |
| CLI / HTTP | 同一 ValidationError issues 結構；CLI exit 1，HTTP state／sensitivity 422；新增全域 `--root` 以驗證獨立資料包 |
| Snapshot / event | 驗證後才允許寫入；snapshot 讀取亦檢查模式與 fixture 內容；拒絕未保存的 sensitivity preview 作為 canonical snapshot |

共享設定中明確 `fixture: true` 的 assumptions、scenarios、graph edges 可在載入研究模式時排除，並記於 `loading_policy.excluded_shared_fixtures`。未引用的 fixture source registry 記錄允許保留。放錯到 research ledger 的 record 直接拒絕；缺少必要 research 檔也報錯，不能視為空資料。

驗證只檢查已宣告的 metadata 和一致性，不會自動閱讀網頁並驗明數字。未標 fixture 而冒充真資料的輸入仍需透過來源存證與人工查核防範。

## 3. 實際執行結果

以下為最終程式版本的執行結果；後續文件提交沒有改程式。

```text
$ python -m unittest discover -s tests -p 'test_*.py'
Ran 67 tests in 12.788s
OK

$ python -m engine.cli validate --demo
Validated 94 metrics, 0 issues; mode=DEMO

$ python -m engine.cli validate
Validated 94 metrics, 0 issues; mode=RESEARCH
```

原 26 個測試保留，新增 41 個有關輸入邊界、lineage 與跨入口拒絕的測試。UNI required market share 維持 **0.422（42.2%）**；SECZ 與 XLM 原有 deterministic regressions 亦通過。研究 validation 成功代表空資料包與規格合法，不代表已有 94 個真實數值。

### 跨入口驗收

| 案例 | 實際驗收 |
| --- | --- |
| 空 RESEARCH | CLI 合法；HTTP 200，94 個 metric value 全部 null，無檔案變更 |
| DEMO | HTTP 200，UNI required share 0.422，fixture 標示保留 |
| research ledger 放入 fixture | CLI 非零、HTTP GET state 與 POST sensitivity 422；包含 `RESEARCH_FIXTURE` 及 record 路徑；不回傳可用 metrics、不寫入 |
| duplicate YAML key | CLI 與 HTTP 同一 `YAML_DUPLICATE_KEY`，診斷有檔案／行／列，原檔不變 |
| 直接 calculate 呼叫 | 污染 project 在求值前拒絕，不能繞過 CLI loader |
| event / observation batch | malformed／fixture／混合來源／ledger 不一致時拒絕；不追加 observation、snapshot 或 changelog |
| snapshot create / save / read | mode 偽裝、nested fixture evidence、非法 project 與未保存 sensitivity 拒絕；先檢查再寫檔 |
| 合法研究結構的測試樣本 | 在暫存 project 驗證、API 及 research snapshot 可通過，證明防護不是一律封鎖 RESEARCH |

HTTP 測試實際啟動 loopback `ThreadingHTTPServer`，透過 `http.client` 呼叫 handler。CLI 測試使用 subprocess 與 `--root`。失敗副作用測試比較暫存 project 的完整檔案內容指紋。

「合法研究結構」樣本只是測試用的 synthetic scaffolding，用於測試 EXTERNAL source schema 分支，**不是真實來源查證，也未入庫 canonical research**。全部污染、偽裝、event／snapshot 測試只在 temporary project 或記憶體複本執行。

### 既有資料與快照相容性

```bash
git diff --exit-code 650cfdff4b025c48dfed3b98c7a56aa8face3caf -- spec data sources dashboard
# exit 0：受保護路徑沒有變更
git diff --check
# exit 0
```

在暫存 project 重跑 `bootstrap-demo`，既有兩份 snapshot 均回報 `existing`：

```text
306a92aa32ab33431b82 2026-03-31 existing
df1d2ede420426dc1ad1 2026-06-30 existing
```

前後全檔案 SHA-256 指紋一致，沒有新增檔案，兩份原快照逐位元保留。Canonical 的 188 筆 demo observations、0 筆 research observations、sources、assumptions、scenarios、events、30 個公式及其版本／鎖、dashboard 均未變更。

## 4. Example：錯放 fixture 的可定位拒絕

`tests/integration/test_boundaries.py` 在 temporary project 將一筆帶 fixture source 的 demo observation 放到 `data/observed/research.yaml`，執行 CLI validation 以及 HTTP state／sensitivity。

驗收要求同時成立：error code 含 `RESEARCH_FIXTURE`、診斷包含 record ID／research 檔案位置、CLI exit 1／HTTP 422、原檔與所有歷史 snapshot 不變。即使加 `--demo`，研究 ledger 的錯放仍拒絕；改寫 `fixture: false` 也無法掩蓋 synthetic source。

相關可重跑測試檔：

- [Schema / preflight](../tests/schema/test_preflight.py)
- [CLI / HTTP / event / snapshot integration](../tests/integration/test_boundaries.py)
- [Lineage / corroborating evidence](../tests/lineage/test_lineage.py)
- [既有 deterministic regressions](../tests/regression/test_regression.py)

## 5. 相容性與仍有的限制

- YAML 現在拒絕 aliases／merge、未知欄位、未加引號的日期與錯誤型別；使用明確欄位和 quoted ISO dates。這是 deliberate input-contract tightening，未支援的 v2 欄位不能偷偷加入 v1。
- 未完成 knowledge-time selector、public/system 時點區分、經濟 scope 與資產／規則各自的 cadence；原稽核 A-02、A-03、A-04 仍待修復。
- 未完成自包含 snapshot replay／digest tamper verification（P0-07），本次只增加模式、內容與 lineage 的發布前檢查。
- GET 在有可發布資料時仍沿用原有 snapshot 行為；純讀 API、跨檔 crash atomicity、並行發布及完整復原留待 P0-08。
- 已改善 fixture 傳播與相同數值的多来源 lineage；完整品質維度、transitive uncertainty 與 conflict resolution ledger 仍屬 P0-09。
- 尚無 verified live observations、來源內容存證、真實 research pack、成本後績效驗證或投資成果證據。沒有建立交易／scheduler／通知。

## 6. Action：只推進下一項 P0-03

下一項為 **v2 時間、scope 與 record 契約及遷移 ADR**：定義 economic period、knowledge time、valuation time 與四分類的關係，建立 v1／v2 compatibility matrix；缺失的歷史公開／首次取得時間保持 unknown，保留 v1 snapshot。

要回答的核心問題：每一次歷史估值，如何證明只用了在指定時間已公開或已取得的證據，並能清楚區分這兩種時間政策？
