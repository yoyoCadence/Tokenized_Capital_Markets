# Task backlog / 專案路線圖

更新：2026-09-25。詳細順序與驗收以 [IMPLEMENTATION_BACKLOG.yaml](docs/planning/IMPLEMENTATION_BACKLOG.yaml) 為準。規劃不是已完成實作。

## CURRENT — MVP 基礎與本次規劃已完成

- [x] Canonical dictionary、formulas/source registries、graph、events、四種 classification。
- [x] UNI／SECZ／XLM demo economic models、reverse underwriting、sensitivity、thesis rules。
- [x] Validation、lineage、regression、synthetic data pack、snapshots／comparison、local dashboard。
- [x] README、methodology、changelog、AGENTS 永久規則。
- [x] 重新檢查基線：26 tests 通過；DEMO／RESEARCH validation 通過；真實 observation = 0。
- [x] [詳細發展計畫](docs/planning/MASTER_PLAN_2026-09-25.md)、[現況稽核](docs/planning/CURRENT_STATE_AUDIT.md)、[資料模型規格](docs/planning/DATA_AND_MODEL_SPEC.md)、[投資驗證方案](docs/planning/EDGE_VALIDATION_AND_RISK.md)。
- [x] 工作依賴、驗收、來源線索與 [第一個工作包](docs/planning/FIRST_IMPLEMENTATION_PACKAGE.md)。

完成的是 MVP 基礎與規劃。已重現的隔離／時點／頻率／YAML 問題尚未修復，真實研究發布與投資優勢尚未驗證。

## NEXT — 先做到可信、再做到日常可用

1. [ ] **WP-01 / P0-02 → P0-01：strict YAML、唯一性與版本鏈、RESEARCH fixture 隔離。**
2. [ ] P0-03～P0-06：資料 v2 契約、knowledge-time selector、realized/forward/reverse scope、資產／規則各自的 cadence。
3. [ ] P0-07～P0-10：可重播 snapshot、read-only API、發布復原、品質傳播與 G0 驗收。
4. [ ] P1：primary-source research pack、entity/security master、價量／股本／EV、UNI／SECZ／XLM 資料對帳與第一份真實快照。
5. [ ] Source freshness monitoring、stale-data detection、conflict queue；缺值保持 unknown。
6. [ ] P2：三資產模型 v2、better bottom-up TAM engine、完整 reverse／joint sensitivity、決策研究包。
7. [ ] Automated research refresh workflow，先有 staging 與審閱。
8. [ ] Event-driven recalculation 的里程碑／經濟傳導與可恢復發布。
9. [ ] Quarterly earnings ingestion 與 protocol governance monitoring。
10. [ ] Additional asset models 的候選與資料可得性評估；先不擴大專用模型，正式擴張依 P5-01 的證據門檻。

原先「先直接導入真實研究包」調整為「先修 P0 邊界再發布」；理由與重現證據見現況稽核。來源查找可先進行，不能跳過發布門檻。

## LATER — 全部保持 PLANNED，這次不實作

- [ ] P3：預先登錄、forecast journal、historical point-in-time／holdout、成本模型與 paper ledger。
- [ ] P3：expected-return model、permanent-loss model；機制／機率不可識別時可拒算。
- [ ] P3：benchmark、淨績效與歸因、校準、研究成本與樣本限制；操作通過不等於 alpha。
- [ ] P4：使用者 IPS、portfolio integration、人工有限 pilot、私有持倉對帳與停止程序。必須另有具體資本授權。
- [ ] P5：unattended API automation、scheduler、automatic PR creation、notifications；另行立項。
- [ ] P5：additional asset models、可選研究產品商業化、provider 擴張；先驗證增量價值與資料使用權。

不自動建立 scheduler、通知、不自動下單或擴大資本；後續按使用者具體任務逐包實作。
