"""Loopback-only local UI/API. Financial calculations never run in JavaScript."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from engine.formulas.runtime import calculate
from engine.sensitivity.analysis import matrix, run
from engine.snapshots import compare, read_snapshots, save_snapshot
from engine.storage import load_project, ROOT
from engine.thesis.rules import evaluate_theses
from engine.temporal import calculate_economics, load_temporal_project
from engine.temporal.economics import LEGACY_V1_SCOPES
from engine.validation.checks import require_valid_project
from engine.validation.errors import ValidationError, reject_errors
from engine.validation.lineage import validate_lineage


def payload(project, overrides=None, persist=False):
    problems = require_valid_project(project)
    state = run(project, overrides) if overrides else calculate(project)
    if not overrides:
        state["thesis"] = evaluate_theses(project, state)
    problems += state["issues"] + validate_lineage(project, state)
    if persist:
        reject_errors(problems)
    if persist and (project["demo"] or any(x["classification"] == "OBSERVED" and x["value"] is not None for x in state["metrics"].values())):
        save_snapshot(project, state)
    history = read_snapshots(project["root"], state["mode"])
    comparison = compare(history[-2], history[-1]) if len(history) >= 2 else None
    return {**state, "issues": problems, "legacy_scopes": LEGACY_V1_SCOPES,
            "graph": project["graph"], "events": project["events"],
            "loading_policy": project.get("loading_policy", {}),
            "assets": project["assets"]["assets"], "comparison": comparison,
            "snapshots": [{"id": x["id"], "as_of_date": x["as_of_date"], "created_at": x["created_at"]} for x in history],
            "matrix": matrix(project, state["as_of_date"], overrides=overrides),
            "disclaimer": "Synthetic demonstration; all financial values are fixtures or analyst assumptions." if project["demo"] else
                          "Research mode: missing observations remain unknown until sourced."}


def handler_factory(root, demo):
    root = Path(root)
    dashboard = root / "dashboard"

    class Handler(BaseHTTPRequestHandler):
        def _json(self, status, object_):
            data = json.dumps(object_, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if urlsplit(self.path).path == "/api/economics":
                try:
                    query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
                    required = {"realized_quarter_end", "horizon_end", "knowledge_cutoff", "valuation_at", "policy"}
                    if set(query) != required or any(len(v) != 1 for v in query.values()):
                        raise ValueError("Expected exactly five scope-report query parameters")
                    args = {key: query[key][0] for key in required}
                    result = calculate_economics(load_temporal_project(root, demo=demo),
                                                 realized_quarter_end=args["realized_quarter_end"],
                                                 horizon_end=args["horizon_end"],
                                                 knowledge_cutoff=args["knowledge_cutoff"],
                                                 valuation_at=args["valuation_at"],
                                                 knowledge_policy=args["policy"], root=root)
                    self._json(200, result)
                except ValidationError as exc:
                    self._json(422, {"error": str(exc), "issues": exc.issues})
                except (ValueError, KeyError) as exc:
                    self._json(422, {"error": str(exc)})
                return
            if self.path == "/api/state":
                try:
                    self._json(200, payload(load_project(root, demo), persist=True))
                except ValidationError as exc:
                    self._json(422, {"error": str(exc), "issues": exc.issues})
                except (ValueError, KeyError) as exc:
                    self._json(422, {"error": str(exc)})
                return
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/style.css": ("style.css", "text/css; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript; charset=utf-8")}
            if self.path not in files:
                self.send_error(404)
                return
            name, mime = files[self.path]
            data = (dashboard / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path != "/api/sensitivity":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 2 or length > 65536:
                    raise ValueError("Invalid request size")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or not isinstance(body.get("overrides"), dict):
                    raise ValueError("Expected {'overrides': {...}}")
                result = payload(load_project(root, demo), overrides=body["overrides"], persist=False)
                errors = [x for x in result["issues"] if x["level"] == "ERROR"]
                self._json(422 if errors else 200, result)
            except ValidationError as exc:
                self._json(422, {"error": str(exc), "issues": exc.issues})
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})

    return Handler


def serve(host="127.0.0.1", port=8765, root=ROOT, demo=False):
    project = load_project(root, demo)
    require_valid_project(project)
    server = ThreadingHTTPServer((host, port), handler_factory(root, demo))
    print(f"Local dashboard: http://{host}:{server.server_port}/ ({'DEMO' if demo else 'RESEARCH'})", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
