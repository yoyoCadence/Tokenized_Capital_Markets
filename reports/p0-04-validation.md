# P0-04 驗收：v2 雙時間 selector 與晚發布重述回放

**2026-09-26｜軟體 0.1.2｜P0-04 DONE｜P0-05／06／07 未完成**

Implementation commit：[`30036560549a1db9923a03647e1645b02268b3ee`](https://github.com/yoyoCadence/Tokenized_Capital_Markets/commit/30036560549a1db9923a03647e1645b02268b3ee)。

## 1. 交付範圍

新增 `engine/temporal/` 的獨立、唯讀 v2 evidence selector，並以 `python -m engine.cli temporal-select` 對外提供。`spec/v2/` 保存 unit registry、metric concept 與 input role，`sources/v2/` 保存來源版本，`data/v2/observed/` 分離研究與 demo ledger。所有 v2 YAML 走既有 strict loader、再走 v2 semantic validation；直接傳入記憶體 project 的選值亦先驗證。

查詢必須明示 `economic_cutoff`、`knowledge_cutoff`、`valuation_at`、`required_scope` 與兩種不同政策之一：

| Policy | 必要證據 | 回傳的主張 |
| --- | --- | --- |
| `AS_KNOWN_BY_SYSTEM` | 該版來源已公開，實際 `first_seen_at`、`ingested_at` 均不晚於知識截止 | 系統在當時可取得並使用；缺任一時間則拒選 |
| `PUBLIC_INFORMATION_RECONSTRUCTION` | 該版來源的公開時點可由 locator 查證，且不晚於截止 | 當時公開可知；輸出 `reconstructed: true`，**不宣稱系統當時已有它** |

先過經濟期間、公開／取得資格，再處理同期間的整條 supersession 鏈。同值多來源保留所有 record/source ID；同期間不同值回 `CONFLICT` 與全部衝突 ID，無任意優先來源。未知公開時間、未知系統首次取得、無時區的 date-only 發布都無法進歷史選值；日期精度採**來源時區隔日零點**，跨日報價保存原時區日期。報價另檢驗 venue、timestamp、valuation cutoff 與角色的最大資料齡。

## 2. 實際執行的驗證

```text
python -m unittest discover -s tests -p 'test_*.py'
Ran 79 tests in 12.927s
OK

python -m engine.cli validate --demo
Validated 94 metrics, 0 issues; mode=DEMO

python -m engine.cli validate
Validated 94 metrics, 0 issues; mode=RESEARCH

python -m engine.cli temporal-select --role secz_quarterly_revenue \
  --economic-cutoff 2026-03-31 --knowledge-cutoff 2026-09-26T05:00:00Z \
  --valuation-at 2026-09-26T05:00:00Z --scope REALIZED \
  --policy AS_KNOWN_BY_SYSTEM
# mode=RESEARCH; value=null; reason=NO_ELIGIBLE_RECORD

git diff --check
# exit 0
git diff --exit-code HEAD -- spec/canonical-schema.yaml spec/formula-registry.yaml \
  spec/formula-lock.yaml spec/assumptions.yaml spec/scenarios.yaml \
  data/observed data/events data/snapshots sources/sources.yaml dashboard
# exit 0
```

其中新增 **12** 個 P0-04 回歸測試，使用 temporary project 或記憶體 synthetic fixtures；原 67 項保持通過。主要測試案例：

| Cutoff／案例 | System-as-known | Public reconstruction |
| --- | --- | --- |
| 2026-06-30，Q1 原報表公開，重述未公開 | 100 | 100 |
| 2026-08-20，重述已公開但本系統 9 月才取得 | 100 | 90 |
| 2026-09-03，兩版均已取得 | 90 | 90 |

`100`／`90` 是**測試專用合成數字**，不是 SECZ 研究值。其他案例檢查：日期與時區精度、DST 次日零點等號邊界、未知歷史時間、Q1 尚未結束的誤標觀測、引用尚未取得的來源、同值來源保留與不同值衝突、跨季最新值、非連續可知的多層修正、venue 本地日跨 UTC 午夜、未來報價與 stale 報價、角色隔離 OBSERVED／ASSUMPTION、CLI 無 policy 拒絕與查詢前後全檔案雜湊一致、研究 ledger 含 fixture 明確拒絕。

兩份原 demo snapshot 未改，SHA-256：

- `306a92aa32ab33431b82.json`: `cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e`
- `df1d2ede420426dc1ad1.json`: `6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`

## 3. 資料品質與界線

- RESEARCH v2 source 與 observation 均為 **0**。固定的 `spec/v2` 是概念與角色定義，沒有虛構市場數據；測試資料一律 `fixture: true` 且留在暫存測試資料包。
- OBSERVED、ASSUMPTION 與 SCENARIO 保留原 classification；時間政策、scope 與 `fixture` 是不同維度。P0-04 只選 source/input record；`DERIVED` v2 尚未可透過此 selector 存入或重算，留待 P0-05。
- 現有 v1 `calculate(as_of=...)`、thesis、Dashboard 與 snapshot 沒有接入 v2，**仍不可用於事前 point-in-time 回測**。P0-05 的 scope 分流與 P0-06 的季度規則才會往完整財務分析推進；P0-07 的自包含 replay 與不可變發布也尚未完成。
- 本次 selector 是唯讀的 deterministic 重查；尚未建立 v2 snapshot 或受控 append-only ingestion。正式研究仍須對來源原文、發布時點、時區及 first-seen 紀錄做實際存證，不能僅信任 metadata。Windows 若沒有 IANA 時區資料，date-only IANA 查詢會 fail closed；timestamp 帶明確 offset 的資料不受此限制。

## 4. 下一項

依 [backlog](../docs/planning/IMPLEMENTATION_BACKLOG.yaml) 進入 **P0-05**，把已實現、年化、模型期間與反推要求拆成不同 formula roles 和 scope；保留既有 v1 的 42.2% demo regression。
