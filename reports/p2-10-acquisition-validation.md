# P2-10 第二增量：官方原文取得與真實引用稽核

驗證日期：2026-10-01。軟體 0.1.21，plan 1.11，contract proposal.10，audit bundle `.9`。P2-10 **IN_PROGRESS**；這次完成取得與原文引用核對，尚未完成真實財務／治理事件的審閱入庫。

## 合併基準

[PR #20](https://github.com/yoyoCadence/Tokenized_Capital_Markets/pull/20) 的 exact head `ec2446a181bb5ffe3a6d90bce41e636ce911161e` 經 GitHub G0 run `36836203562` SUCCESS、非 Draft、無 conflict／review 後合併；main merge commit `7e3ff9be1dde6f8c4613aa3c3a12bf9c0bcd7106`。本增量從此 main 建立。

## 已實作

`source-acquire` 透過可替換的 `OFFICIAL_HTTP_V1` 取得單一明確指定的官方 HTTPS UTF-8 原文。exact host／kind／tier、no redirect、declared User-Agent、每 project 間隔、socket timeout／transfer deadline、32 MiB、MIME／charset／encoding／length 檢查，失敗只保存 public failure code，不存 error body。來源 capture 不核准日期／權利／財務語義；`source-review` 和 `refresh-review` 仍獨立。

staging schema 1.1 明示 HTTP request／completion clocks 與 response metadata，兼容 1.0 manual-only ledger；成功才有實際 retrieval、digest 和 size。相同 ID／metadata 重試不打網路，成功須重新驗原版 digest；新取得／修訂用新 ID。共用 publication lock／journal，可恢復中斷而不重複 ledger。原文不進 git 或 compute bundle。

`scripts.verify_original_citations` 以 strict manifest 核對外部原文完整 hash 和 byte ranges，無網路或發布。輸出明示 `UNREVIEWED_RESEARCH_LEADS` 與 `financial_publication=false`。這不是 accounting／onchain 語義判定。

## 真實操作結果

三筆 `sources/staging.yaml` capture 均 HTTP 200、hash／size 驗證成功，retrieval 是實際 2026-10-01 UTC。**source review 0；canonical source、observation、event、refresh proposal/review 均 0**。權利保守標 RESTRICTED；人工仍須確認。

| 原文 | bytes | SHA-256 | 待審狀態 |
| --- | ---: | --- | --- |
| SEC Securitize Corp. 8-K/A | 34,773 | `038c353f7482582380a971fcec281f98b26c3e822b4cbe430478b6ac369d2ef1` | 保存 parent signature date／Exhibit 99.1 link；不把簽名日當 acceptance instant |
| SEC Securitize, Inc. Q2/H1 Exhibit 99.1 | 1,161,272 | `271119e0e767211e69179cba9e8a30e24f4b15877918ea1402eb42b02cae3e31` | 營運公司、表格欄位、期間、貨幣與 publication 關係待審 |
| Uniswap proposal #93 | 144,088 | `21efa35abcf40f9057a72a983a8b4ac32a78f721158d99530842ae743d8cd0c6` | server HTML 含 proposal 與 portal-reported execution；不执行 scripts，source_date 保持 null |

九處 exact byte citations 已成功離線核對，manifest：`research/refresh/p2-10-original-citations.yaml`。可用原版外部 artifact store 重跑：

```bash
python -m scripts.verify_original_citations --plan research/refresh/p2-10-original-citations.yaml --store-dir /private/artifacts
```

財報 revenue token `14,435,845` 在原版出現三次；manifest 指向 statements of operations 的第一處，但語義／欄位映射尚待人審。原表頭為 Three Months Ended June 30，年份和 `$` 在不同 cells；找不到 `April 1, 2026`、`USD`、`US dollars`、`dollars`、`August 13, 2026` 字面 token。現有 refresh adapter 的要求與真實 filing 不相容，不能捏造 quote、單位、起日或 timezone。營運公司 Securitize, Inc. 不能直接當 `SECZ` issuer role；parent 8-K/A 的 publication relationship 需要多原文引用。

治理 HTML 有 createdTime／executedTime 的 UTC token 和顯示的 Executed Actions；這是網站報告，不是已驗證的 receipt／完整期間 burn 或 USD economics。現有治理 adapter 只允許 PLANNED／ANNOUNCED／APPROVED，不能把網站 execution label 強轉為這些狀態。

## 工程驗證

- 13 個新增 integration tests：精確存證、1.0→1.1 migration、no network retry、capture/review 邊界、HTTP 301／403／429／503、timeout／connection／truncated transfer、MIME／charset／encoding／UTF-8／empty／provider block／length、declared/streamed size／deadline、URL／User-Agent／strict receipt、版本間隔、artifact tamper、crash recovery、CLI nonzero、唯讀 citation audit 和假引用。
- CPython 3.12.14／PyYAML 6.0.3：`python -m scripts.g0_gate` **223 tests OK，64.082 秒**；DEMO／RESEARCH 各 **94 metrics、0 issues**；G0 工程 **PASS**、決策級研究發布 **BLOCKED**。來源／擷取三組 integration tests 另有 29 tests OK。
- 真實原版 citation audit：3 documents、9 spans，全部 verified；source_approved 全 false，financial_publication false。staging 為 3 captures／0 reviews，canonical source/observation/event/refresh 仍為 0。
- `git diff --check` 乾淨；本次相關四份 YAML 以 strict loader 通過。沒有修改金融公式、既有 canonical observation 或原 snapshot。
- 原 v1 demo snapshot SHA-256 維持 `cdd6e94a1297f7fcccab2f8c2d8658493537db7bf9ea6136c10e82a41f0d300e` 與 `6c74c60034ca958c132ad5a3aa1ab0ee8e9feef4d4ae9e458705b19bcd14d808`。

## 下一項

仍是 P2-10：為真實 SEC 表格建立可審閱 column／duration／unit 與 parent-exhibit 多文件關係，並以 operating-company identity 隔離上市 issuer／殼公司／pro forma；治理欄位和 receipt 要以新的有來源證據映射處理。來源與擷取人工審閱完成後才允許 canonical admission。自動 discovery／polling、PDF/OCR、完整研究驗收尚未完成；P1-05～07、P2-04／08、G1 和決策級發布維持 BLOCKED。

Git 保存 metadata／digests，不保存原文 bytes；跨機器稽核需備份外部原版 artifact store。重新下載可能取得新版，須 append capture，不能宣稱自動重現舊 hash。這次測試通過不代表研究可用性或投資成效。
