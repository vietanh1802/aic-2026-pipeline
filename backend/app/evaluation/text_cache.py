# backend/app/evaluation/text_cache.py
"""Record and replay of the text a benchmark query is searched with.

The production UI has no automatic text step: the operator searches the box as typed, or presses
Translate (browser gtx) or Expand (Gemini through /api/expansion) first. The benchmark maps those
to three text policies and calls the SAME functions production calls (translation.py,
expansion.py). Because those outputs come from the network, each one is recorded the first time it
is needed and replayed afterwards:

  - the key is (policy id, model name, prompt hash, normalised query text, task type), so editing a
    prompt or switching model never serves stale text;
  - preflight checks that every needed pair is cached, or fetchable (no key needed, or a key is
    configured), BEFORE a run is created and answers HTTP 422 with the missing list otherwise;
  - prefetch fills the missing pairs before the first retrieval, so retrieval never calls an LLM or
    the network, per query or otherwise;
  - the cache exports to and imports from JSONL, so it can be filled on one machine (gtx may be
    unreachable from EC2) and carried to another.

An Expand answer is recorded only when Gemini produced it. The Ollama fallback in expansion.py would
silently turn the Expand arm into a different model, so it is refused.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.db.connection import utcnow_iso

TEXT_POLICIES = ("raw_vi", "translate_gtx", "expand_gemini")

# raw_vi needs no function at all. The other two map to the production function they replay.
_POLICY_ID = {"translate_gtx" : "google_gtx_v1", "expand_gemini" : "expand_v1"}
_NEEDS_KEY = {"raw_vi" : False, "translate_gtx" : False, "expand_gemini" : True}

# Both Expand entry points in the UI wrap the text like this; see expansion._gemini_expand.
_EXPAND_WRAPPER = "[type={task_type}]\n{text}"


class TextCacheMiss(LookupError) :
    """Replay asked for a pair that is not cached. Retrieval never falls back to the network."""


class PrefetchError(RuntimeError) :
    pass


class PreflightBlocked(RuntimeError) :
    """Missing text that needs a key which is not configured. Routers map this to HTTP 422."""

    def __init__(self, report : dict[str, Any]) :
        super().__init__(report["message"])
        self.report = report


@dataclass(frozen = True)
class TextKey :
    policy      : str
    policy_id   : str
    model       : str
    prompt_sha  : str
    text_sha    : str
    task_type   : str

    def digest(self) -> str :
        joined = "|".join((self.policy_id, self.model, self.prompt_sha, self.text_sha, self.task_type))
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()


@dataclass(frozen = True)
class NeededText :
    policy    : str
    dataset   : str
    query_key : str
    text      : str
    task_type : str


@dataclass(frozen = True)
class CachedText :
    text        : str
    check_units : list[str]
    provider    : str | None
    digest      : str


def normalize_text(text : str) -> str :
    """NFC and collapsed whitespace: two spellings of the same Vietnamese must share a key."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def _sha(text : str) -> str :
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def needs_key(policy : str) -> bool :
    return _NEEDS_KEY[policy]


def key_configured() -> bool :
    # Presence only. The value is never read into a log, a message or a report.
    return bool(os.getenv("GEMINI_API_KEY"))


def make_key(policy : str, text : str, task_type : str = "") -> TextKey :
    if (policy not in _POLICY_ID) :
        raise ValueError(f"policy {policy} has no cache key")
    if (policy == "expand_gemini") :
        from app import expansion
        model = expansion._GEMINI_MODEL
        prompt = expansion._EXPAND_SYSTEM + "\n" + _EXPAND_WRAPPER
        task = task_type
    else :
        from app import translation
        model = "google_gtx"
        prompt = f"{translation._GOOGLE_GTX_URL}?client=gtx&sl=auto&tl=en&dt=t"
        task = ""   # gtx never sees the task type, so every task type shares one entry
    return TextKey(policy, _POLICY_ID[policy], model, _sha(prompt), _sha(normalize_text(text)), task)


def lookup(conn : sqlite3.Connection, key : TextKey) -> dict[str, Any] | None :
    row = conn.execute(
        """
        SELECT output_json, provider FROM evaluation_text_cache
        WHERE policy_id = ? AND model = ? AND prompt_sha256 = ? AND text_sha256 = ? AND task_type = ?
        """,
        (key.policy_id, key.model, key.prompt_sha, key.text_sha, key.task_type),
    ).fetchone()
    if (row is None) :
        return None
    return {"output" : json.loads(row["output_json"]), "provider" : row["provider"]}


def store(
    conn : sqlite3.Connection,
    key : TextKey,
    text : str,
    output : dict[str, Any],
    provider : str | None,
    run_id : int | None = None,
) -> None :
    conn.execute(
        """
        INSERT OR IGNORE INTO evaluation_text_cache (
            policy_id, model, prompt_sha256, text_sha256, task_type,
            query_norm, output_json, provider, source_run_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            key.policy_id, key.model, key.prompt_sha, key.text_sha, key.task_type,
            normalize_text(text), json.dumps(output, ensure_ascii = False), provider, run_id, utcnow_iso(),
        ),
    )


def get_text(conn : sqlite3.Connection, policy : str, text : str, task_type : str = "") -> CachedText :
    """Replay. Reads the table only; raises TextCacheMiss rather than ever reaching the network."""
    if (policy == "raw_vi") :
        return CachedText(text, [], None, "raw_vi")
    key = make_key(policy, text, task_type)
    hit = lookup(conn, key)
    if (hit is None) :
        raise TextCacheMiss(f"{policy}: no cached text for {normalize_text(text)[ : 60]!r} ({task_type or '-'})")
    output = hit["output"]
    searched = output.get("eng_query") or output.get("text") or ""
    return CachedText(searched, list(output.get("check_units") or []), hit["provider"], key.digest())


def query_rows(conn : sqlite3.Connection, dataset_version : str) -> list[sqlite3.Row] :
    """Every query of a dataset's newest reference set with what preflight and selection need."""
    return conn.execute(
        """
        SELECT d.slug AS dataset_slug, d.version AS dataset_version, q.query_key, q.task_type,
               q.query_vi, r.video_id, r.valid_intervals_json, r.trake_events_json
        FROM evaluation_queries q
        JOIN evaluation_datasets d ON d.id = q.dataset_id
        JOIN evaluation_reference_sets rs ON rs.dataset_id = d.id
            AND rs.id = (SELECT MAX(id) FROM evaluation_reference_sets WHERE dataset_id = d.id)
        JOIN evaluation_references r ON r.query_id = q.id AND r.reference_set_id = rs.id
        WHERE d.version = ?
        ORDER BY q.ordinal
        """,
        (dataset_version,),
    ).fetchall()


def needed_texts(conn : sqlite3.Connection, config, dataset_versions : list[str]) -> list[NeededText] :
    """The (policy, text, task type) pairs a run of `config` over these datasets will search with."""
    from app.evaluation.flags import select_rows

    if (config.text_policy == "raw_vi") :
        return []
    needed : list[NeededText] = []
    for version in dataset_versions :
        rows = select_rows(query_rows(conn, version), config)
        for row in rows :
            if (config.task_mode == "trake_n") :
                # TRAKE-N searches each event on its own, so each event is a text.
                events = json.loads(row["trake_events_json"] or "[]")
                for event in events :
                    needed.append(NeededText(
                        config.text_policy, version, f"{row['query_key']}/{event['event_id']}",
                        event["description_vi"], row["task_type"],
                    ))
            else :
                needed.append(NeededText(config.text_policy, version, row["query_key"], row["query_vi"], row["task_type"]))
    return needed


def planned_digests(conn : sqlite3.Connection, config, dataset_version : str) -> list[str] :
    """Digest of every cache key a run of `config` over one dataset will read."""
    return sorted({
        make_key(item.policy, item.text, item.task_type).digest()
        for item in needed_texts(conn, config, [dataset_version])
    })


def preflight(conn : sqlite3.Connection, configs : list, dataset_versions : list[str]) -> dict[str, Any] :
    """Count cached and missing pairs; mark the report blocked when a missing pair needs a key
    that is not configured. Does not raise: ensure_ready() decides."""
    needed : list[NeededText] = []
    for config in configs :
        needed.extend(needed_texts(conn, config, dataset_versions))

    seen : set[str] = set()
    unique : list[tuple[NeededText, TextKey]] = []
    for item in needed :
        key = make_key(item.policy, item.text, item.task_type)
        if (key.digest() in seen) :
            continue
        seen.add(key.digest())
        unique.append((item, key))

    missing = [item for item, key in unique if lookup(conn, key) is None]
    key_present = key_configured()
    blocked_policies = sorted({item.policy for item in missing if needs_key(item.policy) and not key_present})
    by_policy : dict[str, int] = {}
    for item in missing :
        by_policy[item.policy] = by_policy.get(item.policy, 0) + 1

    report = {
        "needed"           : len(unique),
        "cached"           : len(unique) - len(missing),
        "missing"          : len(missing),
        "missing_by_policy": by_policy,
        "key_configured"   : key_present,
        "blocked"          : bool(blocked_policies),
        "blocked_policies" : blocked_policies,
        "first_missing"    : [
            {"policy" : m.policy, "dataset" : m.dataset, "query_key" : m.query_key} for m in missing[ : 20]
        ],
        "message"          : "",
    }
    if (blocked_policies) :
        report["message"] = (
            f"{len(missing)} text(s) are not cached and policy {', '.join(blocked_policies)} needs "
            f"GEMINI_API_KEY, which is not configured. Set the key or import a text cache."
        )
    report["_missing_items"] = missing
    return report


def public_report(report : dict[str, Any]) -> dict[str, Any] :
    return {k : v for k, v in report.items() if not k.startswith("_")}


def ensure_ready(report : dict[str, Any]) -> None :
    if (report["blocked"]) :
        raise PreflightBlocked(public_report(report))


def prefetch(
    conn : sqlite3.Connection,
    missing : list[NeededText],
    run_id : int | None = None,
    *,
    gtx_fn : Callable[[str], tuple[str, float]] | None = None,
    expand_fn : Callable[[str, str], dict[str, Any]] | None = None,
    on_progress : Callable[[int, int], None] | None = None,
) -> int :
    """Call the production function for each missing pair and record it. Runs before any
    retrieval; the first failure stops it with the pair named, so a run is never left half
    fed. The 4.5 s per-provider pacing lives inside the production functions."""
    if (gtx_fn is None) :
        from app.translation import translate_vi_to_en

        def gtx_fn(text : str) -> tuple[str, float] :
            return translate_vi_to_en(text, policy = "google_gtx_v1")

    if (expand_fn is None) :
        from app.expansion import expand_query as expand_fn

    fetched = 0
    done : set[str] = set()
    for index, item in enumerate(missing, start = 1) :
        key = make_key(item.policy, item.text, item.task_type)
        if (key.digest() in done or lookup(conn, key) is not None) :
            continue
        done.add(key.digest())
        label = f"{item.policy} {item.dataset}/{item.query_key}"
        if (item.policy == "translate_gtx") :
            try :
                translated, _ms = gtx_fn(item.text)
            except Exception as exc :
                raise PrefetchError(f"{label}: {type(exc).__name__}: {exc}") from exc
            store(conn, key, item.text, {"text" : translated}, "google_gtx", run_id)
        elif (item.policy == "expand_gemini") :
            result = expand_fn(item.text, item.task_type or "KIS")
            if (result.get("error")) :
                raise PrefetchError(f"{label}: {result['error']}")
            if (result.get("provider") != "gemini") :
                raise PrefetchError(
                    f"{label}: Expand answered through {result.get('provider')!r}; only Gemini "
                    f"outputs are recorded because another provider would change the arm"
                )
            output = {
                "eng_query"        : result["eng_query"],
                "check_units"      : list(result.get("check_units") or []),
                "translated_query" : result.get("translated_query"),
            }
            store(conn, key, item.text, output, "gemini", run_id)
        else :
            raise PrefetchError(f"{label}: policy has nothing to fetch")
        fetched += 1
        if (on_progress is not None) :
            on_progress(index, len(missing))
    return fetched


TEXT_CACHE_DIR = Path(__file__).resolve().parent / "seeds" / "text_cache"

_EXPORT_FIELDS = (
    "policy_id", "model", "prompt_sha256", "text_sha256", "task_type",
    "query_norm", "output_json", "provider", "created_at",
)


def export_jsonl(conn : sqlite3.Connection) -> str :
    rows = conn.execute(
        f"SELECT {', '.join(_EXPORT_FIELDS)} FROM evaluation_text_cache "
        "ORDER BY policy_id, model, prompt_sha256, text_sha256, task_type"
    ).fetchall()
    return "".join(json.dumps({f : row[f] for f in _EXPORT_FIELDS}, ensure_ascii = False) + "\n" for row in rows)


def import_jsonl(conn : sqlite3.Connection, text : str) -> dict[str, int] :
    """INSERT OR IGNORE: an entry already present wins, so importing twice changes nothing and a
    stale file can never overwrite what this database recorded."""
    inserted = skipped = 0
    for number, line in enumerate(text.splitlines(), start = 1) :
        if (not line.strip()) :
            continue
        entry = json.loads(line)
        missing = [f for f in _EXPORT_FIELDS if f not in entry]
        if (missing) :
            raise ValueError(f"line {number}: missing fields {missing}")
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO evaluation_text_cache (
                policy_id, model, prompt_sha256, text_sha256, task_type,
                query_norm, output_json, provider, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(entry[f] for f in _EXPORT_FIELDS),
        )
        inserted += cursor.rowcount
        skipped += 1 - cursor.rowcount
    return {"inserted" : inserted, "skipped" : skipped}


def import_seed_caches(conn : sqlite3.Connection, directory : Path = TEXT_CACHE_DIR) -> dict[str, int] :
    """Load every seeds/text_cache/*.jsonl (INSERT OR IGNORE). A cache filled on one machine and
    committed here reaches a fresh database, or a host that cannot reach gtx, with the seeds."""
    total = {"inserted" : 0, "skipped" : 0}
    for path in sorted(directory.glob("*.jsonl")) :
        result = import_jsonl(conn, path.read_text(encoding = "utf-8"))
        total["inserted"] += result["inserted"]
        total["skipped"] += result["skipped"]
    return total
