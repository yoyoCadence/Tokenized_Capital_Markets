# Tokenized Capital Markets Living Underwriting Engine

Local, reproducible investment research software. This MVP is an **engine plus a traceable presentation layer**, with a deliberately synthetic demo pack. It contains **no verified live prices or company financials**. SEC filings identify Securitize Corp. common stock as NYSE listed under `SECZ` since 2026-07-02; this does not verify a particular investor's ability to trade it.

## 後續發展規劃 / Development plan

已完成 [2026-09-25 詳細規劃與現況稽核](docs/planning/README.md)：可信資料與歷史重播、三資產經濟模型、真實研究流程、投資優勢驗證、成本後模擬與有限人工實證。尚未完成的功能維持 **PROPOSED / PLANNED**。

2026-09-29 已完成 **WP-01、P0-03～P0-10 與 P1-01～04**。軟體版本 0.1.12，**156 項測試通過**，見 [市場橋接驗收](reports/p1-04-validation.md)。v2 有雙時間選值、UNI scope-aware 公式、逐規則季度證據、身分主檔、唯讀正規化與市場橋接報告，以及可離線重播的 audit bundle。來源原文須在 repo 外留存並經人工審閱才能進 canonical source registry；官方身分連結尚未完成原文存證，也沒有真實財務或市場觀察值。v1 財務數字、thesis 與既有快照仍是 LEGACY 路徑。G0 工程驗收通過，但真實 observation 與正式 conflict resolution 均為 0；決策級研究發布維持 BLOCKED。下一步 **P1-05：UNI primary evidence 最小包**，依賴與驗收見 [backlog](docs/planning/IMPLEMENTATION_BACKLOG.yaml)。

## Requirements / 啟動

Python 3.11+ and PyYAML 6.x. No API key, npm, paid database or AI provider SDK.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p 'test_*.py'
python -m engine.cli validate --demo
python -m engine.cli bootstrap-demo   # safe to repeat; same content is deduplicated
python -m engine.cli serve --demo
```

G0 CI 使用 CPython 3.12.14／PyYAML 6.0.3。重現整合驗收：在此環境執行 `python -m pip install -r requirements-g0.txt`，再執行 `python -m scripts.g0_gate`；命令列出工程測試結果及未解 P0 任務，決策級研究發布狀態另以 `BLOCKED` 顯示。`--require-ready` 在尚未具備 G1 與真實觀察值時回非零退出。

Open `http://127.0.0.1:8765/`. `--demo` is explicit: pink DEMO markers mean every financial observation is synthetic. Run `python -m engine.cli serve` for research mode; current numerical observations and fixture assumptions are absent, so values are correctly **Unknown** until sourced.

Other commands:

```bash
python -m engine.cli validate              # validate real research pack (currently empty)
python -m engine.cli snapshot --demo --as-of 2026-06-30
python -m engine.cli compare --demo
python -m engine.cli apply-event --demo --id event_demo_dtcc_planned
python -m engine.cli recover            # complete a pending explicit event publication, if any
python -m engine.cli identity --asset SECZ
python -m engine.cli identity --namespace NYSE --symbol SECZ --as-of 2026-07-02
python -m engine.cli normalize-report --demo --plan /path/to/plan.yaml
python -m engine.cli market-report --demo --plan /path/to/market-plan.yaml
```

`identity` 是唯讀的公開資料重建，日期只判斷工具 alias 的有效期間，不表示本系統當日已取得證據。SECZ `market_instrument_status=LISTED`，但 `user_trade_eligibility=UNKNOWN`、`investable=null`；tokenized form 的個人資格和起始時間另待驗證。見 [P1-02 報告](reports/p1-02-validation.md)。

SECZ 申報研究包可用 `python -m engine.secz_evidence` 唯讀重算兩類收入、非 GAAP 調節、現金橋接與衝突股數。官方 2026 Q2/H1 營運財報屬合併前 Securitize, Inc.，同期 SECZ 10-Q 為未營運控股殼公司；原文待存證人審，結果仍 `BLOCKED`，六分析分項、FCFF、postclose EV cash 和 fully diluted shares 均未知。見 [P1-06 報告](reports/p1-06-validation.md)。

XLM 研究包可用 `python -m engine.xlm_evidence` 唯讀檢查 native reserve／sponsorship 去重與 DTCC 鏈別里程碑。DTCC 在 Besu／Canton 的 production trades 不能當 Stellar live；全網 XLM 存量、DTCC 可歸因需求及價格效果仍未知。見 [P1-07 報告](reports/p1-07-validation.md)。

`normalize-report` 需要以 strict YAML 提供 `schema_version: '2.0'`、`context`（`economic_cutoff`、`knowledge_cutoff`、`valuation_at`、`knowledge_policy`）和有序 `steps`。例如：

```yaml
schema_version: '2.0'
context:
  economic_cutoff: '2027-01-10'
  knowledge_cutoff: '2027-01-10T23:00:00Z'
  valuation_at: '2027-01-10T12:00:00Z'
  knowledge_policy: AS_KNOWN_BY_SYSTEM
steps:
  - id: revenue_usd
    formula_id: secz_scale_musd
    inputs: {raw: exact_observed_record_id}
```

此 ID 是用法佔位符，repo 的 v2 demo/research ledger 目前都沒有該 OBSERVED 紀錄。輸入必須已有查核來源、相符概念／單位／會計口徑及合格時間；結果保留公式鎖版與逐層 lineage，僅為唯讀稽核輸出，不進 canonical ledger、v2 economics 或 thesis。六個支援公式及完整限制見 [P1-03 驗收](reports/p1-03-validation.md)。

`market-report` 使用同樣的已審來源與雙時間政策，另指定 quote／結構最長資料齡。現價模式需 OBSERVED 報價 ID；假設價格模式以 `SCENARIO` 標示，不能作歷史行情。以下為欄位範例，所有 ID 都是**佔位符**，現有 ledger 不含真實價格或股數：

```yaml
schema_version: '2.0'
asset: SECZ
price_mode: CURRENT_MARKET
context:
  economic_cutoff: '2026-09-30'
  knowledge_cutoff: '2026-10-01T12:00:00Z'
  valuation_at: '2026-09-30T12:00:00Z'
  knowledge_policy: AS_KNOWN_BY_SYSTEM
  max_quote_age_seconds: 86400
  max_structure_age_days: 120
price_record_id: exact_nyse_quote_id
inputs: {basic: exact_basic_share_id, diluted: exact_diluted_share_id}
```

此例可計基本股權價值與示意稀釋價值；沒有債務、優先股權、非控制權益、可扣除現金及非營運資產的來源時，EV 保持 Unknown。UNI／XLM 則要求流通量與總供給，輸出不同語義的流通市值與 FDV。輸入時間、供應商市值差額和完整契約見 [P1-04 驗收](reports/p1-04-validation.md)。

`GET /api/state` 不建立快照；請以 `snapshot` 明確發布。`apply-event` 逐檔更新前先建立 redo journal；若途中故障，讀取 API 回傳 503，`recover` 補齊完整版本（或下一次明確發布自動補齊）。相同事件與觀察值重試不重複新增；衝突的重用事件 ID 被拒絕。見 [故障注入驗收](reports/p0-08-validation.md)。

For a sourced LIVE/COMPLETED event, add its immutable record and source to the registries, then run `python -m engine.cli apply-event --id EVENT_ID --observations new-observations.yaml`. The batch must use fresh IDs, match the event's source IDs and classification, and pass full validation before its observations are appended. The command recalculates, applies thesis rules, writes a snapshot and records the event in `reports/changelog.md`. Planned/announced events cannot ingest live observations. The demo command above has no new observations and only records graph propagation; avoid running it when you want the default two-version comparison unchanged.

## Source staging / P1-01

先在 repo 外準備原始檔與 metadata YAML。必填欄位為 `url`、`publisher`、`title`、`document_kind`、`source_date`（無法查證則設 `null`）、`tier`、`covered_metrics`（明確的 v2 concept IDs）、`locator`、`rights`、`media_type`；可選 `supersedes_id`。`source-stage` 只讀本機提供的檔案，將位元組存到 repo 外指定的絕對路徑，並把 digest／大小／實際取得時間記入 `sources/staging.yaml`。無法取得檔案或日期不明時不會自動成為 canonical source，更不會變成 OBSERVED。

例如，repo 外的 `source-metadata.yaml` 可採以下**純示意**格式，日期與欄位必須以實際原文查核後填寫：

```yaml
url: https://example.invalid/test-only
publisher: Example issuer
title: Example release
document_kind: OFFICIAL_RELEASE
source_date: '2026-09-28'
tier: 2
covered_metrics: [uni_burn_value]
locator: page 1, table A
rights: RESTRICTED
media_type: application/pdf
```

```bash
python -m engine.cli source-stage --id candidate_001 \
  --metadata /private/source-metadata.yaml --file /private/source.pdf \
  --store-dir /private/source-artifacts
python -m engine.cli source-verify --id candidate_001 --store-dir /private/source-artifacts
python -m engine.cli source-review --id candidate_001 --review-id review_001 \
  --decision APPROVED --reviewer 'Research reviewer' \
  --reason 'Original document, date and rights checked' --store-dir /private/source-artifacts
python -m engine.cli source-status
```

審閱可選 `HOLD`、`REJECTED` 或 `APPROVED`；核准需要原文 digest 核對、來源日期與權利狀態，僅原子發布 source metadata。舊來源版本不改寫，新版需新 ID 與 `supersedes_id`。API 不自動擷取外部網址，沒有把任何真實原文或數值加入本 repo。`snapshot-v2` 封存審閱 ledger 和 metadata hash，外部原文須另行保管並以 `source-verify` 查核；詳見 [驗收與限制](reports/p1-01-validation.md)。

## Input validation / WP-01

- 所有計算、CLI、HTTP、事件與 snapshot 入口先驗證輸入。重複 YAML key、aliases／merge、NaN／Infinity、錯誤型別、未知欄位、重複 ID、非法 supersession 與 formula cycle 會被拒絕。日期使用引號包住的 `YYYY-MM-DD`；`fixture` 使用真正的 boolean，不接受字串 `"false"`。
- RESEARCH 不載入 demo ledger。共享設定中明確 `fixture: true` 的 assumptions／scenarios／graph edges 可依政策排除；排除清單由 API 的 `loading_policy` 提供。未引用的 fixture source 可以保留。
- 放錯到 research ledger 的 fixture observation／event 直接報錯，使用 `--demo` 也不能繞過；`fixture: false` 但引用 fixture source 同樣拒絕。來源相同數值的多筆證據全部保留，任何 synthetic dependency 都會傳到衍生結果。
- 輸入驗證失敗：CLI 以 exit code 1 及 stderr JSON issues 回覆；HTTP state／sensitivity 回傳 422 與 `issues`。issue 包含 `level`、`code`、`message`、`path`；例：`RESEARCH_FIXTURE`、`YAML_DUPLICATE_KEY`。失敗不發布 snapshot 或寫入 ledger／changelog。
- 測試與隔離資料包可指定根目錄：`python -m engine.cli --root /path/to/project validate`。`--root` 放在子命令前。

這些檢查驗證已宣告的結構、來源引用與模式邊界；它們不會自動查證來源內容是否真實，也無法辨識刻意冒充真資料的未標記數字。新增真實 OBSERVED 仍須人工核對原始證據。未保存的 sensitivity overrides 不可直接存為 canonical snapshot。

## v2 雙時間證據查詢 / P0-04

`spec/v2/` 存概念與輸入角色，`sources/v2/` 存來源版本，`data/v2/observed/` 分開存 RESEARCH 與 DEMO。新查詢只讀這些檔案，**不呼叫 v1 `calculate(as_of=...)` 或寫 snapshot**。目前研究 ledger 為空，因此下例回傳 `value: null`：

```bash
python -m engine.cli temporal-select \
  --role secz_quarterly_revenue --economic-cutoff 2026-03-31 \
  --knowledge-cutoff 2026-09-26T05:00:00Z --valuation-at 2026-09-26T05:00:00Z \
  --scope REALIZED --policy AS_KNOWN_BY_SYSTEM
```

`AS_KNOWN_BY_SYSTEM` 同時要求當時已公開、已取得及已入庫；`PUBLIC_INFORMATION_RECONSTRUCTION` 可用事後取得但當時已公開且有發布存證的來源，輸出 `reconstructed: true`。兩種模式不得合併成一個歷史樣本。日期精度只能用有時區的隔日零點；未知發布或首次取得時間維持 unknown。同期間不同值回傳 `CONFLICT`；同值的不同來源保留全部 ID。報價使用原時區日期及明確最大資料齡。

CLI 的 `--demo` 讀取 `data/v2/observed/demo.yaml`，目前也是空的；新增回歸案例僅在測試的暫存資料包執行。v1 `snapshot`／`compare` 不提供 point-in-time 保證，不能當事前決策紀錄使用。

## V2 UNI economic scopes / P0-05

`scope-report` 經 v2 雙時間 selector 選擇輸入，再用 `spec/v2/formula-registry.yaml` 的獨立鎖版公式計算；只讀、不覆寫 v1 公式與快照。`REALIZED` 要求同一已完成季度的實際 burn、已分配價值與其他稀釋，以及同日供給量／即期價；費用收入不是自動等於 burn。`RUN_RATE` 只是季度淨值乘四。`MODELED_HORIZON` 依未來同一年度的 TAM 情境與明示假設；`REVERSE_REQUIREMENT` 使用當下市值與同年度費率／分配／目標收益率。輸出保留公式簽章、角色依賴、所有 record/source IDs 和 fixture 標記，缺任一必要值保持 Unknown。這不是 token 總報酬或承諾的持續燒毀率。

```bash
python -m engine.cli scope-report \
  --realized-quarter-end 2026-06-30 --horizon-end 2027-12-31 \
  --knowledge-cutoff 2026-09-26T12:00:00Z --valuation-at 2026-09-26T12:00:00Z \
  --policy AS_KNOWN_BY_SYSTEM
```

目前 RESEARCH 與 v2 DEMO ledger 均空，故全部 v2 結果為 Unknown；156 項測試中的數值只存在隔離的暫存 fixture。Dashboard 的「V2 scopes」可指定時間查詢，點選結果可檢視來源 tier、新鮮度、涵蓋、量測、機制及衝突候選與理由；沒有經原文查核的量測仍標未核實。[Resolution ledger 契約](reports/p0-09-validation.md)要求審核時間不能早於資料入庫，後續候選會使舊決定失效。原 v1 `net_burn_yield`、`xlm_network_fee_value` 等混合口徑在 UI 標為 LEGACY_MIXED；v1 當期 UNI 兩條含 TAM／反推的 thesis rule 已封鎖，狀態 Unknown 而非 Healthy。42.2% 的 v1 demo reverse regression 原值保留，不是 v2 結果。

## V2 rule cadence / P0-06

每條規則由自己的 OBSERVED/REALIZED 季度錨點建立期間窗口，不使用全域資料日期；窗口和資產 calendar／reporting grace／新鮮度政策有獨立版本與簽章。歷史估值須逐季指定，資訊須在該季估值時已符合所選 knowledge policy；每日 UNI 報價不會製造 SECZ/XLM 新季度。沒有季報、財年未知、TTM 期間錯位或報價過期都明示未評估。九條舊規則均可檢視，唯有使用 P0-05 實現公式的 UNI 低 burn 規則可於來源齊備時評估；其他八條缺 v2 對應資料，**不能用 v1 fixture 自動填補**。

```bash
python -m engine.cli thesis-cadence \
  --economic-cutoff 2026-09-26 --knowledge-cutoff 2026-09-26T12:00:00Z \
  --policy AS_KNOWN_BY_SYSTEM --valuations '{}'
# 若有具證據的逐季估值，格式例：--valuations '{"2026-06-30":"2026-07-06T10:05:00Z"}'
```

Dashboard 的「V2 cadence」和唯讀 `/api/thesis-cadence` 提供相同查詢。SECZ 發行人 fiscal year-end 尚未驗證，政策填 null；v1 Thesis 區特別標 LEGACY V1，仍有全域日期缺陷，不可當 point-in-time 判斷或實盤訊號。詳見 [P0-06 驗收](reports/p0-06-validation.md)。

## V2 replayable audit bundle / P0-07

`snapshot-v2` 明示兩個 track：`HISTORICAL` 指定知識與估值截止、資訊政策；`CURRENT` 捕捉呼叫當下的 UTC 系統時間，固定使用 system-as-known。每份 audit bundle 封存 v2 資料與來源版本、公式／規則／字典／graph、程式碼和 runtime lock、選用證據的 record/source 雜湊與完整計算結果。檔名是整份檔案的 SHA-256；`replay-v2` 先驗每個位元組與執行版本，再從封存的資料重算。結果是 `AUDIT_ONLY`；真實研究 ledger 仍空，不會由此產生可投資的結論。

```bash
python -m engine.cli snapshot-v2 --track HISTORICAL \
  --economic-cutoff 2026-09-26 --realized-quarter-end 2026-06-30 \
  --horizon-end 2027-12-31 --knowledge-cutoff 2026-09-26T12:00:00Z \
  --valuation-at 2026-09-26T12:00:00Z --policy AS_KNOWN_BY_SYSTEM
python -m engine.cli replay-v2 /path/from/previous/output.json
```

第一個指令會明確寫入 `data/snapshots/v2/research/historical/`；先用 `--root /path/to/disposable/project` 在隔離專案試跑。相同內容重試會回報 `created: false`。`CURRENT` 不接受手填 knowledge／valuation 時鐘；歷史逐季報價另以 `--valuations` 明示。此命令不修改 v1 快照，既有 `snapshot`／`compare` 仍只代表 legacy v1。封存 source URL 及 metadata 並不等於已封存外部來源原文，也不構成真實性或作者身分認證。見 [驗收與舊版遷移報告](reports/p0-07-validation.md)；GET 純讀及 v1 事件跨檔案事務見 [P0-08](reports/p0-08-validation.md)。

## Architecture

`sources/sources.yaml` → `data/observed/*.yaml` → `spec/canonical-schema.yaml` → `spec/formula-registry.yaml` → `engine/formulas/` → `engine/validation/` → `engine/thesis/` and `engine/propagation/` → immutable `data/snapshots/*.json` → `engine/server.py` API → `dashboard/`.

| Layer | Role |
| --- | --- |
| `spec/` | Human-readable data dictionary, expression formulas and locked signatures, assumption revisions, named scenarios, thesis thresholds, graph and universe |
| `sources/` | Source identity and metadata; synthetic source is marked FIXTURE |
| `data/observed/` | Append-only observations with period, unit and source; `research.yaml` starts empty |
| `data/events/` | Typed, status-aware events with separate materiality |
| `data/snapshots/` | Content-addressed write-once research states; two demo versions included |
| `engine/` | YAML validation, safe expression evaluator, lineage, history-aware thesis rules, sensitivity recomputation, graph propagation, snapshot comparison and loopback API |
| `dashboard/` | Vanilla HTML/CSS/JS that receives financial values only from the engine |
| `tests/` | Deterministic UNI, SECZ and XLM regressions and evidence/temporal/transition tests |

## Data and calculation conventions

- FRACTION is stored as a decimal (0.25 = 25%); BP is basis points (1.25 bp = 0.000125). USD and native token units are separate.
- AUM is a point-in-time stock; turnover and protocol revenue are annualized/TTM flows. `tokenized_equity_tam` is a hypothetical scenario, while `tokenized_equity_aum` is a separate current observed input. The modeled UNI AUM is `TAM × penetration assumption` and is **not** present market AUM.
- `required_uniswap_market_share` exactly implements the project's standalone equity-only reverse hurdle. `incremental_required_share` also deducts other protocol accrual and adds other dilution. Neither is a price target.
- Growth budget (20M UNI/year) was supplied in the brief but not independently verified in this build; it is an **assumption**, multiplied by UNI price for synthetic annual USD distribution value. Treating a distribution as dilution is a modeling convention and may double count or misclassify actual treasury transfers until supply mechanics are verified.
- SECZ revenue is the sum of six streams, not AUM times a flat rate. Prior TTM comparisons must have compatible periods; enterprise value backs out required FCF/revenue.
- XLM native asset demand uses locked XLM components. Network fee USD is shown as a diagnostic, never used as fee-only token fair value.
- Source conflicts return `Unknown` with an error. Empty inputs propagate `Unknown`; zero denominators return errors. A requested share above 100% warns.

## Updating research evidence

1. Inspect a primary source; add a uniquely identified version in `sources/sources.yaml` with publication/retrieval dates and metrics.
2. Append a new row to `data/observed/research.yaml`: `id`, `metric_id`, `classification: OBSERVED`, numeric `value`, dictionary `unit`, `source_id`, `as_of_date`, `period: {basis,start,end}`, `fixture: false`. Keep prior rows. A correction uses `supersedes_id` and the same observation date.
3. Add a rationale to any new assumption, or a name to any new scenario. Preserve old revisions and adjust effective dates. Increase formula version and update its lock (run `PYTHONPATH=. python tools/lock_formulas.py`) if its expression changes; add a changelog entry.
4. Validate, test, create a snapshot, compare, inspect all issues and provenance in the dashboard. A live event needs its own source and status transition; reference observation IDs.

The MVP has no automated fetch, earnings parser, source freshness alert or external execution. Event ingestion validates before append, but the YAML ledger, snapshot and changelog are separate local files; it is not crash-atomic like a database transaction. Historical source records and observations are protected against in-place edits once a snapshot exists. Repository files should also be tracked in version control and reviewed when changed.

See `reports/methodology.md`, `reports/current-thesis.md`, `reports/changelog.md`, `task.md` and `AGENTS.md`.
