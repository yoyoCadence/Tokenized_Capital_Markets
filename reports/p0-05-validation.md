# P0-05 驗收：UNI 經濟 scope 分流

**2026-09-26｜軟體 0.1.3｜P0-05 DONE｜P0-06 規則 cadence 與 P0-07 快照重播未完成**

## 原則及分流

| 輸出 | 公式口徑 | 輸入約束 |
| --- | --- | --- |
| `uni_realized_net_burn_yield` | (實際燒毀 USD − 實際分配 USD − 其他實際稀釋 USD)／查詢時市值 | 三筆同一已完成季度 OBSERVED/REALIZED；同日供給與 24h 內即期價。沒有實際燒毀紀錄時 Unknown，不能用 protocol fees 代替。 |
| `uni_annualized_net_burn_yield_run_rate` | 以上季度淨值 × 4／即期市值 | 80–100 天完成季度的簡單年化；分類 RUN_RATE，不是實際年報或未來預測。 |
| `uni_modeled_net_yield` | (同一未來年度 TAM×滲透×周轉×鏈上×AMM×UNI 份額×假設費率／10000 − 假設分配)／即期市值 | SCENARIO/MODELED_HORIZON TAM 和假設；即使期間在知識 cutoff 後，發布／採納時間仍必須不晚於 cutoff。 |
| `uni_required_market_share` | (即期市值×假設目標收益率 + 未來年度假設分配)／(同年度 TAM×滲透×周轉×鏈上×AMM×假設費率／10000) | REVERSE_REQUIREMENT，獨立 standalone hurdle；>100% warning，零分母拒算。不等同 v1 的 42.2% fixture。 |

所有輸出為 `DERIVED`，有 formula ID/version/signature、role dependencies、transitive record/source IDs、fixture flag 與明示的 economic/knowledge/valuation context；缺項 null 不補零。`spec/v2/metric-concepts.yaml`、`input-roles.yaml`、`formula-registry.yaml` 和 `formula-lock.yaml` 與 v1 registry/lock 分開。相同 `uni_effective_protocol_fee` 概念用 OBSERVED/REALIZED 季度 role 與 ASSUMPTION／SCENARIO/MODELED_HORIZON 年度 role；舊 v1 assumption 未升格。

## 實作及驗收

- `engine/temporal/economics.py` 消費 P0-04 selector；`scope-report` 和唯讀 `/api/economics` 須明示完成季度、年度 horizon、knowledge cutoff、valuation time 和政策。UI 有分開的 v2 panel，v1 混合口徑顯示 LEGACY_MIXED；XLM network fee 的 v1 混用也明示，不假裝已遷移。
- v1 UNI `uni_low_net_burn` 和 `uni_fee_share_stress` 的當期 thesis 不再接受 v1 混合 TAM／反推值：兩者報 `V1_SCOPE_UNFIT` 且 UNI 純 demo 沒有被稱為 HEALTHY；供給規則等無關現有規則仍執行。P0-06 才重新建立含期間/freshness 的 v2 規則。
- 獨立合成測試手算：季 burn 100 − 分配 20 − 稀釋 10 = 70；即期 100 UNI × $10 = $1000；realized yield = 7%，run rate = $280／28%；未來 TAM 1,000,000、滲透 50%、周轉 2、鏈上 50%、AMM 50%、份額 20%、100 bp → $500 revenue，扣假設分配 $1 → $499／49.9%；reverse share = (1000×10%+1)／2500 = 4.04%。所有數字僅暫存 fixture，**不是市場資料**。
- TAM ×10 不改 realized/run-rate；缺 burn 只會 Unknown；過期報價、跨季度／年度資料無法冒充當期；負值／份額越界／零分母／未生效 scenario／公式簽章被改動皆拒絕或 Unknown。CLI 與 HTTP 的隔離資料包查詢不寫檔。舊 v1 standalone share **42.2%** 及 SECZ/XLM regression 未變。

重現：

```bash
python -m unittest discover -s tests -p 'test_*.py'  # 90 tests OK
python -m engine.cli validate --demo              # 94 metrics, 0 issues
python -m engine.cli validate                     # 94 metrics, 0 issues
python -m engine.cli scope-report --realized-quarter-end 2026-06-30 \
  --horizon-end 2027-12-31 --knowledge-cutoff 2026-09-26T12:00:00Z \
  --valuation-at 2026-09-26T12:00:00Z --policy AS_KNOWN_BY_SYSTEM
```

最後一個指令在真實空 ledger 應全部回 Unknown；未新增 research observation、來源、v1 快照或價格。v1 `calculate` 和 demo 舊數字保留原版本解讀，不可當歷史當時可知資料；**P0-06／07、其他資產 v2 公式、來源驗證與 G0 尚未完成**。
