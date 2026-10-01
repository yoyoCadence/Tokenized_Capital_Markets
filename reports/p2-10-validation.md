# P2-10 第一增量：原文定位、審阅和研究發布

**2026-10-01｜軟體 0.1.20｜手動工程流程已實作｜P2-10 IN_PROGRESS**

先審查並合併 PR #19：GitHub G0 CI 成功、無衝突或 review thread，本地固定 CPython 3.12.14／PyYAML 6.0.3 環境重跑 199 tests、DEMO／RESEARCH 各 94 metrics / 0 issues，工程 PASS、真實研究 BLOCKED。PR 原為 Draft；已轉 ready 並以 exact head `fe06fd73884e68fda9588c31f9b76a18d77832da` 合併為 `794cb73599c3476258c8618301df391c87b48e91`。這證明 repository 層可前進，無法單靠 GitHub 判定前一個 ChatGPT session 的內部卡住原因。

## 本次工程結果

- `refresh-plan`、`refresh-preview`、`refresh-stage`、`refresh-review`、`refresh-status`：strict YAML／JSON、唯一 literal token 或明確原文 byte span、版本 SHA-256、先來源核准再擷取核准，無 AI SDK 或 provider key。
- SEC 財報 adapter 只接受明示單位、日期、entity／measurement basis 的 direct OBSERVED/REALIZED；不推定缺值、倍率、FX 或歷史時區。原文日期支持 ISO、MM/DD/YYYY 和英文月份。
- Uniswap 治理 adapter 只接受官方 source kind/host、PLANNED／ANNOUNCED／APPROVED 與有效版本鏈；治理核准不等於 burn、LIVE 或持有人經濟收益。
- review、canonical record/event、audit snapshot、changelog 共用 redo journal。原文在 repo 外，snapshot `.8` 封存 proposal/review metadata、digest、程式和資料供离線回放；canonical ingestion 用實際 review/publish UTC，不能回填 staging time。

## 驗收範圍

`tests/integration/test_research_refresh.py` 使用 disposable project 和 **合成原文**，不寫入本 checkout 的研究證據。覆蓋財報與治理兩條審閱發布及離線回放、無 provider key 的 CLI、preview 唯讀、原文 absent/ambiguous token、假引用、錯單位、數值倍率、錯期間、unknown fields、duplicate YAML、fixture 邊界、未審來源、原文與提案 instruction markers、原文篡改、staged candidate 修改、HOLD／REJECTED、實際 ingestion 前後可知時間、發布中斷恢復及冪等重試。

詳見 [操作說明](../docs/RESEARCH_REFRESH.md)。人工 reviewer 欄位是明確操作紀錄，程式不認證人的身分或代替其語義審閱。byte matching 不能自行證明 entity／會計概念相同；有限 marker 偵測也不宣稱捕捉所有 prompt injection。

## 驗證結果

- G0 固定環境：CPython 3.12.14、PyYAML 6.0.3。
- `python -m scripts.g0_gate`：完整 suite **210 tests OK**（55.491 秒），DEMO／RESEARCH 各 **94 metrics、0 issues**，G0 工程 **PASS**；新增 11 個 refresh integration tests。
- 本 checkout 真實 v2 source、observation、event、refresh proposal／review 均為 **0**；決策級研究發布 **BLOCKED**。
- 原 v1 demo snapshot SHA-256 維持 `cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e` 與 `6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`。

## 尚未完成

這個增量的 replay 依靠已存證的手動輸入。自動發現／polling、provider acquisition、PDF/OCR 和真實官方原文端到端研究驗收尚未完成；沒有將整個 P2-10 標 DONE。下一項仍為 P2-10：補足取得 adapter 與真實文檔操作驗收，優先解鎖 P1-06 官方財報原文；P1-05／06／07、P2-04／08 的研究證據缺口保持可見。
