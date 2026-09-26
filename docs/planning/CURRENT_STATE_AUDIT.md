# 現況稽核與實盤前缺口

**審查日期：2026-09-25｜基準 commit：68f19531cfd77bc2c70006921a6402e7a10f04f6**

本文件保留 2026-09-25 的檢查與程式碼推論。下列探針與缺口描述屬於原始基線；後續修復以這裡的進度表與獨立驗收報告為準。

## 修復進度（2026-09-26）

| 原始發現 | WP-01 後狀態 |
| --- | --- |
| A-01：fixture 模式隔離 | P0-01 完成：計算、CLI、HTTP、event、snapshot 拒絕 synthetic 研究輸入；共享 demo 配置依明示政策排除 |
| A-07：輸入／公式驗證 | P0-02 完成 strict YAML、型別、唯一 ID、版本鏈與 formula DAG；完整量綱與 normalization 仍屬 P1-03 |
| A-08：品質／lineage | 修復相同數值的多筆支持證據遺失與 fixture 傳播；完整不確定性／衝突選取理由 P0-09 未完成 |
| 其他發現 | 保持原有待辦；歷史可知時間、scope、混合頻率、完整重播與發布復原未在 WP-01 解決 |

證據：[WP-01 validation](../../reports/wp-01-validation.md)，implementation commit `e8b4d55520ea71f1d626a9286fa64a30cd745f3d`。現有 67 tests 通過，真實 observation 仍為 0。下一項為 P0-03。

## 1. 已具備的基礎

| 項目 | 現況 |
| --- | --- |
| canonical / engine / UI 分離 | 已有，Python + YAML + local HTTP + vanilla JS |
| 模型 | 30 個公式、94 個 metric 定義，UNI／SECZ／XLM |
| observed | 188 筆 demo fixture；research observation 為 0 |
| 歷史 | 4 個 demo 季末；2 個已保存 demo snapshot |
| 規則 | 三資產多期規則，保留 triggered rules 並取最高 severity |
| 來源 | 目前只有 fixture provenance；沒有已入庫真實來源 |
| graph | 13 節點；現有關係仍為 ASSUMED |
| 版本 | 公式 version/lock、append-only 檢查、snapshot 比較 |
| 自動擷取／交易 | 未實作 |

這些能力足以演示研究管線與進行 deterministic regression；不能推論真實研究的 completeness、時點正確性或投資有效性。

## 2. 本次實際執行

~~~bash
python -m unittest discover -s tests -p 'test_*.py'
# Ran 26 tests ... OK

python -m engine.cli validate --demo
# Validated 94 metrics, 0 issues; mode=DEMO

python -m engine.cli validate
# Validated 94 metrics, 0 issues; mode=RESEARCH
~~~

RESEARCH 驗證通過，代表現行規格與空資料集沒有觸發既有 validator；不代表已具備研究資料。

另以記憶體複本執行以下四個探針，未修改 canonical 檔案或建立 snapshot。

| 探針 | 操作 | 實際結果 | 意義 |
| --- | --- | --- | --- |
| fixture 模式邊界 | 把一筆 demo uni_market_cap 放入 demo=False 的 project.observations | mode=RESEARCH、fixture=true、value=6,050,000,000，validation errors=[] | 隔離依賴檔名；沒有完整模式拒絕機制。數字是 fixture |
| 歷史可知時間 | 同一 as_of 兩個版本，修正版 published_at=2026-09-01；查 cutoff=2026-07-31 | 選到 audit-correction | selector 不讀 publication time；新增欄位本身不能防止 look-ahead |
| 混合頻率 | 在四個季度 observation 中新增 2026-06-29 的 uni_market_cap | UNI／SECZ／XLM 多期規則均出現 Insufficient consecutive quarterly periods | 全域 observation 日期被當作規則期間，單日資料干擾跨資產規則 |
| YAML 重複鍵 | safe_load 解析同一 mapping 兩個 value 鍵：1、2 | 得到 value: 2，未報錯 | 欄位可被靜默覆蓋 |

publication 探針的 published_at 是測試用 metadata；現有正式 schema 尚未支援。它證明現行 selector 不提供 knowledge-time 保證，不是宣称一筆正式的歷史資料已被污染。

## 3. 缺口清單

### A-01 / P0：RESEARCH 無完整 fixture 防火牆（已重現）

- 位置：engine/storage.py 的 load_project；engine/validation/checks.py 的 validate_project。
- loader 依 research.yaml／demo.yaml 分流，assumptions/scenarios 有 fixture 過濾，但 research 檔內的 fixture observations/events 沒有全域拒絕。
- validator 核對 source 與 observation 的 fixture 一致性，沒有把 RESEARCH 含 synthetic input 視為發布錯誤。
- 後果：即使值仍帶 fixture 標籤，RESEARCH 模式名也會造成錯誤信任。
- 驗收：錯放 fixture 必須明確拒絕，不能靜默丟棄；transitive lineage／event／graph／snapshot 同樣檢查。DEMO 保留可用。
- 任務：P0-01。

### A-02 / P0：缺少 point-in-time 可知時間（已重現）

- 位置：engine/formulas/runtime.py 的 _select。
- 現在只比較 as_of_date/effective_date；新修正版只要 economic date 過去，就會取代舊值。
- 後果：歷史研究可能用到當時尚未發布的重述，回測與「當時判斷」不可相信。
- 驗收：經濟日期、公開日期、首次取得日期與 system ingestion 分開；同一 economic cutoff + 不同 knowledge cutoff 可以重播不同合法版本。
- 任務：P0-03、P0-04。

### A-03 / P0：季度規則使用全域日期（已重現）

- 位置：engine/thesis/rules.py 的 evaluate_theses。
- 取所有 metrics 的日期，再以 70–105 日判斷季度；所有 OBSERVED leaves 又被要求與該日相等。
- 後果：每天更新價格，可能使季度規則永遠缺資料；實際財報、鏈上 TTM 與價格自然不會同日。
- 驗收：每條 rule 指定資產、fiscal cadence、期間對齊、價格 valuation cutoff、freshness； unrelated daily quote 不得改變季度樣本。
- 任務：P0-06。

### A-04 / P0：情境經濟收益參與當期 thesis（程式審查）

- 位置：spec/formula-registry.yaml 的 gross_uni_accrual/net_uni_accrual/net_burn_yield；spec/thesis-rules.yaml。
- gross 含由 TAM scenario 推導的收入，net_burn_yield 又進入 thesis rules。
- classification=DERIVED 正確，但沒有表達「已實現」與「未來情境」；來源分類與經濟時間範圍是兩回事。
- 驗收：realized accrual、run-rate、forward scenario、reverse requirement 是不同 metric/scope；當期規則拒用 forward scenario。原 regression 以 demo 模型 v1 保存。
- 任務：P0-05、P2-01。

### A-05 / P0：snapshot 未達完整離線重播（程式審查）

- 位置：engine/snapshots.py 的 make_snapshot/read_snapshots/save_snapshot。
- 已保存結果、輸入、公式版本及 signature；未封存完整 expression、rule／dictionary／graph 內容、code revision 與 runtime lock、原始證據。
- read_snapshots 直接讀 JSON，沒有重新核對 snapshot digest；來源原文也沒有 digest 存證。
- record_fingerprints 含目前所有 records，包括 snapshot cutoff 之後的紀錄；這不等於 selected evidence manifest。
- last_changed 依建立時間排序，事後產生舊日期 snapshot 可能干擾業務時間的前一版定義。
- 驗收：deterministic compute manifest 與 commit timestamp 分離；在乾淨環境重播、篡改拒絕、歷史與 current track 分離。
- 任務：P0-07。

### A-06 / P0：讀 API 寫入，發布缺少完整事務（程式審查）

- 位置：engine/server.py 的 GET /api/state、payload；engine/propagation/ingest.py 的 commit_event。
- GET 可以產生 snapshot；ThreadingHTTPServer 允許同時請求。YAML、snapshot、changelog 分次寫入，沒有跨程序鎖與完整 crash recovery journal。
- 目前事件 ID 重複有檢查，但不等於整個發布流程可 idempotently recover。
- 驗收：GET 不變更任何 tracked data；明確 publish、鎖、compare-and-swap／journal、故障恢復測試、retry 不重複入帳。
- 任務：P0-08。

### A-07 / P0：嚴格解析與 schema 邊界不足（部分已重現）

- 位置：engine/storage.py、engine/validation/checks.py、engine/formulas/runtime.py。
- YAML 重複鍵可靜默取最後值。sources 轉 dict 前需拒絕重複 ID；supersession 已有 parent/metric/class 檢查，仍需自循環／多節點循環／非法版本鏈檢查。
- 公式 graph 循環現在於排序時報錯，應提升為 preflight 明確診斷；量綱、unknown keys、合法 timestamp、非有限數值皆須有負向案例。
- 驗收：在計算與發布前 fail closed，輸出可定位檔案／record／field 的錯誤；CLI 不以 traceback 作唯一診斷。
- 任務：P0-02、P0-10、P1-03。

### A-08 / P1：品質標示未充分傳播（程式審查）

- 位置：engine/formulas/runtime.py 的 _leaf、computed confidence。
- 葉節點主要依 source tier 決定 confidence；derived 主要看直接 dependencies 的 classification。多層 DERIVED 可能使上游 assumption/scenario 不再反映於 confidence。
- 保留 lineage 是優點，但一個 SOURCE_BASED 文案仍可能使人過度信任結果。單一 tier 也無法代表資料新鮮度或量測定義正確。
- 驗收：transitive uncertainty、freshness、coverage、conflict 分開；原文來源再高 tier，也不能把預測內容視作 realized observation。
- 任務：P0-09、P1-08。

### A-09 / P1：metric concept 與 evidence classification 綁死（程式審查）

- 位置：spec/canonical-schema.yaml、calculate 的 definition.class 分流。
- effective protocol fee 現為 ASSUMPTION 類型；未來有實測 fee 時不能把舊 assumption 改成 observed。
- 驗收：保留語義 metric 與不同 input role／record classification；例如 realized_effective_fee 與 scenario_effective_fee，各自有來源或 rationale，再由 context 選擇。遷移不得改寫歷史。
- 任務：P0-03、P0-05、P1-03。

### A-10 / P0 研究門檻：資產經濟口徑不足（模型審查）

| 模型 | 現有可用部分 | 進一步缺口 |
| --- | --- | --- |
| UNI | gross/net、兩種 required share、20M budget 情境 | 實際 fees/burn/treasury/vesting 對帳；stock vs flow；分配不等同新增鑄幣；burn 金額不能重複加入 terminal value |
| SECZ | 六收入流、growth/leverage、EV reverse hurdle | 公開總收入可能有而六分項沒有；EBITDA→FCF、稀釋股數／warrants、現金債務、折現與終值 |
| XLM | 採用／需求分層、fee diagnostic | 需求存量重疊、sponsorship、速度、供給、參數版本；capture ratio 不是價格模型 |
| TAM | scenario 基本敏感度 | 股票／基金／信用、原生／wrapped 權利、跨鏈重複量、可服務市場與實際可交易量 |

- 現有 standalone SECZ RequiredFCF = EV / multiple 是終值等於當前 EV 的簡化壓力問題，不能直接冒稱完整 intrinsic valuation。
- 驗收：對帳、單位／時間一致、範圍與適用性明示，見模型規格。
- 任務：P1-04～P1-07、P2-01～P2-06。

### A-11 / P1：宇宙與可交易工具需分離（程式審查）

- initial core 的設定不能等於「已完成 primary verification／可交易」；SECZ 現有 investability 仍 unknown。
- 公司、協議、網路、基金、股票／token 是不同 entity/security。不能把某公司成功自動歸屬同名 ticker。
- 驗收：研究核心、投資 eligibility、資料 readiness、value-capture evidence 分開；promotions 有證據／核可者／原因與版本。
- 任務：P1-02、P2-08。

### A-12 / P0 投資門檻：不存在 alpha／淨報酬驗證（範圍確認）

- 沒有 forecast journal、事前決策、可執行價、交易成本、持倉／基準、樣本外協議與歸因。
- 三資產、四期 synthetic history 不能支持投資統計結論。
- 驗收：研究／模擬／實盤結果分離，樣本不足不升級為獲利承諾；無需為了通過門檻勉強交易。
- 任務：P3 全部、P4。

## 4. 修復策略與避免回歸

1. 小工作包先補 boundary tests，再改 engine；現有 26 tests 保留。
2. schema／formula v2 以新版本與新 record 引入；舊 snapshots 與 fixtures 原樣保留。
3. 成熟功能不重寫：表達式 evaluator、DAG 與簡單 UI 繼續使用，只有已辨識風險或新需求才擴張。
4. 強制 migration/replay tests；不能把原預期值「更新成新結果」當作修復 drift。
5. 指標通過要伴隨證據路徑、測試輸出與 review；範例資料不能證明 live readiness。

## 5. 本次審查的限制

這是針對 correctness、provenance 與投資研究可用性的範圍審查。未完成全面安全稽核、效能壓測、跨作業系統驗收、chain 合約審計或完整真實財務核對。某些風險來自程式碼審查而非故障注入實驗，已逐項標明，後續以 backlog 驗收案例確認。
