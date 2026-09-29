# P0-10 / G0 整合驗收

**2026-09-29｜軟體 0.1.8｜G0 工程驗收 PASS；決策級研究發布 BLOCKED**

## 固定環境與 CI

`g0-environment.json` 固定 CPython 3.12.14、PyYAML 6.0.3；`requirements-g0.txt` 與 manifest 需一致。`.github/workflows/g0.yml` 在 PR 和 main push 上使用 Ubuntu 24.04、固定 Python patch 與 PyYAML 版本執行 `python -m scripts.g0_gate`。入口先比對本機版本，再跑完整 unittest、DEMO 與 RESEARCH 驗證，逐項報出結果。未符合版本即失敗；其他 Python 3.11+ 開發環境仍可執行一般程式，但不能宣稱重現這份 G0 報告。CI runner 映像及 actions major tags 未作位元組鎖定；可重現性限於上述解譯器、依賴版本、儲存庫版本與快照自身的 compute manifest。

## 負向整合與獨立 golden

新增暫存專案整合案例覆蓋：研究 ledger 被 fixture 污染時，兩種 CLI 模式、snapshot 與 HTTP 均拒絕且不寫檔；晚到重述在 system-as-known 不可見，public reconstruction 僅使用已公開證據；將已實現 burn 錯置為未來 scope 在 strict loader 被拒；v2 bundle 篡改被 digest 拒絕、原始 artifact 仍可重播；v1 event 在 ledger 落盤後故障時讀 API 回 503，recover 完成後重試不重複且先前 v2 bundle 可重播。兩份 v1 DEMO 快照 SHA-256 維持原值：`cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e`、`6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`。

`tests/regression/test_g0_golden.py` 用 Python `Fraction`/基本乘除對原有 synthetic fixture 的輸入另算預期，不讀 formula expression，也不依引擎輸出重寫 `tests/regression/fixtures.yaml`：

| 合成 fixture | 獨立算式 | 鎖定預期 |
| --- | --- | ---: |
| UNI legacy reverse | `(242m + 180m) / (4tr × 2 × 1 × 1 × 1.25 / 10000)` | 0.422 |
| SECZ reverse | `2bn / 20 = 100m FCF`; `100m / .25 = 400m revenue`; `(400m / 100m)^(1/5) − 1` | 0.3195079107728942 CAGR |
| XLM diagnostic | `1bn × .00001 × .2 = 2000` fee；`((500−490)/490) / ((12−10)/10)` | 2000 USD；0.1020408163265306 ratio |

這些數字只支持 fixture 算術回歸，**不是**真實 UNI／SECZ／XLM 的市場觀測或獲利驗證。

## 執行與發布門檻

```bash
python -m pip install -r requirements-g0.txt
python -m scripts.g0_gate
# 127 tests OK；DEMO 與 RESEARCH 各 94 metrics、0 issues；環境匹配
python -m scripts.g0_gate --status-only --require-ready
# 非零退出：decision-ready research 仍被封鎖；不重跑測試
```

G0 的工程檢查通過，但 research v2 真實 OBSERVED 仍為 **0**，G1 尚未完成。`g0_gate` 列出全部未完成且 priority=P0 的任務，並要求 P1-09、真實 observation 與測試 gate 一同通過才可標記 `DECISION_READY`；現在一律回報 `BLOCKED`。v2 bundle 的 `purpose` 仍為 `AUDIT_ONLY`，v1 快照仍是 legacy，沒有發布可供決策的研究包。未完成的 P0 優先級任務按階段列於下表；P0-10 在本工作包交付後為 DONE：

| 待完成階段 | P0 優先級任務 |
| --- | --- |
| P1 | P1-01、P1-02、P1-03、P1-04、P1-05、P1-06、P1-07、P1-09 |
| P2 | P2-01、P2-02、P2-03、P2-05 |
| P3 | P3-01、P3-02、P3-03、P3-04、P3-07、P3-08、P3-10 |
| P4 | P4-01、P4-02、P4-04 |

下一項依 backlog 為 **P1-01：Source staging 與原始證據存證**。此驗收不新增金融來源、observation、公式或 snapshot；CI 通過只代表明示的工程邊界通過，不能證明來源真實性、投資模型完整性或 alpha。
