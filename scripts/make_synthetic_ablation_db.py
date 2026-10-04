# scripts/make_synthetic_ablation_db.py
"""Build a SYNTHETIC ablation run folder, so the analysis can be developed and tested without EC2.

The real suite machinery runs on a fake corpus: suite.create_suite, runner.process_run, the real
shared_search memo and the real preprocess._merge_ensemble over fake per-model searches. So the
database has exactly the structure and the stored fields of a real run (routes, ranked videos, model
timings, interval gap, TRAKE discovery). Only the numbers are invented: ranks come from a latent
difficulty per query, a skill per encoder, an offset per prefix and per text policy, plus noise.

NOTHING HERE IS A RESULT. The folder is marked "synthetic" : true in provenance.json and the analysis
writes its output to a folder named analysis_SYNTHETIC and stamps every table and figure.

Written to <out>/:
    ablation.db, suite.json, provenance.json, run.log-less, features/ (videos.csv, shots.csv,
    frames_ref.csv, index_files.csv, corpus_totals.json, all synthetic)

Needs the backend environment (the same one the tests use: torch and faiss are imported by
app.preprocess, whose search functions are replaced here).

    python scripts/make_synthetic_ablation_db.py --out synthetic_run
    python scripts/make_synthetic_ablation_db.py --out smoke_run --limit-queries 3
"""
from __future__ import annotations

import argparse
import csv
import functools
import hashlib
import json
import math
import random
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

if hasattr(sys.stdout, "reconfigure") :
    sys.stdout.reconfigure(encoding = "utf-8")

SEED = 20261004
DATASETS = ("round1-v3", "round2-v2", "round3-v2", "final-v1")
SKILL = {"beit3" : 0.0, "clip" : 0.25, "siglip2" : 0.45}
PREFIX_OFFSET = {"L" : 0.0, "M" : -0.35, "N" : -0.7, "S" : -0.55}
SLEEP_S = {"beit3" : 0.004, "clip" : 0.012, "siglip2" : 0.008}   # fake per-model search cost, only so timings are not all zero
PREFIX_COUNTS = {"L" : 70, "M" : 40, "N" : 24, "S" : 12}


def sigmoid(x : float) -> float :
    return 1.0 / (1.0 + math.exp(-x))


def rng_for(*parts) -> random.Random :
    return random.Random("|".join(str(p) for p in (SEED, *parts)))


# ─── corpus ────────────────────────────────────────────────────────────────

def video_id(prefix : str, series : int, number : int) -> str :
    """L and M ids use an underscore, N and S a hyphen, as in the real data."""
    sep = "_" if prefix in "LM" else "-"
    width = 3 if prefix == "N" else 2
    return f"{prefix}{series:0{width}d}{sep}V{number:03d}"


def make_corpus(references : dict[str, list[int]]) -> dict[str, dict] :
    """{video: {"prefix", "fps", "shots": [(shot, [frame_idx, ...])]}}. Every reference video is in it and
    long enough to hold its intervals; shot keyframe counts follow n(T) = min(40, 2 + ceil(max(0, T - 1.67) / 2))
    most of the time and fewer otherwise, so the sampling analysis has something to measure."""
    rng = rng_for("corpus")
    corpus : dict[str, dict] = {}
    wanted = set(references)
    for prefix, count in PREFIX_COUNTS.items() :
        have = [v for v in wanted if v[0] == prefix]
        extra = [video_id(prefix, 1 + i // 12, 1 + i % 12) for i in range(count)]
        wanted.update(extra[ : max(0, count - len(have))])
    for video in sorted(wanted) :
        prefix = video[0]
        fps = rng.choice([25.0, 25.0, 30.0, 29.97]) if prefix != "N" else rng.choice([25.0, 29.97, 30.0])
        need = max(references.get(video, [0]) + [0]) + 3000
        frames_total = max(rng.randint(15000, 70000), int(need * 1.1))
        shots, cursor, shot = [], 0, 0
        while cursor < frames_total :
            seconds = max(0.4, rng.lognormvariate(1.0, 0.9))
            n = min(40, 2 + math.ceil(max(0.0, seconds - 1.67) / 2))
            if (rng.random() < 0.12) :
                n = max(1, n - rng.randint(1, 3))
            length = int(seconds * fps)
            step = max(1, length // n)
            shots.append((shot, [cursor + 3 + i * step for i in range(n) if cursor + 3 + i * step < frames_total]))
            cursor += length
            shot += 1
        corpus[video] = {"prefix" : prefix, "fps" : fps, "shots" : [s for s in shots if s[1]]}
    return corpus


def all_frames(video : dict) -> list[tuple[int, int]] :
    return [(shot, idx) for shot, frames in video["shots"] for idx in frames]


# ─── query contexts: what the fake search needs to know about a text ───────

class Context :
    def __init__(self, dataset : str, key : str, task : str, video : str, intervals : list[tuple[int, int]], event : bool = False, raw : bool = False, expand : bool = False) :
        self.dataset, self.key, self.task, self.video, self.intervals, self.event, self.raw, self.expand = dataset, key, task, video, intervals, event, raw, expand
        self.prefix = video[0]


def expand_text(label : str) -> str :
    """A synthetic Expand text whose length varies (20 to 79 words) so the truncation analysis has something to see."""
    words = 20 + (int(hashlib.sha256(label.encode("utf-8")).hexdigest(), 16) % 60)
    return f"EXP::{label} " + " ".join(f"w{i}" for i in range(words))


def load_contexts(conn) -> tuple[dict[str, Context], dict[str, Context]] :
    """{searched text: Context} for the three text variants a query is searched with, and {query key: Context}."""
    from app.evaluation import text_cache

    by_text : dict[str, Context] = {}
    by_key : dict[str, Context] = {}
    for dataset in DATASETS :
        for row in text_cache.query_rows(conn, dataset) :
            intervals = [(int(i["start"]), int(i["end"])) for i in json.loads(row["valid_intervals_json"] or "[]")]
            ctx = Context(dataset, row["query_key"], row["task_type"], row["video_id"], intervals)
            by_key[row["query_key"]] = ctx
            by_text[f"EN::{row['query_key']}"] = ctx
            by_text[expand_text(row["query_key"])] = Context(dataset, row["query_key"], row["task_type"], row["video_id"], intervals, expand = True)
            by_text[row["query_vi"]] = Context(dataset, row["query_key"], row["task_type"], row["video_id"], intervals, raw = True)
            for event in json.loads(row["trake_events_json"] or "[]") :
                by_text[f"EN::{event['description_vi']}"] = Context(dataset, row["query_key"], row["task_type"], row["video_id"], [], event = True)
                by_text[expand_text(event["description_vi"])] = Context(dataset, row["query_key"], row["task_type"], row["video_id"], [], event = True, expand = True)
    return by_text, by_key


# ─── fake retrieval ────────────────────────────────────────────────────────

class FakeSearch :
    def __init__(self, corpus : dict[str, dict], contexts : dict[str, Context]) :
        self.corpus, self.contexts = corpus, contexts
        self.videos = sorted(corpus)
        self.frames = {v : all_frames(c) for v, c in corpus.items()}

    def latent(self, model : str, text : str, ctx : Context) -> float :
        """Skill of the model on this query: higher is easier. Difficulty is shared by every model and text."""
        difficulty = rng_for("difficulty", ctx.key).gauss(0, 1)
        noise = rng_for("noise", model, text).gauss(0, 1)
        return SKILL[model] + PREFIX_OFFSET[ctx.prefix] - 0.9 * difficulty + 0.7 * noise - (0.8 if ctx.raw else 0.0) - (0.3 if ctx.event else 0.0) + (0.25 if ctx.expand else 0.0)

    def reference_frame(self, rng : random.Random, ctx : Context, s : float) -> tuple[str, int, int] :
        """A keyframe of the reference video: inside a valid interval with probability rising in s, else near it."""
        video = self.corpus[ctx.video]
        frames = self.frames[ctx.video]
        if (ctx.intervals and rng.random() < sigmoid(s + 0.2)) :
            lo, hi = rng.choice(ctx.intervals)
            inside = [f for f in frames if lo <= f[1] <= hi]
            if (inside) :
                shot, idx = rng.choice(inside)
                return ctx.video, shot, idx
        centre = rng.choice(ctx.intervals)[0] if ctx.intervals else rng.choice(frames)[1]
        seconds = rng.choice([rng.uniform(0, 5), rng.uniform(5, 30), rng.uniform(30, 300)])
        target = centre + int(seconds * video["fps"] * rng.choice([-1, 1]))
        shot, idx = min(frames, key = lambda f : abs(f[1] - target))
        return ctx.video, shot, idx

    def distractor(self, rng : random.Random, ctx : Context, previous : str | None) -> tuple[str, int, int] :
        if (previous and rng.random() < 0.45) :
            video = previous
        elif (rng.random() < 0.25) :
            series = ctx.video.split("_")[0].split("-")[0]
            video = rng.choice([v for v in self.videos if v.startswith(series) and v != ctx.video] or self.videos)
        else :
            pool = [v for v in self.videos if v != ctx.video]
            video = rng.choice([v for v in pool if v[0] == ctx.prefix] if rng.random() < 0.4 else pool)
        shot, idx = rng.choice(self.frames[video])
        return video, shot, idx

    def search_one(self, model : str, text : str, top_m : int) -> list[dict] :
        time.sleep(SLEEP_S[model] * (0.8 + 0.4 * rng_for("sleep", model, text).random()))
        ctx = self.contexts.get(text)
        rng = rng_for("search", model, text)
        position = None
        if (ctx is not None) :
            s = self.latent(model, text, ctx)
            if (rng.random() < sigmoid(s + 0.3)) :
                position = 1 + int((top_m - 1) * rng.random() ** (1 + 2.5 * sigmoid(s)))
        hits, previous = [], None
        for i in range(top_m) :
            if (ctx is not None and position == i + 1) :
                video, shot, idx = self.reference_frame(rng, ctx, s)
            elif (ctx is not None and position is not None and i > position and rng.random() < 0.05) :
                video, shot, idx = self.reference_frame(rng, ctx, s)
            else :
                video, shot, idx = self.distractor(rng, ctx or Context("", "", "KIS", self.videos[0], []), previous)
            previous = video
            score = 0.38 - 0.0035 * i + rng.gauss(0, 0.004)
            hits.append({
                "name" : f"{video}-{shot:04d}-{idx}.jpg", "faiss_id" : i, "score" : score, "raw_score" : score,
                "video" : video, "frame_idx" : idx, "timestamp" : "",
            })
        seen, unique = set(), []
        for hit in hits :
            if (hit["name"] not in seen) :
                seen.add(hit["name"])
                unique.append(hit)
        unique.sort(key = lambda h : -h["score"])
        return unique

    def rerank(self, hits : list[dict], text : str, model : str) -> list[dict] :
        """Neighbour scores that depend on the frame name only (as the real function does), with the
        reference video's frames moved up or down by a latent effect of this (model, query)."""
        time.sleep(0.006)
        ctx = self.contexts.get(text)
        effect = 0.25 * math.tanh(rng_for("rr", model, ctx.key if ctx else text).gauss(0.15, 1.0))
        for hit in hits :
            base = 5 * (0.15 + 0.2 * rng_for("nb", model, text, hit["name"]).random())
            is_ref = ctx is not None and hit["video"] == ctx.video
            hit["score"] = base * (1 + effect) + (0.35 if is_ref else 0.0)
            hit["n_neighbors"] = 5
        hits.sort(key = lambda h : -h["score"])
        return hits


def fake_trake(fake : FakeSearch, discovery_info, event_texts, top_m, top_videos, gap_c, min_score, model_name) :
    """Chains for the shortlisted videos, built from the same shortlist rule the discovery rebuild uses so
    the two agree. The reference video has a feasible chain most of the time, its frames near the labels."""
    ctx = fake.contexts[event_texts[0]]
    info = discovery_info(event_texts, ctx.video, top_m, top_videos, [])
    rng = rng_for("trake", ctx.key)
    chains = []
    for video in info["shortlist_videos"] :
        if (rng.random() > (0.8 if video == ctx.video else 0.85)) :
            continue
        frames = fake.frames[video]
        events = []
        for i, _ in enumerate(event_texts) :
            if (video == ctx.video and rng.random() < 0.6 and ctx.key in TRAKE_TRUTH) :
                target = TRAKE_TRUTH[ctx.key][i] + int(rng.gauss(0, 90))
                shot, idx = min(frames, key = lambda f : abs(f[1] - target))
            else :
                shot, idx = rng.choice(frames)
            events.append({"name" : f"{video}-{shot:04d}-{idx}.jpg", "frame_idx" : idx, "score" : round(rng.uniform(20, 40), 2)})
        chains.append({"video" : video, "events" : events, "combined_score" : rng.uniform(0.1, 0.4) + (0.1 if video == ctx.video else 0.0)})
    chains.sort(key = lambda c : -c["combined_score"])
    return chains


TRAKE_TRUTH : dict[str, list[int]] = {}


# ─── synthetic OCR / ASR annotation (patched into text_measures) ───────────

def fake_annotate_block(frame_results, terms, variant, reference_video, valid_intervals, reference_rank, asr_mode = "substring", memo = None) :
    sources = ("ocr", "asr") if variant == "both" else (variant,)
    used = {s : terms.get(s, [])[ : 5] for s in sources}
    if (not any(used.values())) :
        return None
    rng = rng_for("annotate", reference_video, variant, "|".join(sum(used.values(), [])))
    chance = {"ocr" : 0.5, "asr" : 0.3, "both" : 0.62}[variant] * (1.0 if reference_video[0] == "L" else 0.4)
    flagged = rng.random() < chance
    videos = {f["video"] for f in frame_results}
    n_flagged = rng.randint(0, 6) + int(flagged)
    # The strict rule can only flag fewer videos than the OR rule; a single-term cue is the same either way.
    multi = any(len(t) > 1 for t in used.values())
    strict_flagged = flagged and (not multi or rng.random() < 0.6)
    return {
        "terms" : used, "ref_flagged" : flagged, "ref_location" : rng.choice(["here", "elsewhere"]) if flagged else "none",
        "ref_in_interval" : (rng.random() < 0.5) if (flagged and valid_intervals is not None) else None,
        "n_flagged" : n_flagged, "n_videos" : len(videos), "ref_rank" : reference_rank,
        "strict" : {"ref_flagged" : strict_flagged, "n_flagged" : n_flagged if not multi else max(int(strict_flagged), n_flagged // 3)},
    }


def fake_text_coverage(corpus : dict[str, dict], video_id_ : str, errors = None) -> dict :
    frames = sum(len(f) for _s, f in corpus[video_id_]["shots"]) if video_id_ in corpus else 0
    rng = rng_for("coverage", video_id_)
    share = {"L" : 0.5, "M" : 0.25, "N" : 0.0, "S" : 0.0}[video_id_[0]]
    return {"keyframes" : frames, "ocr" : int(frames * share * rng.uniform(0.8, 1.0)), "asr" : int(frames * min(1.0, share * 3) * rng.uniform(0.8, 1.0))}


# ─── features written next to the database ─────────────────────────────────

def write_features(out : Path, corpus : dict[str, dict], references : set[str]) -> None :
    out.mkdir(parents = True, exist_ok = True)
    videos, shots, refs = [], [], []
    for video, c in sorted(corpus.items()) :
        fps = c["fps"]
        n_frames = sum(len(f) for _s, f in c["shots"])
        last = c["shots"][-1][1][-1]
        # Like the real metadata: M, N and S carry stored neighbour links, and an L video has them all or none (about a quarter do).
        share = 1.0 if (c["prefix"] != "L" or int(hashlib.sha256(video.encode("utf-8")).hexdigest(), 16) % 4 == 0) else 0.0
        videos.append({"video" : video, "prefix" : c["prefix"], "n_keyframes" : n_frames, "n_shots" : len(c["shots"]), "fps" : fps,
                       "fps_varies" : int(c["prefix"] == "N" and fps != 25.0), "fps_map" : fps, "first_frame" : c["shots"][0][1][0],
                       "last_frame" : last, "duration_s" : round(last / fps, 2), "last_timestamp_s" : round(last / fps, 2),
                       "n_with_links" : int(share * n_frames), "share_with_links" : share})
        for index, (shot, frames) in enumerate(c["shots"]) :
            nxt = c["shots"][index + 1][1][0] if index + 1 < len(c["shots"]) else frames[-1]
            shots.append({"video" : video, "shot" : shot, "n_keyframes" : len(frames), "first_frame" : frames[0], "last_frame" : frames[-1],
                          "span_s" : round((frames[-1] - frames[0]) / fps, 3), "duration_est_s" : round((nxt - frames[0]) / fps, 3)})
            if (video in references) :
                refs.extend({"video" : video, "name" : f"{video}-{shot:04d}-{f}.jpg", "shot" : shot, "frame_idx" : f} for f in frames)
    for name, rows in (("videos.csv", videos), ("shots.csv", shots), ("frames_ref.csv", refs)) :
        with open(out / name, "w", encoding = "utf-8", newline = "") as handle :
            writer = csv.DictWriter(handle, fieldnames = list(rows[0]), lineterminator = "\n")
            writer.writeheader()
            writer.writerows(rows)
    (out / "index_files.csv").write_text("name,bytes\nbeit3.index,1000000\nclip.index,1000000\nsiglip2_giant.index,1000000\n", encoding = "utf-8")
    totals = {"all" : {"videos" : len(videos), "keyframes" : sum(v["n_keyframes"] for v in videos), "shots" : len(shots)}}
    (out / "corpus_totals.json").write_text(json.dumps({"synthetic" : True, "totals" : totals, "disagreements" : {}}, indent = 1), encoding = "utf-8")


# ─── main ──────────────────────────────────────────────────────────────────

def main() -> int :
    parser = argparse.ArgumentParser(description = __doc__.split("\n")[0])
    parser.add_argument("--out", required = True, help = "run folder to create")
    parser.add_argument("--limit-queries", type = int, default = None, help = "first N queries of each dataset (makes it a smoke-style folder)")
    parser.add_argument("--presets", default = "core2")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents = True, exist_ok = True)
    started = datetime.now()

    from app import preprocess
    from app.db.connection import get_conn
    from app.db.migrate import migrate
    from app.evaluation import coverage, runner, shared_search, text_cache, text_measures, trake
    from app.evaluation.presets import preset_configs
    from app.evaluation.runner import _db_path_env, process_run
    from app.evaluation.seed import import_all_seeds
    from app.evaluation.suite import create_suite, run_suite, suite_runs

    with _db_path_env(out / "ablation.db") :
        conn = get_conn()
        migrate(conn)
        import_all_seeds(conn)
        by_text, by_key = load_contexts(conn)

        references : dict[str, list[int]] = {}
        for ctx in by_key.values() :
            references.setdefault(ctx.video, []).extend(i for pair in ctx.intervals for i in pair)
        for dataset in DATASETS :
            for row in text_cache.query_rows(conn, dataset) :
                events = json.loads(row["trake_events_json"] or "[]")
                if (events) :
                    TRAKE_TRUTH[row["query_key"]] = [e["reference_frame_idx"] or 0 for e in events]
                    references.setdefault(row["video_id"], []).extend(TRAKE_TRUTH[row["query_key"]])
        corpus = make_corpus(references)
        fake = FakeSearch(corpus, by_text)

        # The text every policy needs, so replay never touches a provider: gtx for each query and each event.
        for dataset in DATASETS :
            for row in text_cache.query_rows(conn, dataset) :
                texts = [(row["query_vi"], f"EN::{row['query_key']}")]
                texts += [(e["description_vi"], f"EN::{e['description_vi']}") for e in json.loads(row["trake_events_json"] or "[]")]
                for vi, en in texts :
                    text_cache.store(conn, text_cache.make_key("translate_gtx", vi, ""), vi, {"text" : en}, "google_gtx")
                # The Expand text of the query and of each TRAKE event (task type of the row, as the runner asks for it).
                labels = [(row["query_vi"], row["query_key"])] + [(e["description_vi"], e["description_vi"]) for e in json.loads(row["trake_events_json"] or "[]")]
                for vi, label in labels :
                    output = {"eng_query" : expand_text(label), "check_units" : ["a unit", "another unit"], "translated_query" : None}
                    text_cache.store(conn, text_cache.make_key("expand_gemini", vi, row["task_type"]), vi, output, "gemini")

        patches = [
            (preprocess, "_load_indexes", lambda : None), (preprocess, "_load_meta", lambda : None),
            (preprocess, "_search_one", fake.search_one), (preprocess, "rerank_one_model", fake.rerank),
            (preprocess, "_image_url", lambda name : f"img/{name}"), (preprocess, "_has_image", lambda name : True),
            (preprocess, "fps_for_video", lambda video : corpus[video]["fps"] if video in corpus else 25.0),
            (preprocess, "trake_search_candidates", functools.partial(fake_trake, fake, trake.discovery_info)),
            (text_measures, "annotate_block", fake_annotate_block),
            (text_measures, "load_text_artifacts", lambda : {s : {"ready" : True, "entries" : 1, "path" : "synthetic", "error" : None} for s in ("ocr", "asr")}),
            (text_measures, "coverage_for_video", lambda video, errors = None : fake_text_coverage(corpus, video, errors)),
            (runner, "video_coverage", lambda video : {m : 1.0 for m in preprocess.MODEL_NAMES}),
            (coverage, "index_coverage", lambda : {"metadata_frames" : 0, "synthetic" : True, "models" : {}}),
        ]
        # trake_search_candidates is called positionally by name in trake.py; adapt the partial's signature.
        original = [(obj, name, getattr(obj, name)) for obj, name, _new in patches]
        for obj, name, new in patches :
            setattr(obj, name, new)
        try :
            configs = preset_configs(args.presets)
            for config in configs :
                config.subset.limit_queries = args.limit_queries
            created = create_suite(conn, f"synthetic-{started:%Y%m%d-%H%M%S}", configs, list(DATASETS))
            shared_search.clear_memo()
            run_suite(conn, created["suite_id"], functools.partial(process_run, runtime_snapshot_fn = lambda : {"device" : "test", "synthetic" : True}))
            runs = suite_runs(conn, created["suite_id"])
        finally :
            for obj, name, old in original :
                setattr(obj, name, old)

        (out / "suite.json").write_text(json.dumps({
            "suite_id" : created["suite_id"], "preset" : args.presets, "datasets" : list(DATASETS), "limit_queries" : args.limit_queries,
            "started_at" : started.isoformat(), "verify" : {"skipped" : True, "synthetic" : True},
        }, indent = 1), encoding = "utf-8")
        (out / "provenance.json").write_text(json.dumps({
            "synthetic" : True, "started_at" : started.isoformat(), "finished_at" : datetime.now().isoformat(),
            "argv" : sys.argv, "preset" : args.presets, "datasets" : list(DATASETS), "limit_queries" : args.limit_queries,
            "commit_full" : "synthetic", "version" : "synthetic", "host" : "synthetic", "gemini_key_configured" : False,
            "verify_shared_search" : {"skipped" : True, "synthetic" : True},
            "runs" : [{"id" : r["id"], "config_name" : r["configuration"].get("config_name"), "dataset" : r["dataset_version"], "status" : r["status"],
                       "completed" : r["completed_count"], "failed" : r["failed_count"], "config_hash" : r["configuration"].get("config_hash"),
                       "config" : r["configuration"].get("config")} for r in runs],
            "runtime_first_run" : runs[0]["runtime"] if runs else None,
        }, indent = 1), encoding = "utf-8")
        statuses = sorted({r["status"] for r in runs})
        conn.close()

    write_features(out / "features", corpus, set(references))
    print(f"synthetic run folder {out}: {len(runs)} runs, statuses {statuses}")
    return 0 if statuses == ["completed"] else 1


if (__name__ == "__main__") :
    raise SystemExit(main())
