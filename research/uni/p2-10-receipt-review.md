# P2-10 第八增量：成功 receipt 與一筆實際 UNI vesting 轉帳

這是待審研究材料。PR #26 已以 head `ec16b137f27d5b31f3fd01cf97e018dbd3ddd7c1` 合併，main merge commit `032e073121803f35f5a4a6efc6aa07d97a6966bd`，G0 run `36971227592` SUCCESS。新證據追加於舊核對之後；[舊 plan](p2-10-execution-plan.yaml) 與 [舊 packet](p2-10-execution-packet.yaml) 保持原樣，舊 null receipt 不是 pending／failed 判定。

[新 plan](p2-10-receipt-plan.yaml) 與 [新 packet](p2-10-receipt-packet.yaml) 由唯讀 [receipt checker](../../scripts/verify_uni_receipts.py) 產生。它先重播原版治理 checker，再核對兩家 RPC 的成功 receipt、全部標準 receipt 欄位、完整 raw log inventory、交易／區塊、indexer 和固定 ABI。JSON、HTML 與 Solidity 都只當 inert bytes，不執行來源指令或編譯下載的合約。

```bash
python -m scripts.verify_uni_receipts --plan research/uni/p2-10-receipt-plan.yaml --store-dir /private/artifacts
```

| 已核對項目 | 結果 | 範圍 |
| --- | --- | --- |
| 治理交易 `0x091f…2c1e` | Blast API／MEV Blocker `status=0x1`；15 raw logs 與舊 RPC 一致 | 八個 timelock 呼叫仍經原版 checker 核對 |
| vesting 交易 `0x3143…48b2` | 兩家成功 receipts；PublicNode mined tx／block 與 indexer 一致 | block 24,169,836；2026-01-05 17:04:23 UTC |
| UNI `Approval`，log 166 | Timelock → vesting 的剩餘 allowance，35M UNI | 不是分配金額；不推定期间没有其他 approvals |
| UNI `Transfer`，log 167 | Timelock → `0xaba63748c4b4def4a3319c3a29fe4829029d926f`，raw `5000000000000000000000000` | 18 decimals 的 DERIVED 展示為 5M UNI |
| `Withdrawn(address,uint256,uint48)`，log 168 | recipient／raw amount 與 Transfer 相同；quartersPaid=1 | 两个 canonical ABI words，不读 indexer 的 decoded amount |
| 官方合約／interface | commit `0c071d199dc32556365c78e03ec3f4d09b9fbf37` 的檔案與 indexer source text 相同 | 僅 byte match 與 ABI context，不是歷史部署 bytecode 證明 |
| DUNI 第一筆 grant 敘述 | exact original byte span 支持 5M 與 Jan 5；與鏈上時間／數量相符 | 收款地址屬 Uniswap Labs 的法律身分仍是 publisher assertion |

vesting 地址為 `0xca046a83edb78f74ae338bb5a291bf6fdac9e1d2`；UNI 為 identity master 的 Ethereum 合約。交易 caller `0x2cf8e5b175aa29c1fdf0e9fe572735c78eacce43` 與收款人不同，不能把發起地址當受款人。官方 source 的 withdraw 允許任何人呼叫，由 owner transferFrom 到 recipient；recipient 與 quarterly amount 可以修改，歷史設定仍未獨立核對。source 與 indexer constructor context 的一致，不代表完整期間內沒有變更。

## 仍須明確判定的事項

- 九份新原文／captures 的日期、分類、Tier、locator、權利與來源核准仍待審。原文共 21 份、captures 25 筆，real reviews 與 canonical sources／observations／events 均為零。所有原文限制再散布，完整 bytes 留在 checkout 外；plan 與 packet 保存 digest／定位。官方報告、GitHub code 和 multi-block receipt bundle 的 source_date 保持 null；Jan5 JSON 的日期僅 block context。
- Blast／MEV 的原文是操作者記錄的 request／response envelope，含 endpoint、方法／參數／IDs、真實 request／completion 時間、HTTP status／media 與 response SHA。staging 的 retrieved_at 是之後实际手動存證時間，不回填網路時間。這些不是 `OFFICIAL_HTTP_V1` adapter 簽發的 HTTP receipts；兩個 endpoint 一致也不是共識或獨立後端的證明。
- 完整標準 receipt payload 一致，但沒有 receipt-trie inclusion proof，也沒有追溯 finalized ancestry。不得稱歷史 finality 已獨立證實。原 portal 比 matched block time 晚 96,972 秒的衝突仍存在；receipt 不會消除它。
- 這是 treasury-funded growth transfer 的待審解釋。官方 DUNI 報告是特殊目的、未審計、non-GAAP 報表；不等於 protocol-layer income 或 holder 法定收益。40M allowance、5M 實際轉帳、100M treasury 轉 dead 不能互換。
- 只查核一筆 Jan5 交易，`complete_period=false`、季度總量 null。PublicNode 歷史 range query 回覆需要 token 的 provider error，不能當成空清單或零轉帳。Apr／Jul／Oct vesting transactions 只作後續 discovery，本版未核對或加總。
- totalSupply 變動、全季 protocol-fee burn、USD basis、holder cash flow 仍 null。尚不能發布 UNI 淨 burn、估值或可交易結論。SEC 的兩個 pending proposals 和原四筆收入／五項量測決議不變。

工程合併不代替具名 source／semantic acceptance。P2-10 維持 IN_PROGRESS，P1-05 complete-period evidence 與 G1 仍 BLOCKED。下一步是補 2026Q1 全期間 coverage 與實際審閱，再評估 canonical admission；沒有新增核准或 publication API。
