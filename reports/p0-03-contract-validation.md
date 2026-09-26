# P0-03 驗收：v2 時間、scope、record 契約及遷移 ADR

**2026-09-26｜設計版本 `2.0-proposal.1`｜任務 P0-03 DONE｜軟體仍為 0.1.1**

## 產物與核對

| Backlog 驗收 | 產物與具體約束 |
| --- | --- |
| economic period／knowledge time／valuation time 分離 | [v2 YAML 契約](../docs/planning/CONTRACT_V2_PROPOSAL.yaml) 各設獨立欄位與時間精度；[ADR](../docs/planning/ADR-0001-V2-TIME-SCOPE-MIGRATION.md) 定義兩種 query policy、日精度保守起算與「先篩資格、後套 supersession」 |
| 四種 classification 與 scope 分離 | 保留 OBSERVED／DERIVED／ASSUMPTION／SCENARIO 四類；`fixture` 旗標與四種 economic scope 是另外維度。`DERIVED/REALIZED` 不可吃 future scenario 的經濟收益 |
| legacy 時間不虛構、snapshot 保留 | `published_at`、`first_seen_at`、`ingested_at` 缺直接存證維持 null，v1 demo 使用 LEGACY_V1 顯示，不進歷史績效；本次沒有修改 `data/snapshots` |
| metric concept／role／record 選用 | [相容矩陣](../docs/planning/V1_V2_COMPATIBILITY.md) 對應全部 30 個 v1 公式，另列 observed realized 與 forward assumption 使用不同 input role 的範例 |

## 實際檢查

從 repository 根目錄執行：

```text
python -m unittest discover -s tests -p 'test_*.py'
Ran 67 tests in 12.039s
OK

python -m engine.cli validate --demo
Validated 94 metrics, 0 issues; mode=DEMO

python -m engine.cli validate
Validated 94 metrics, 0 issues; mode=RESEARCH

git diff --check
# exit 0
git diff --exit-code HEAD -- spec data sources engine dashboard tests
# exit 0
```

另外以現有 strict YAML reader 解析提案與 backlog，核對四類分類、四種 scope、role references、P0-03 DONE/P0-04 next、51 個 task、相容矩陣涵蓋全部 **30/30** 個 v1 formula ID，並檢查修改文件的本地相對連結。以上是**設計完整性檢查**；67 個 runtime tests 驗證 v1 沒退化，不驗證尚未寫入 engine 的 v2 selector。

## 資料品質與限制

- 沒有新 OBSERVED 市場值。既有真實 research observation 仍為 0；DEMO 的 188 observations、17 assumptions、1 scenario 與兩份 snapshot 均保持 fixture／原檔未變。
- 新增的時間／scope 條件是 **PROPOSED contract**；v1 `calculate(as_of=...)` 仍依經濟日期選值，尚未能阻止晚發布資料滲入歷史回測。v1 `net_burn_yield` 仍有情境混用，不應作已實現收益解讀。
- 研究源的實際 publication 時點／原文內容尚未取得；本次不把示例日期或欄位當真實金融證據。現有 demo fixture 仍不代表當時可知。
- P0-04 實作雙時間 selector，P0-05 分流經濟 scope，P0-06 修規則 cadence；P0-07/08 的 snapshot replay 與發布原子性也尚未完成。這些未完成工作仍不能當成 G0 通過。

## 下一項

依 [backlog](../docs/planning/IMPLEMENTATION_BACKLOG.yaml) 執行 **P0-04：雙時間 selector 與歷史重述重播**；優先用 ADR 的 6 月／8 月／9 月範例寫出負向測試，再實作 selector。
