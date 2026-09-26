# Tokenized Capital Markets Living Underwriting Engine

Local, reproducible investment research software. This MVP is an **engine plus a traceable presentation layer**, with a deliberately synthetic demo pack. It contains **no verified live prices or company financials**. The identifiers `SECZ` and its investability/listing status are research items, not an assertion that an instrument is currently listed.

## 後續發展規劃 / Development plan

已完成 [2026-09-25 詳細規劃與現況稽核](docs/planning/README.md)：可信資料與歷史重播、三資產經濟模型、真實研究流程、投資優勢驗證、成本後模擬與有限人工實證。尚未完成的功能維持 **PROPOSED / PLANNED**。

2026-09-26 已完成 **WP-01：研究資料隔離與嚴格輸入驗證**，軟體版本 0.1.1，**67 項測試通過**，詳見 [驗收紀錄](reports/wp-01-validation.md)。也已完成 **P0-03 的 v2 資料契約設計**，詳見 [ADR](docs/planning/ADR-0001-V2-TIME-SCOPE-MIGRATION.md)；此設計尚未在引擎執行。真實 observation 仍為 0；歷史可知時間、混合頻率與完整快照重播仍待實作。現有 MVP 不代表已驗證的投資優勢或實盤系統。下一步為 **P0-04：雙時間 selector 與歷史重述重播**，依賴與驗收見 [structured backlog](docs/planning/IMPLEMENTATION_BACKLOG.yaml)。

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

Open `http://127.0.0.1:8765/`. `--demo` is explicit: pink DEMO markers mean every financial observation is synthetic. Run `python -m engine.cli serve` for research mode; current numerical observations and fixture assumptions are absent, so values are correctly **Unknown** until sourced.

Other commands:

```bash
python -m engine.cli validate              # validate real research pack (currently empty)
python -m engine.cli snapshot --demo --as-of 2026-06-30
python -m engine.cli compare --demo
python -m engine.cli apply-event --demo --id event_demo_dtcc_planned
```

For a sourced LIVE/COMPLETED event, add its immutable record and source to the registries, then run `python -m engine.cli apply-event --id EVENT_ID --observations new-observations.yaml`. The batch must use fresh IDs, match the event's source IDs and classification, and pass full validation before its observations are appended. The command recalculates, applies thesis rules, writes a snapshot and records the event in `reports/changelog.md`. Planned/announced events cannot ingest live observations. The demo command above has no new observations and only records graph propagation; avoid running it when you want the default two-version comparison unchanged.

## Input validation / WP-01

- 所有計算、CLI、HTTP、事件與 snapshot 入口先驗證輸入。重複 YAML key、aliases／merge、NaN／Infinity、錯誤型別、未知欄位、重複 ID、非法 supersession 與 formula cycle 會被拒絕。日期使用引號包住的 `YYYY-MM-DD`；`fixture` 使用真正的 boolean，不接受字串 `"false"`。
- RESEARCH 不載入 demo ledger。共享設定中明確 `fixture: true` 的 assumptions／scenarios／graph edges 可依政策排除；排除清單由 API 的 `loading_policy` 提供。未引用的 fixture source 可以保留。
- 放錯到 research ledger 的 fixture observation／event 直接報錯，使用 `--demo` 也不能繞過；`fixture: false` 但引用 fixture source 同樣拒絕。來源相同數值的多筆證據全部保留，任何 synthetic dependency 都會傳到衍生結果。
- 輸入驗證失敗：CLI 以 exit code 1 及 stderr JSON issues 回覆；HTTP state／sensitivity 回傳 422 與 `issues`。issue 包含 `level`、`code`、`message`、`path`；例：`RESEARCH_FIXTURE`、`YAML_DUPLICATE_KEY`。失敗不發布 snapshot 或寫入 ledger／changelog。
- 測試與隔離資料包可指定根目錄：`python -m engine.cli --root /path/to/project validate`。`--root` 放在子命令前。

這些檢查驗證已宣告的結構、來源引用與模式邊界；它們不會自動查證來源內容是否真實，也無法辨識刻意冒充真資料的未標記數字。新增真實 OBSERVED 仍須人工核對原始證據。未保存的 sensitivity overrides 不可直接存為 canonical snapshot。

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
