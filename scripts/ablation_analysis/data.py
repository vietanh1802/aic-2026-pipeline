# scripts/ablation_analysis/data.py
"""Load an ablation run folder (ablation.db, suite.json, provenance.json) into plain Python objects.

Only sqlite3 and json: no backend import, so it runs on a PC that has not got torch or faiss. One Result
per (configuration, dataset, query). A query that failed has rank None and counts as a miss everywhere,
as in scoring.py.

Run mode. A folder is classified before anything is written, because synthetic or smoke numbers must
never be mistaken for results:
  SYNTHETIC  provenance.json says "synthetic" : true (scripts/make_synthetic_ablation_db.py)
  SMOKE      a limit on queries per dataset was used, the shared-search verification was skipped, or the
             recorded device is "test"
  REAL       none of the above
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CANONICAL_MODELS = ("beit3", "clip", "siglip2")
HIT_KS = (1, 3, 5, 10, 20, 50, 100)
NOT_RETRIEVED_RANK = 101   # where a miss goes when a rank correlation needs a number: worse than any returned rank


@dataclass
class Result :
    """One query under one configuration."""
    code : str
    config_name : str
    run_id : int
    dataset : str
    bench : str                # "A" (rounds 1 to 3) or "B" (final-v1)
    key : str
    task : str
    ref_video : str
    prefix : str
    status : str
    rank : int | None          # video rank of the reference, None if not retrieved or failed
    query_vi : str
    query_en : str | None
    intervals : list[tuple[int, int]]
    ref_frame_idx : int | None
    interval_hit : bool | None
    interval_rank : int | None
    final_score : float | None
    retrieval_ms : float | None
    frames : list[dict[str, Any]]
    ranked : list[dict[str, Any]]
    extra : dict[str, Any]
    error : str | None = None

    @property
    def uid(self) -> tuple[str, str] :
        return (self.dataset, self.key)

    @property
    def flags(self) -> list[str] :
        return list(self.extra.get("flags") or [])

    def hit(self, k : int) -> bool :
        return self.rank is not None and self.rank <= k

    @property
    def rr(self) -> float :
        return 1.0 / self.rank if self.rank else 0.0

    @property
    def rank_or_miss(self) -> int :
        return self.rank if self.rank is not None else NOT_RETRIEVED_RANK


@dataclass
class ConfigInfo :
    code : str
    name : str
    config : dict[str, Any]
    role : str
    sanity : bool = False      # a sanity check, not an ablation arm: kept in the CSVs, left out of the paper tables


@dataclass
class RunData :
    folder : Path
    results : list[Result]
    configs : dict[str, ConfigInfo]
    provenance : dict[str, Any]
    suite : dict[str, Any]
    mode : str = "REAL"
    mode_reasons : list[str] = field(default_factory = list)
    by_code : dict[str, dict[tuple[str, str], Result]] = field(default_factory = dict)
    # {(dataset, query_key): {"confidence", "provenance", "status", "notes", "trake_events"}} from the reference set
    refs : dict[tuple[str, str], dict[str, Any]] = field(default_factory = dict)

    @property
    def stamp(self) -> str :
        return "" if self.mode == "REAL" else f"{self.mode} RUN"

    def code_for(self, role : str) -> str | None :
        return next((c for c, info in self.configs.items() if info.role == role), None)

    def results_of(self, code : str, bench : str | None = None, *, clean : bool = False, task : str | None = None, prefix : str | None = None) -> list[Result] :
        """Results of one configuration in query order. clean drops queries that carry a label flag."""
        picked = []
        for r in self.by_code.get(code, {}).values() :
            if ((bench and r.bench != bench) or (task and r.task != task) or (prefix and r.prefix != prefix) or (clean and r.flags)) :
                continue
            picked.append(r)
        return picked

    def query_ids(self, bench : str, code : str | None = None) -> list[tuple[str, str]] :
        code = code or self.code_for("base")
        return [r.uid for r in self.results_of(code, bench)] if code else []


def config_code(name : str) -> str :
    """C01, T01, and the lettered arms C12a to C12c."""
    match = re.match(r"^([A-Z]\d+[a-z]?)\b", name)
    return match.group(1) if match else name


def role_of(config : dict[str, Any], base_text : str = "translate_gtx") -> str :
    """What a configuration is, from its fields (not its name), so a renamed preset still maps.

    base_text is the text policy of the run folder's baseline (C01): translate_gtx in the first real run,
    expand_gemini from preset core2 on. An arm that searches the baseline's text is classified by its encoders
    and rerank mode; an arm that varies the text is plain_text (translate_gtx against an Expand baseline),
    expand_gemini (the reverse) or raw_vi."""
    models = [m for m in CANONICAL_MODELS if m in config.get("models", [])]
    mode, text, task_mode = config.get("rerank_mode", "per_model"), config.get("text_policy", ""), config.get("task_mode", "ensemble")
    if (task_mode == "trake_n") :
        return "trake_n"
    if ((config.get("subset") or {}).get("task_types") == ["TRAKE"]) :
        return "trake_plain"
    label = "+".join(models)
    all_models = len(models) == len(CANONICAL_MODELS)
    if (text == base_text and mode == "per_model" and all_models) :
        return "base"
    if (text == "raw_vi" and all_models and mode == "per_model") :
        return "raw_vi"
    if (text != base_text and all_models and mode == "per_model") :
        return "expand_gemini" if text == "expand_gemini" else "plain_text" if text == "translate_gtx" else f"other:{label}:{mode}:{text}"
    if (text != base_text) :
        return f"other:{label}:{mode}:{text}"
    suffix = "" if mode == "per_model" else f":{mode}"
    return ("all" if all_models else f"single:{label}" if len(models) == 1 else f"pair:{label}") + suffix


def _json(value : str | None, default : Any) -> Any :
    return json.loads(value) if value else default


def detect_mode(provenance : dict[str, Any], suite : dict[str, Any], devices : set[str], features_synthetic : bool = False) -> tuple[str, list[str]] :
    synthetic = []
    if (provenance.get("synthetic")) :
        synthetic.append("provenance.json has synthetic = true")
    if (features_synthetic) :
        synthetic.append("corpus_totals.json has synthetic = true")
    if (synthetic) :
        return "SYNTHETIC", synthetic
    smoke = []
    limit = suite.get("limit_queries", provenance.get("limit_queries"))
    if (limit) :
        smoke.append(f"limit_queries = {limit}")
    for verify in (suite.get("verify"), provenance.get("verify_shared_search")) :
        if (isinstance(verify, dict) and verify.get("skipped")) :
            smoke.append("shared-search verification was skipped")
            break
    if ("test" in devices) :
        smoke.append('recorded device is "test"')
    return ("SMOKE", smoke) if smoke else ("REAL", [])


def load_run_folder(folder : Path, features_synthetic : bool = False) -> RunData :
    folder = Path(folder)
    db_path = folder / "ablation.db"
    if (not db_path.exists()) :
        raise FileNotFoundError(f"{db_path} not found: the run folder must include ablation.db (tar without --exclude=ablation.db)")
    provenance = _json((folder / "provenance.json").read_text(encoding = "utf-8"), {}) if (folder / "provenance.json").exists() else {}
    suite = _json((folder / "suite.json").read_text(encoding = "utf-8"), {}) if (folder / "suite.json").exists() else {}

    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri = True)
    conn.row_factory = sqlite3.Row
    configs : dict[str, ConfigInfo] = {}
    devices : set[str] = set()
    results : list[Result] = []
    refs : dict[tuple[str, str], dict[str, Any]] = {}
    runs = conn.execute(
        "SELECT r.id, r.reference_set_id, r.configuration_json, r.runtime_json, r.status, d.version AS dataset, d.slug AS slug "
        "FROM evaluation_runs r JOIN evaluation_datasets d ON d.id = r.dataset_id ORDER BY r.id"
    ).fetchall()
    base_text = "translate_gtx"
    for run in runs :
        config = _json(run["configuration_json"], {}).get("config") or {}
        if (config_code(config.get("name") or "") == "C01") :
            base_text = config.get("text_policy", base_text)
            break
    for run in runs :
        configuration = _json(run["configuration_json"], {})
        config = configuration.get("config") or {}
        name = config.get("name") or configuration.get("config_name") or f"run {run['id']}"
        code = config_code(name)
        role = role_of(config, base_text)
        # The old preset's C12 (raw Vietnamese) predates the flag: it is a sanity check by what it is.
        configs.setdefault(code, ConfigInfo(code, name, config, role, sanity = bool(config.get("sanity")) or role == "raw_vi"))
        for ref in conn.execute(
            "SELECT q.query_key, r.confidence, r.provenance, r.status, r.notes, r.trake_events_json FROM evaluation_references r "
            "JOIN evaluation_queries q ON q.id = r.query_id WHERE r.reference_set_id = ?", (run["reference_set_id"],)
        ) :
            refs[(run["dataset"], ref["query_key"])] = {
                "confidence" : ref["confidence"], "provenance" : ref["provenance"], "status" : ref["status"],
                "notes" : ref["notes"], "trake_events" : _json(ref["trake_events_json"], []),
            }
        runtime = _json(run["runtime_json"], {})
        if (runtime.get("device")) :
            devices.add(str(runtime["device"]))
        rows = conn.execute(
            "SELECT * FROM evaluation_query_results WHERE run_id = ? AND status IN ('completed', 'failed') ORDER BY ordinal", (run["id"],)
        ).fetchall()
        for row in rows :
            completed = row["status"] == "completed"
            results.append(Result(
                code = code, config_name = name, run_id = run["id"], dataset = run["dataset"], bench = "B" if run["slug"] == "final" else "A",
                key = row["query_key"], task = row["task_type"], ref_video = row["reference_video"], prefix = str(row["reference_video"])[ : 1],
                status = row["status"], rank = row["reference_video_rank"] if completed else None,
                query_vi = row["query_vi"], query_en = row["query_en"],
                intervals = [(int(i["start"]), int(i["end"])) for i in _json(row["reference_intervals_json"], None) or []],
                ref_frame_idx = row["reference_frame_idx"],
                interval_hit = None if row["interval_hit"] is None else bool(row["interval_hit"]),
                interval_rank = row["interval_rank"], final_score = row["final_score"], retrieval_ms = row["retrieval_ms"],
                frames = _json(row["frame_results_json"], []), ranked = _json(row["ranked_videos_json"], []),
                extra = _json(row["extra_json"], {}), error = row["error"],
            ))
    conn.close()

    data = RunData(folder = folder, results = results, configs = configs, provenance = provenance, suite = suite, refs = refs)
    for r in results :
        data.by_code.setdefault(r.code, {})[r.uid] = r
    data.mode, data.mode_reasons = detect_mode(provenance, suite, devices, features_synthetic)
    return data
