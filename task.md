# Task backlog / 專案路線圖

更新：2026-09-29。詳細順序與驗收以 [IMPLEMENTATION_BACKLOG.yaml](docs/planning/IMPLEMENTATION_BACKLOG.yaml) 為準。未完成規劃不代表現有功能。

## CURRENT — MVP 基礎、WP-01 與 P0-03～10 已完成

- [x] Canonical dictionary、formulas/source registries、graph、events、四種 classification。
- [x] UNI／SECZ／XLM demo economic models、reverse underwriting、sensitivity、thesis rules。
- [x] Validation、lineage、regression、synthetic data pack、snapshots／comparison、local dashboard。
- [x] README、methodology、changelog、AGENTS 永久規則。
- [x] 2026-09-25 原始基線：26 tests 通過；DEMO／RESEARCH validation 通過；真實 observation = 0。
- [x] [詳細發展計畫](docs/planning/MASTER_PLAN_2026-09-25.md)、[現況稽核](docs/planning/CURRENT_STATE_AUDIT.md)、[資料模型規格](docs/planning/DATA_AND_MODEL_SPEC.md)、[投資驗證方案](docs/planning/EDGE_VALIDATION_AND_RISK.md)。
- [x] 工作依賴、驗收、來源線索與 [第一個工作包](docs/planning/FIRST_IMPLEMENTATION_PACKAGE.md)。
- [x] **WP-01 / P0-02 → P0-01**：strict YAML、唯一性與版本鏈、formula DAG、各入口的 RESEARCH fixture 隔離；保留全部相同數值的支持證據。軟體 0.1.1；67 tests 通過，兩種 validation 各 94 metrics／0 issues，原快照未變。[驗收證據](reports/wp-01-validation.md)；implementation commit `e8b4d55520ea71f1d626a9286fa64a30cd745f3d`。
- [x] **P0-03：v2 時間／scope／record 設計契約。** [契約提案](docs/planning/CONTRACT_V2_PROPOSAL.yaml)、[相容矩陣](docs/planning/V1_V2_COMPATIBILITY.md)、[遷移 ADR](docs/planning/ADR-0001-V2-TIME-SCOPE-MIGRATION.md)；runtime 尚未切換 v2，[驗收證據](reports/p0-03-contract-validation.md)。
- [x] **P0-04：v2 雙時間 selector。** 唯讀 CLI 與程序入口，分別重播「當時系統已知」和「當時公開可知」；晚發布重述、來源衝突、日期精度、DST、報價資料齡與原快照保留有回歸。[驗收證據](reports/p0-04-validation.md)。
- [x] **P0-05：v2 UNI 四種經濟 scope。** role/時間選值接入獨立金融公式、鎖版、lineage 與唯讀 Dashboard；封鎖 v1 TAM/混合收益進入當期 UNI 規則，42.2% demo regression 保留。[驗收證據](reports/p0-05-validation.md)。
- [x] **P0-06：分資產／規則的 v2 季度時點與資料期限。** 九條規則逐一保留、UNI realized burn 可用足夠證據評估，其餘缺證據明示 Unknown；獨立 CLI／API／UI 查詢，舊 v1 thesis 保留 legacy 標籤。[驗收證據](reports/p0-06-validation.md)。
- [x] **P0-07：自包含 v2 compute bundle 與完整性重播。** 封存程式、runtime、spec、source metadata／ledger、選用證據與結果；逐位元組雜湊及乾淨環境重播，CURRENT／HISTORICAL 分軌，舊 v1 快照不升格。[驗收與遷移報告](reports/p0-07-validation.md)。
- [x] **P0-08：純讀 API 與可恢復發布。** GET 不新增快照，明確事件發布共用跨行程鎖及 redo journal，逐步故障可恢復且重試不重複。[驗收報告](reports/p0-08-validation.md)。
- [x] **P0-09：品質傳播與衝突選取理由。** v2 多維品質、完整上游 assumption/scenario 葉節點及有時點門檻的人審 resolution ledger；v1 confidence 也修復跨層遺漏。[驗收報告](reports/p0-09-validation.md)。
- [x] **P0-10：G0 整合驗收。** 固定測試環境、CI、獨立 golden 算術與跨邊界負例；127 tests 通過。工程 gate PASS，決策級研究發布 BLOCKED。[驗收報告](reports/p0-10-validation.md)。

已修復 WP-01 fixture 隔離、v2 時間、UNI scope、規則排程、離線計算重播與事件發布復原；其他資產的 v2 財務輸入仍待後續工作；真實 observation 仍為 0，投資優勢尚未驗證。

## NEXT — 先做到可信、再做到日常可用

1. [ ] P1-01：Source staging 與原始證據存證。
2. [ ] P1：primary-source research pack、entity/security master、價量／股本／EV、UNI／SECZ／XLM 資料對帳與第一份真實快照。
4. [ ] Source freshness monitoring、stale-data detection、conflict queue；缺值保持 unknown。
5. [ ] P2：三資產模型 v2、better bottom-up TAM engine、完整 reverse／joint sensitivity、決策研究包。
6. [ ] Automated research refresh workflow，先有 staging 與審閱。
7. [ ] Event-driven recalculation 的里程碑／經濟傳導與可恢復發布。
8. [ ] Quarterly earnings ingestion 與 protocol governance monitoring。
9. [ ] Additional asset models 的候選與資料可得性評估；先不擴大專用模型，正式擴張依 P5-01 的證據門檻。

原先「先直接導入真實研究包」調整為「先修 P0 邊界再發布」；理由與重現證據見現況稽核。來源查找可先進行，不能跳過發布門檻。

## LATER — 全部保持 PLANNED，這次不實作

- [ ] P3：預先登錄、forecast journal、historical point-in-time／holdout、成本模型與 paper ledger。
- [ ] P3：expected-return model、permanent-loss model；機制／機率不可識別時可拒算。
- [ ] P3：benchmark、淨績效與歸因、校準、研究成本與樣本限制；操作通過不等於 alpha。
- [ ] P4：使用者 IPS、portfolio integration、人工有限 pilot、私有持倉對帳與停止程序。必須另有具體資本授權。
- [ ] P5：unattended API automation、scheduler、automatic PR creation、notifications；另行立項。
- [ ] P5：additional asset models、可選研究產品商業化、provider 擴張；先驗證增量價值與資料使用權。

不自動建立 scheduler、通知、不自動下單或擴大資本；後續按使用者具體任務逐包實作。
