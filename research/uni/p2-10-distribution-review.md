# UNI 分配全集：範圍提議與查詢待辦

2026-10-03，**PROPOSED / ASSUMPTION**。這份文件定義下一輪取證的查詢範圍，**不是已完成的全集、季度數值或審閱決議**。PR #28 的 5M UNI 僅是指定 vesting 查詢的待審子集。所有原版 packets、31 captures、SEC proposals 與 canonical ledgers 不變。

## 提議的計量邊界

`FIRST_EXIT_OF_REVIEWED_TREASURY_CONTROL`：將 growth distribution 的候選口徑設定為從**經人審確認的 treasury 控制帳戶集合**首次退出的 UNI。目前只有 timelock seed，控制全集及其 Q1 歷史有效性均未知，因此不能產生該口徑的季度總數。這是分析者的 proposed accounting policy，不是既有 `uni_realized_distribution_value` 定義已被批准修改。

先取 Ethereum 原生 UNI 的 Transfer census；只有 Treasury / Withdrawn filter 不足以發現漏列帳戶或其他分配方式。全部 Transfer 也不能直接當分配：交易所交易、自轉、內部調撥和 onward transfers 不是新增 growth cost。全球 UNI / 所有持有人 / circulating supply 是另外的問題，本增量不宣稱覆蓋。

| Lane | 本版狀態 | 關閉缺口需要什麼 |
| --- | --- | --- |
| GROWTH_VESTING | selected packet only | 重播原文、來源／語義人審、歷史配置；已有 5M 子集不是全集 |
| TREASURY_DIRECT | 未查詢 | UNI token emitter 的完整 treasury 出入帳，以及控制帳戶全集 |
| DELEGATED_PROGRAMS | 帳戶／program inventory 未知 | Foundation、grant、incentive 中介帳戶的控制與來源資金 lineage；不能假定已列出所有 programs |
| CROSS_CHAIN | chain／representation inventory 未知 | 歷史部署、bridge message/lock/mint 對應、跨鏈經濟去重；不能用今日 deployment list 當 Q1 狀態 |
| LEGACY_UNLOCKS | separate supply，未知 | 歷史受益人／unlock 與 actual transfers；不自動扣進 growth 分配成本 |
| MINT_SUPPLY | separate supply，未知 | 原生 mint events、期初／期末 totalSupply state 及殘差；不能把設計上允許的通膨當已鑄幣 |

[官方 UNI 原始介紹](https://blog.uniswap.org/uni) 提及 community treasury、多種 program 用途、其他持有人分配與通膨設計；它是分類線索，不證明 2026Q1 實際提款或供給。[今日 protocol deployment 文件](https://developers.uniswap.org/docs/protocols/protocol-fee/deployments) 有 UNI／vesting 與多鏈部署；它不證明歷史 account control 或該季度 bridge 流量。兩個網頁此次只作 link-checked research leads，未新增 source capture、日期或批准。

## 可執行的查詢規劃

```bash
python -m scripts.plan_uni_distribution --summary
python -m scripts.plan_uni_distribution
# 有外部原版時才可另行重播舊 Q1 audit；仍不發送新 RPC requests：
python -m scripts.plan_uni_distribution --summary --store-dir /absolute/path/to/originals
```

[plan](p2-10-distribution-plan.yaml) 釘住舊 Q1 plan／packet 與 receipt packet bytes；[helper](../../scripts/plan_uni_distribution.py) 驗證 shared preflight、source manifest／取得時點、helper pins、同一 Withdrawal / Transfer context。默认只核對 Git metadata：`prior_originals_replayed=false`。缺外部原版的 optional replay 回非零，不能退回 metadata-only 而宣稱成功。即使原文重播一致也只驗證**舊子集**，不關閉新的 distribution universe。

兩 provider × 五 filter families ×（chainId + 全區間 + 65 相鄰分段）= **670 個未執行 requests**；UTC Q1 inclusive blocks 24,136,053–24,781,026。Filters 是 token-wide Transfer、seed outflow、seed inflow、zero-from mint diagnostic、dead-to diagnostic，均查 **UNI token emitter**，不是以 UNIVesting 當 ERC20 Transfer emitter。10,000-block segment／1,024-request 上限是分析者起始政策，不是 provider SLA 或可成功查詢的保證。若範圍／response-size 受限，須追加有明確 coverage 的新版本，不把失敗當零，也不截取部分 plan 冒稱完成。

本版生成 requests，**沒有 acquisition、response importer、transfer 聚合或全域去重實作**。完整取得後仍需 full/split/providers 一致性、response-cap／錯誤／截斷檢查、每筆 receipt、歷史 control/ABI、finality 與語義分類，才能考慮新的 measurement/admission contract。

## 去重規則提議，不是金融核准

- Raw logs 以 `(chain_id, token_contract, block_hash, transaction_hash, log_index)` 識別，不能只靠 tx hash。Full/split/providers 是同一筆 evidence 的多次觀測，不是多筆支出。
- Jan5 receipt 的 Approval index 166、Transfer index 167、Withdrawn index 168 是不同 raw logs；Transfer 與 Withdrawn 描述**同一資金移動**，只列一筆待審 movement。Approval 剩餘 allowance 不是另一筆分配。
- 一筆 UNI 先 treasury→program→beneficiary 或 bridge lock→representation mint，不得在 first-exit 口徑重算每一條 leg。控制邊界未核准時保留 unknown，不假定中介帳戶已在圈外。
- Returns／退款單列 inbound；不偷偷從 gross 分配扣除。Legacy unlock、mint、fee-to-dead、treasury-to-dead 與 ordinary transfer 各自分類。Dead transfer 也不直接等於 totalSupply reduction。
- 5M 待審子集不宣稱 global minimum：未核准其 economic classification，不能把它當已確認的 global lower bound。

**季度 growth UNI、供給變動、realized distribution USD、holder cashflow 全為 null**；來源批准、financial admission／publication 與 decision_ready 均未發生。原本 +96,972 秒 portal 衝突仍保留。P2-10 IN_PROGRESS，P1-05／G1 BLOCKED。

下一包：實際存證 seed 出入帳與 token-wide census，追加 immutable request/response envelopes，對 full/split/two-provider inventories 對帳，再擴充 control/program/bridge inventory。金融 scope/source acceptance 須由具名審閱者另外決定，merge 授權不代替它。
