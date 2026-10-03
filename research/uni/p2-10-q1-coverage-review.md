# P2-10：2026Q1 UNIVesting 查詢範圍待審

此份資料是 `PENDING_REVIEW`。指定合約／topic 的 provider-returned inventory 已對帳，沒有來源核准、金融語義接受或 canonical admission。前版 [receipt 審閱](p2-10-receipt-review.md)、null receipt 原文及 portal +96972 秒時間衝突保留。

## 可重播的範圍

Ethereum mainnet；UTC `[2026-01-01T00:00:00Z, 2026-04-01T00:00:00Z)`，inclusive blocks **24,136,053–24,781,026**，共 **644,974** blocks。相鄰邊界由 MEV Blocker／Tenderly 的 number、hash、parentHash、timestamp 一致性及 UTC bracketing 支持，不是完整 ancestry／finality proof。

| 邊界 | Block | UTC | Hash |
| --- | --- | --- | --- |
| 起始前一塊 | 24,136,052 | 2025-12-31 23:59:59 | `0xa08a367ae7bf2f0d018a5001dcf3084e36aa7ce78957ca3b6a4eedc8e59a2474` |
| 首塊 | 24,136,053 | 2026-01-01 00:00:11 | `0x53e1c0caa885383824d39dc57c0692ea20e971ade409553c4a8031e90f44c516` |
| 末塊 | 24,781,026 | 2026-03-31 23:59:59 | `0xa66185ac20df0d3bb59ad13ef3b0bd3a4eca5b5058504794a554cb74abf529bd` |
| 末塊後一塊 | 24,781,027 | 2026-04-01 00:00:11 | `0x84b52aea82b4cace3d5224a5f1e771092d360246898940144d05f30653a3c67d` |

`eth_getLogs` 固定 address `0xca046a83edb78f74ae338bb5a291bf6fdac9e1d2`、topic0 `0xe3a7b52bde0e5e2ab4cd91182c9b2a0c7e49183cc039f6d5c3ba738c84e0427b` (`Withdrawn(address,uint256,uint48)`)；未查所有 UNI 合約或其他 event 類型。

| 查詢 | Inclusive blocks | MEV selected document / response ID | Tenderly response ID | 成功回傳筆數 |
| --- | --- | --- | --- | --- |
| 全區間 | 24,136,053–24,781,026 | range_mev_initial / 2 | 2 | 1 |
| 第一段 | 24,136,053–24,351,043 | range_mev_followup / 3 | 3 | 1 |
| 第二段 | 24,351,044–24,566,034 | range_mev_initial / 4 | 4 | 0 |
| 第三段 | 24,566,035–24,781,026 | range_mev_initial / 5 | 5 | 0 |

兩家全區間、分段聯集及同 provider 成功重查結果一致。MEV initial 第一段 -32603，followup 第二／三段 -32603；各次原始錯誤保持 `null` count，manifest 逐段明確選取成功回應，未將錯誤視為零。Blast 四個範圍均 -32600／端點報告上限 10 blocks，僅診斷；没有掃描 64,498 次或購入服務。兩個端點不代表已證明 backend 獨立，也沒有 cryptographic absence／provider omission proof。

## 範圍內事件與尚缺語義

唯一回傳事件與前版兩家 positive receipts 綁定相同 block／tx／index／recipient／raw amount／quartersPaid：Jan5 tx `0x3143564279cec3aab40ec01146c0ca4a9b8339f1516646ac58496f6d198148b2`，logIndex 168，raw `5000000000000000000000000`，18 decimals。`uni_selected_vesting_sum@1.0 = sum(receipt_matched raw_base_units)/10**18` 產生 DERIVED **5,000,000 UNI**。公式只存在本唯讀 audit，沒有改 canonical formula registry。Approval 35M remaining allowance 與 2025 的 100M dead transfer 不加進此總和。

需要具名審閱／新原文：

- 接受來源 metadata／API 時間的限制，以及 selected vesting universe 與全 UNI growth distribution 的差別。
- 確認歷史 deployed bytecode、recipient／amount 設定及 recipient 法律身份；官方 source 文字一致不等於歷史配置已驗證。
- 處理 provider 遺漏／截斷風險、finality ancestry／receipt-trie proof；新增其他 withdrawals 須追加完整 receipts 與新版 audit。
- 財務意義保持 treasury growth transfer pending review。全 UNI Q1 distribution total、realized fee burn USD、totalSupply change、holder cashflow USD 全為 null。

[plan](p2-10-q1-coverage-plan.yaml) 釘住六份 originals、前版 receipt plan digest 與成功回應選取；[packet](p2-10-q1-coverage-packet.yaml) 釘住新／前版 checker SHA256。所有 RPC request/completion clocks 與實際手動 archive clocks 分開，source_date=null；不得回填成歷史 publication／first-seen。原 `p1-05-period.yaml` 未更動。共 27 originals／31 captures，reviews 0，canonical source／observation／event 0；SEC 四筆量／兩個 proposals／五項量測決議不變。

## 離線重播

取得私人原文備份，解壓在 checkout 外，再執行：

```bash
python -m scripts.verify_uni_q1_coverage \
  --plan research/uni/p2-10-q1-coverage-plan.yaml \
  --store-dir /absolute/path/to/originals
```

此 helper 先重播 receipt／execution audit，再驗證完整 staging preflight；缺原文、改 digest、錯 response/filter、gap/overlap、provider disagreement 或不匹配 receipt 都拒絕。原文權利 RESTRICTED，Git 只存 metadata 與 audit packets。engine／contract proposal.13／bundle .12 不變。P2-10 IN_PROGRESS，P1-05／G1 BLOCKED。
