# Tokenized Capital Markets Living Underwriting Engine

Local, reproducible investment research software. This MVP is an **engine plus a traceable presentation layer**, with a deliberately synthetic demo pack. It contains **no verified live prices or company financials**. The identifiers `SECZ` and its investability/listing status are research items, not an assertion that an instrument is currently listed.

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
