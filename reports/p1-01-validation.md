# P1-01 來源暫存與原始證據存證驗收

**2026-09-29｜軟體 0.1.9｜P1-01 工程流程 DONE；真實來源／OBSERVED 仍為 0**

## 採集、審閱與發布邊界

`MANUAL_FILE_V1` 僅處理使用者明確提供的本機原文檔。`source-stage` 用 strict YAML 讀 metadata，檢查 HTTPS URL、publisher、title、document kind、source date 或 null、tier、明確的 v2 metric IDs、原文 locator、權利狀態與宣告的 MIME。記下本次真實嘗試與取得時間，計算 SHA-256／位元組數，將原檔內容定址保存在指定的**專案目錄外**。Git 僅保存 `sources/staging.yaml` 的 metadata／digest，沒有檔案路徑或原文；沒有捏造來源公開時間、首次系統取得或 canonical ingestion time。檔案不存在或過大時，暫存 `FAILED` 且 `retrieved_at`、digest 為 null。來源日期未知也可以暫存，不能核准。

`source-review` 要求人工 reviewer、理由與決定。`HOLD`／`REJECTED` 留在 staging；`APPROVED` 須有原檔、有效 source date、已知權利狀態，重新核對外部原檔 digest，再把 review 和 `sources/v2/sources.yaml` 的**來源 metadata** 於同一 redo journal 發布。source ID 的後續版本以新 ID、`supersedes_id` 附加，舊版保持；重試相同 review ID 不重複。核准不會建立 `data/v2/observed/research.yaml` 的數值或宣稱發行人財務／合約已實現；之後每筆 observation 仍需獨立核對 period、口徑、當時可知時間及原文定位。

已核准的 v2 source metadata 另含原文 SHA-256、位元組數、MIME、locator、review ID。`snapshot-v2` bundle `2.0-compute-bundle.3` 封存 source registry 與 staging/review ledger 的位元組，離線 replay 可核對這些 metadata；**原文位元組不在 bundle**，驗證原檔須有外部 artifact store。現有舊 bundle 仍需原版本程式環境；兩份 v1 DEMO snapshot 原樣保留。

## 操作範例與驗證

以下 metadata 與檔案為使用者在 repo **以外** 建立的來源候選，不是本次新增的真實研究資料。Metadata 必填：`url`、`publisher`、`title`、`document_kind`、`source_date`（未知時 null）、`tier`、`covered_metrics`、`locator`、`rights`（`PUBLIC_REDISTRIBUTABLE`／`RESTRICTED`／`UNKNOWN`）、`media_type`；可選 `supersedes_id`。`document_kind` 明示 FILING／GOVERNANCE_PROPOSAL／OFFICIAL_RELEASE 等來源性質，不把提案視為執行證據。URL 不收登入資料、query 與 fragment；storage 必須為絕對路徑且位於 repo 外。此版不自動連網擷取，MIME 由提供者宣告，人工需核對原檔、日期、授權與頁碼／表格定位。

```bash
python -m engine.cli source-stage --id candidate_001 \
  --metadata /private/source-metadata.yaml --file /private/source.pdf \
  --store-dir /private/source-artifacts
python -m engine.cli source-verify --id candidate_001 --store-dir /private/source-artifacts
python -m engine.cli source-review --id candidate_001 --review-id review_001 \
  --decision APPROVED --reviewer 'Research reviewer' \
  --reason 'Source date, original file and rights checked' \
  --store-dir /private/source-artifacts
python -m engine.cli source-status
```

`python -m unittest discover -s tests -p 'test_*.py' -q`：**132 tests OK**。新增五項隔離測試涵蓋成功採集與獨立 digest、核准前零 source/observation、核准後原檔不入 repo／snapshot、外部原檔竄改拒絕、未知日期或擷取失敗留 staging、含憑證 URL／重複 YAML／repo 內 raw path 拒絕、跨 staging／source registry 故障恢復與 review 重試、來源版本附加不改舊版。`validate --demo` 與 `validate` 各 **94 metrics、0 issues**；原兩份 v1 DEMO SHA-256 仍為 `cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e`、`6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`。

## 尚待處理

本次沒有將 `RESEARCH_SOURCES.md` 的網頁線索或任何私有檔案直接入庫。專案的 `sources/staging.yaml`、v2 source registry 及 research observation 均空；沒有外部原文 hash 可宣稱已核實。外部 store 的保管、存取控制、備份、資料授權及 reviewer 真實身分仍由操作者與後續治理處理；SHA-256 證明所持位元組一致，不證明網站內容、發行時間或經濟口徑正確。Journal 保障 repo 內兩份 metadata ledger 一致；檔案先保存於 repo 外，故中斷可能留下未引用的孤兒 artifact，可依 manifest 定期清理，不能把它解釋成已核准來源。下一項 P1-02 需查核 entity/security identity 與可交易性；G1／決策級研究仍 BLOCKED。
