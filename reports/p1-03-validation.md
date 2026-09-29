# P1-03：財務／鏈上資料字典與 normalization 驗收

**2026-09-29｜軟體 0.1.11｜工程 DONE；真實財務／鏈上 OBSERVED = 0**

## 原則與實作

原文直接量測保留 `OBSERVED` 和原單位。`spec/v2/normalization.yaml` 以概念、stock／flow／ratio、GAAP／IFRS／adjusted、gross／net、合併範圍、持續營業、財務曆及期間可比性定義語義；`normalization-lock.yaml` 為每個公式保存獨立版本與完整輸入／輸出／運算簽章。v2 selector 將 `measurement_basis` 納入衝突與重述身分：相同數值但 GAAP 與 adjusted 不同仍是兩筆待分辨證據；role 可指定必要口徑，resolution 不能混合兩種口徑。既有無此欄位的資料可繼續載入，但不能用來正規化。

`normalize-report` 讀取確切 raw observed ID 及有序前一步 DERIVED 結果，驗證來源可用時點、固定知識政策和所有上游相容性，產出帶公式 ID／版本／簽章、依賴 ID、原始 record/source IDs、fixture 旗標的唯讀稽核報告。不得將此結果直接寫入 canonical OBSERVED 或自動接入經濟／thesis 模型。

| 公式 | 輸入 → 輸出 | 限制 |
| --- | --- | --- |
| `secz_scale_musd` | 百萬美元 SECZ 營收 × 1,000,000 → USD | flow，同期間，保留原觀察值 |
| `secz_fx_eur_usd` | EUR 營收 × USD/EUR 平均匯率 → USD | 匯率為同一經濟區間、正值、當時可知；非單日 spot quote |
| `secz_ttm` | 連續四個財季 USD 營收之和 → TTM | 同一口徑、曆法及可比期間 |
| `secz_ytd_quarter` | 當期累計 − 前期累計 → 單季 | 同一財年與相鄰季度 |
| `secz_revenue_cagr` | 兩個完整財年的 USD 營收 → fraction | 同曆法與財年期末；基期至少 USD 1、當期正值。USD 1 是本版分析門檻，並非普遍統計定律 |
| `uni_percent_to_bp` | 原始百分比 × 100 → basis points | ratio；1.2% 對應 120 bp |

六項是特定概念的第一版映射。沒有通用股數、供給、即時匯率或鏈上總額換算。不同會計口徑、gross/net、fiscal calendar 或重組前後不可比期間直接拒算；負基期、零或接近零的 CAGR 分母也拒算。精確 ID 有另一個同期間同口徑且已可知的版本時，本報告拒絕自行取捨。日後須依人審 resolution 與 append-only 派生紀錄契約建立正式整合。

## 驗證

- `python -m unittest discover -s tests -p 'test_*.py' -q`：**145 tests OK**，包含合成四季 lineage、YTD／FX／百分比、CAGR 負與近零基期、單位與期間錯配、不同會計口徑同值衝突、未可知來源、公式鎖變更及 CLI 只讀檔案指紋。
- `python -m engine.cli validate --demo` 與 `python -m engine.cli validate`：各 **94 metrics／0 issues**。
- `python -m scripts.g0_gate`：工程 gate **PASS**，決策級研究 **BLOCKED**；真實 observation 仍 0。
- 舊 v1 DEMO 快照 SHA-256：`cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e`、`6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`，與原紀錄一致。v2 compute bundle 已包含兩個 normalization 登錄檔，schema `2.0-compute-bundle.5`；舊 bundle 依原版本程式重播。

測試數字均在隔離 synthetic fixture，並非 SECZ 業績、UNI 收益或市場匯率。SECZ 真實財年及 comparable accounting 尚未核對；來源連結與暫存原文未建立可發布的財務觀察值。P1-04 將處理價格、供給、股本、EV 等不同 stock／price 口徑；G1 與決策級發布仍 BLOCKED。
