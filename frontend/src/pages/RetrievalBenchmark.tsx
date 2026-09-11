import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiRequestError } from "../api/base";
import {
  R_AT_CUTS,
  cancelRun,
  createRun,
  getRun,
  getRunResult,
  getRunResults,
  listDatasets,
  listRuns,
  listTranslationPolicies,
  resumeRun,
} from "../api/retrievalBenchmark";
import type {
  BenchmarkRun,
  Dataset,
  IntervalMetrics,
  QueryResult,
  QueryResultDetail,
  RAt,
  RunHeadline,
  RunStatus,
  TaskType,
  TranslationPolicy,
  VideoMetrics,
} from "../api/retrievalBenchmark";
import Button from "../components/Button";
import RetrievalBenchmarkDetail from "../components/RetrievalBenchmarkDetail";

const POLL_MS = 2500;

const ACTIVE_STATUSES = new Set<RunStatus>(["queued", "running", "cancelling"]);
const RESUMABLE_STATUSES = new Set<RunStatus>([
  "partial",
  "failed",
  "cancelled",
  "interrupted",
]);

type ResultFilter =
  | "all"
  | "video-miss"
  | "interval-miss"
  | "video-hit-interval-miss"
  | "failed"
  | "has-note";

function errorMessage(error: unknown): string {
  return error instanceof ApiRequestError ? error.message : "Benchmark request failed";
}

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function seconds(ms: number | null): string {
  return ms === null ? "—" : `${(ms / 1000).toFixed(2)}s`;
}

function score(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toFixed(3);
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

function policyLabel(id: string | null | undefined, policies: TranslationPolicy[]): string {
  if (!id) return "Not recorded";
  return policies.find((policy) => policy.id === id)?.label ?? id;
}

function configFingerprint(run: BenchmarkRun): string {
  const config = run.configuration ?? {};
  return JSON.stringify({
    translator: run.translator,
    models: config.models,
    top_k: config.top_k,
    top_m: config.top_m,
    use_rerank: config.use_rerank,
    translation_policy: config.translation_policy,
  });
}

// ── small presentational pieces ────────────────────────────────────────────

function StatusBadge({ status }: { status: RunStatus }) {
  const tone: Record<string, string> = {
    completed: "bg-[#3d7a4d]/10 text-[#3d7a4d]",
    running: "bg-proto-teal/15 text-[#317d6e]",
    queued: "bg-proto-soft text-proto-muted",
    partial: "bg-[#d4a017]/20 text-[#8a6a0f]",
    cancelling: "bg-[#d4a017]/20 text-[#8a6a0f]",
    cancelled: "bg-proto-card text-proto-muted",
    interrupted: "bg-[#d4a017]/20 text-[#8a6a0f]",
    failed: "bg-[#c64545]/10 text-[#c64545]",
  };
  return (
    <span
      className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full uppercase tracking-wide ${
        tone[status] ?? "bg-proto-card text-proto-muted"
      }`}
    >
      {status}
    </span>
  );
}

function Metric({
  label,
  value,
  sub,
  primary = false,
}: {
  label: string;
  value: string;
  sub?: string;
  primary?: boolean;
}) {
  return (
    <div className="border border-proto-line rounded-[10px] bg-white p-3.5 min-h-[96px]">
      <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">{label}</div>
      <div
        className={`font-mono font-bold text-proto-ink leading-none mt-2.5 ${
          primary ? "text-[26px]" : "text-[22px]"
        }`}
      >
        {value}
      </div>
      {sub && <div className="text-[11px] font-mono text-proto-muted mt-1.5">{sub}</div>}
    </div>
  );
}

function RAtRow({ label, rAt }: { label: string; rAt: RAt }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[12px]">
      <span className="text-proto-muted uppercase text-[10px] font-bold tracking-wide">{label}</span>
      {R_AT_CUTS.map((cut) => (
        <span key={cut} className="font-mono">
          R@{cut} <b className="text-proto-ink">{pct(rAt[String(cut)] ?? 0)}</b>
        </span>
      ))}
    </div>
  );
}

function VideoBlock({ video }: { video: VideoMetrics }) {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-[12px] font-mono">
      <span>
        Hit@1 <b className="text-proto-ink">{pct(video.hit_at_1)}</b>
      </span>
      <span>
        R@3 <b className="text-proto-ink">{pct(video.recall_at_3)}</b>
      </span>
      <span>
        R@5 <b className="text-proto-ink">{pct(video.recall_at_5)}</b>
      </span>
      <span>
        R@10 <b className="text-proto-ink">{pct(video.recall_at_10)}</b>
      </span>
      <span>
        MRR <b className="text-proto-ink">{video.mrr.toFixed(3)}</b>
      </span>
      <span className="text-proto-muted">
        median rank {video.median_reference_rank ?? "—"}
      </span>
    </div>
  );
}

function IntervalBlock({ interval }: { interval: IntervalMetrics }) {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-[12px] font-mono">
      <span>
        Final <b className="text-proto-ink">{score(interval.final_score)}</b>
      </span>
      <span>
        interval-hit <b className="text-proto-ink">{pct(interval.interval_hit_rate)}</b>
      </span>
      <span className="text-[#c64545]">
        video-hit / interval-miss <b>{interval.video_hit_interval_miss}</b>
      </span>
    </div>
  );
}

// ── report sections ───────────────────────────────────────────────────────

function CaveatsBlock({ staleFiles }: { staleFiles: string[] }) {
  return (
    <div className="border border-proto-line rounded-[10px] bg-white px-4 py-3 text-[12px] text-proto-body space-y-1.5">
      {staleFiles.length > 0 && (
        <div className="rounded-[8px] border border-[#c64545]/30 bg-[#c64545]/5 px-3 py-2 text-[#c64545]">
          <b>Index was stale at run start.</b> These files changed on disk without a
          restart, so the numbers may not reflect current retrieval:{" "}
          <span className="font-mono">{staleFiles.join(", ")}</span>
        </div>
      )}
      <p className="m-0">
        <b>QA</b> queries are scored on video + frame-interval only. Answer text is
        never checked.
      </p>
      <p className="m-0">
        <b>TRAKE</b> queries are Tier 0: target-video ranking only. Per-event frames
        are not scored.
      </p>
      <p className="m-0">
        Translations are captured per run, not frozen across runs — re-running the
        same policy can yield slightly different English.
      </p>
      <p className="m-0 text-proto-muted">
        A benchmark run shares the live backend process with competition search.
        Don't start one during a live round.
      </p>
    </div>
  );
}

function HeadlineStrip({ headline }: { headline: RunHeadline }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-3 min-[1050px]:grid-cols-6 gap-3">
        <Metric
          label="Final Score · KIS+QA"
          value={score(headline.final_score_kis_qa)}
          sub={`${headline.scored_queries} scored`}
          primary
        />
        <Metric
          label="Final Score · KIS only"
          value={score(headline.final_score_kis)}
          sub="QA excluded"
          primary
        />
        <Metric label="R@1" value={pct(headline.r_at_kis_qa["1"] ?? 0)} sub="KIS+QA" />
        <Metric label="R@5" value={pct(headline.r_at_kis_qa["5"] ?? 0)} sub="KIS+QA" />
        <Metric label="R@20" value={pct(headline.r_at_kis_qa["20"] ?? 0)} sub="KIS+QA" />
        <Metric
          label="Interval hit"
          value={pct(headline.interval.interval_hit_rate)}
          sub={`${headline.interval.video_hit_interval_miss} video-hit / interval-miss`}
        />
      </div>

      <div className="border border-proto-line rounded-[10px] bg-white px-4 py-3 space-y-2">
        <RAtRow label="R@k · KIS+QA" rAt={headline.r_at_kis_qa} />
        <RAtRow label="R@k · KIS only" rAt={headline.r_at_kis} />
        <div className="pt-2 border-t border-proto-line">
          <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-1">
            Video level — did we find the right video at all
          </div>
          <VideoBlock video={headline.video} />
        </div>
        <div className="pt-2 border-t border-proto-line flex flex-wrap gap-x-3 gap-y-1 text-[12px] font-mono text-proto-muted">
          <span>
            P50 <b className="text-proto-ink">{seconds(headline.latency.p50_ms)}</b>
          </span>
          <span>
            P95 <b className="text-proto-ink">{seconds(headline.latency.p95_ms)}</b>
          </span>
          <span>
            Max <b className="text-proto-ink">{seconds(headline.latency.max_ms)}</b>
          </span>
          <span>
            ≤10s <b className="text-proto-ink">{pct(headline.latency.within_10s_rate)}</b>
          </span>
        </div>
      </div>
    </div>
  );
}

function TaskTypeCards({ run }: { run: BenchmarkRun }) {
  const byType = run.task_type_summary;
  if (!byType) return null;
  return (
    <div className="grid gap-3 min-[900px]:grid-cols-3">
      {(["KIS", "QA"] as const).map((type) => {
        const block = byType[type];
        return (
          <div key={type} className="border border-proto-line rounded-[10px] bg-white p-3.5">
            <div className="text-[11px] font-bold uppercase tracking-wide text-proto-ink">
              {type}{" "}
              <span className="text-proto-muted font-normal">
                · {block.video.total} queries
              </span>
            </div>
            <div className="mt-2 space-y-1.5">
              <IntervalBlock interval={block.interval} />
              <VideoBlock video={block.video} />
            </div>
          </div>
        );
      })}
      <div className="border border-proto-line rounded-[10px] bg-white p-3.5">
        <div className="text-[11px] font-bold uppercase tracking-wide text-proto-ink">
          TRAKE{" "}
          <span className="text-proto-muted font-normal">
            · {byType.TRAKE.video.total} queries
          </span>
          <span className="ml-2 text-[9.5px] px-1.5 py-0.5 rounded-full bg-proto-cream-strong text-proto-ink">
            Tier 0 — video ranking only
          </span>
        </div>
        <div className="mt-2">
          <VideoBlock video={byType.TRAKE.video} />
        </div>
      </div>
    </div>
  );
}

function combinedFinal(a: BenchmarkRun, b: BenchmarkRun): number | null {
  if (!a.summary || !b.summary) return null;
  const totalScored = a.summary.scored_queries + b.summary.scored_queries;
  if (totalScored === 0) return 0;
  return (
    (a.summary.final_score_kis_qa * a.summary.scored_queries +
      b.summary.final_score_kis_qa * b.summary.scored_queries) /
    totalScored
  );
}

function CompareSection({
  runs,
  datasets,
}: {
  runs: BenchmarkRun[];
  datasets: Dataset[];
}) {
  const completed = runs.filter((run) => run.summary !== null);
  const [pickA, setPickA] = useState<number | null>(null);
  const [pickB, setPickB] = useState<number | null>(null);

  const slugs = useMemo(() => {
    const seen = new Map<string, string>();
    for (const dataset of datasets) seen.set(dataset.version, dataset.display_name);
    return seen;
  }, [datasets]);

  const versions = useMemo(
    () => Array.from(new Set(completed.map((run) => run.dataset_version))),
    [completed]
  );

  const defaultFor = useCallback(
    (version: string) => completed.find((run) => run.dataset_version === version)?.id ?? null,
    [completed]
  );

  const versionA = versions[0] ?? "";
  const versionB = versions[1] ?? "";
  const runA = completed.find((run) => run.id === (pickA ?? defaultFor(versionA))) ?? null;
  const runB = completed.find((run) => run.id === (pickB ?? defaultFor(versionB))) ?? null;

  if (versions.length < 2) {
    return (
      <p className="text-[12px] text-proto-muted m-0">
        Run a completed benchmark against a second dataset to compare.
      </p>
    );
  }

  const mismatch = runA && runB && configFingerprint(runA) !== configFingerprint(runB);
  const combined = runA && runB && !mismatch ? combinedFinal(runA, runB) : null;

  const runOptions = (version: string) =>
    completed
      .filter((run) => run.dataset_version === version)
      .map((run) => (
        <option key={run.id} value={run.id}>
          #{run.id} · {run.status} · {formatDate(run.created_at)}
        </option>
      ));

  return (
    <div className="space-y-3">
      <div className="grid gap-3 min-[900px]:grid-cols-2">
        {[
          { version: versionA, run: runA, pick: pickA, setPick: setPickA },
          { version: versionB, run: runB, pick: pickB, setPick: setPickB },
        ].map(({ version, run, pick, setPick }) => (
          <div key={version} className="border border-proto-line rounded-[10px] bg-white p-3.5">
            <div className="flex items-center gap-2 mb-2">
              <div className="text-[12px] font-semibold text-proto-ink">
                {slugs.get(version) ?? version}
              </div>
              <select
                className="ml-auto text-[11px] px-1.5 py-0.5 rounded-[6px] border border-proto-line bg-white"
                value={pick ?? defaultFor(version) ?? ""}
                onChange={(event) => setPick(Number(event.target.value))}
              >
                {runOptions(version)}
              </select>
            </div>
            {run?.summary ? (
              <div className="space-y-1.5">
                <div className="text-[13px] font-mono">
                  Final Score{" "}
                  <b className="text-proto-ink">{score(run.summary.final_score_kis_qa)}</b>{" "}
                  <span className="text-proto-muted">
                    (KIS {score(run.summary.final_score_kis)})
                  </span>
                </div>
                <IntervalBlock interval={run.summary.interval} />
                <VideoBlock video={run.summary.video} />
              </div>
            ) : (
              <p className="text-[12px] text-proto-muted m-0">No summary.</p>
            )}
          </div>
        ))}
      </div>

      {mismatch ? (
        <div className="rounded-[8px] border border-[#d4a017]/40 bg-[#d4a017]/10 px-3 py-2 text-[12px] text-[#7a5c0c]">
          The two runs used a different translation policy or model config, so a
          combined number would average incompatible measurements. Pick runs with
          matching config to see it.
        </div>
      ) : (
        <div className="border border-proto-line rounded-[10px] bg-white px-4 py-3 text-[13px]">
          Combined Final Score (KIS+QA, both datasets pooled){" "}
          <b className="font-mono text-proto-ink">{score(combined)}</b>
          <div className="text-[11px] text-proto-muted mt-1">
            A portfolio figure — Round 1 and Round 2 difficulty are not identical.
          </div>
        </div>
      )}
    </div>
  );
}

// ── page ──────────────────────────────────────────────────────────────────

export default function RetrievalBenchmark() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [policies, setPolicies] = useState<TranslationPolicy[]>([]);
  const [selectedPolicy, setSelectedPolicy] = useState("");
  const [runs, setRuns] = useState<BenchmarkRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [run, setRun] = useState<BenchmarkRun | null>(null);
  const [results, setResults] = useState<QueryResult[]>([]);
  const [selectedQueryKey, setSelectedQueryKey] = useState<string | null>(null);
  const [detail, setDetail] = useState<QueryResultDetail | null>(null);
  const [filter, setFilter] = useState<ResultFilter>("all");
  const [taskFilter, setTaskFilter] = useState<"all" | TaskType>("all");
  const [datasetVersion, setDatasetVersion] = useState("");
  const [referenceSetVersion, setReferenceSetVersion] = useState("");
  const [showCompare, setShowCompare] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const [datasetResponse, runResponse, policyResponse] = await Promise.all([
          listDatasets(),
          listRuns(),
          listTranslationPolicies(),
        ]);
        if (cancelled) return;
        setDatasets(datasetResponse.datasets);
        setPolicies(policyResponse.policies);
        setSelectedPolicy(policyResponse.default);
        setRuns(runResponse.runs);

        const latest = runResponse.runs[0] ?? null;
        const firstDataset = datasetResponse.datasets[0] ?? null;
        if (latest) {
          setSelectedRunId(latest.id);
          setDatasetVersion(latest.dataset_version);
          setReferenceSetVersion(latest.reference_set_version);
        } else if (firstDataset) {
          setDatasetVersion(firstDataset.version);
          setReferenceSetVersion(firstDataset.reference_sets[0]?.version ?? "");
        }
        setError(null);
      } catch (err) {
        if (!cancelled) setError(errorMessage(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const patchRun = useCallback((next: BenchmarkRun) => {
    setRuns((current) => {
      const exists = current.some((item) => item.id === next.id);
      const updated = exists
        ? current.map((item) => (item.id === next.id ? next : item))
        : [next, ...current];
      return updated.sort((a, b) => b.id - a.id);
    });
  }, []);

  const refreshRun = useCallback(async () => {
    if (selectedRunId === null) return;
    try {
      const [runResponse, resultResponse] = await Promise.all([
        getRun(selectedRunId),
        getRunResults(selectedRunId),
      ]);
      setRun(runResponse.run);
      setResults(resultResponse.results);
      patchRun(runResponse.run);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [patchRun, selectedRunId]);

  useEffect(() => {
    if (selectedRunId === null) {
      setRun(null);
      setResults([]);
      setSelectedQueryKey(null);
      return;
    }
    setSelectedQueryKey(null);
    void refreshRun();
  }, [refreshRun, selectedRunId]);

  const pollStatus = run?.status ?? null;
  useEffect(() => {
    if (run?.id !== selectedRunId || pollStatus === null || !ACTIVE_STATUSES.has(pollStatus)) {
      return;
    }
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      await refreshRun();
      if (!cancelled) timer = window.setTimeout(() => void poll(), POLL_MS);
    };
    timer = window.setTimeout(() => void poll(), POLL_MS);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [run?.id, pollStatus, refreshRun, selectedRunId]);

  useEffect(() => {
    if (selectedRunId === null || selectedQueryKey === null) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    void getRunResult(selectedRunId, selectedQueryKey)
      .then((response) => {
        if (!cancelled) setDetail(response.result);
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRunId, selectedQueryKey]);

  const selectedDataset = useMemo(
    () => datasets.find((dataset) => dataset.version === datasetVersion) ?? null,
    [datasetVersion, datasets]
  );

  const activeRun = runs.find((item) => ACTIVE_STATUSES.has(item.status)) ?? null;

  const startRun = async () => {
    if (!datasetVersion || !referenceSetVersion || !selectedPolicy) return;
    setBusy(true);
    try {
      const response = await createRun({
        dataset_version: datasetVersion,
        reference_set_version: referenceSetVersion,
        translation_policy: selectedPolicy,
      });
      patchRun(response.run);
      setRun(response.run);
      setResults([]);
      setSelectedRunId(response.run.id);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const doCancel = async () => {
    if (!run) return;
    setBusy(true);
    try {
      const response = await cancelRun(run.id);
      setRun(response.run);
      patchRun(response.run);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const doResume = async () => {
    if (!run) return;
    setBusy(true);
    try {
      const response = await resumeRun(run.id);
      setRun(response.run);
      patchRun(response.run);
      await refreshRun();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const filteredResults = useMemo(() => {
    return results.filter((result) => {
      if (taskFilter !== "all" && result.task_type !== taskFilter) return false;
      switch (filter) {
        case "video-miss":
          return result.status === "completed" && result.reference_video_rank === null;
        case "interval-miss":
          return result.status === "completed" && result.interval_hit === false;
        case "video-hit-interval-miss":
          return (
            result.status === "completed" &&
            result.reference_video_rank !== null &&
            result.interval_hit === false
          );
        case "failed":
          return result.status === "failed";
        case "has-note":
          return result.reference_notes.trim().length > 0;
        default:
          return true;
      }
    });
  }, [results, filter, taskFilter]);

  const downloadTable = (asJson: boolean) => {
    if (!run || results.length === 0) return;
    const rows = results.map((result) => ({
      query_key: result.query_key,
      ordinal: result.ordinal,
      task_type: result.task_type,
      status: result.status,
      reference_video: result.reference_video,
      video_rank: result.reference_video_rank,
      interval_hit: result.interval_hit,
      interval_rank: result.interval_rank,
      matched_interval: result.matched_interval_index,
      final_score: result.final_score,
      hit_at_1: result.hit_at_1,
      reciprocal_rank: result.reciprocal_rank,
      total_ms: result.total_ms,
      query_en: result.query_en,
      translator: result.translator,
      reference_notes: result.reference_notes,
    }));
    let blob: Blob;
    let name: string;
    if (asJson) {
      blob = new Blob([JSON.stringify({ run, results: rows }, null, 2)], {
        type: "application/json",
      });
      name = `benchmark-run-${run.id}.json`;
    } else {
      const headers = Object.keys(rows[0] ?? {});
      const escape = (value: unknown) => {
        const text = value === null || value === undefined ? "" : String(value);
        return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
      };
      const lines = [
        headers.join(","),
        ...rows.map((row) => headers.map((key) => escape((row as Record<string, unknown>)[key])).join(",")),
      ];
      blob = new Blob([lines.join("\n")], { type: "text/csv" });
      name = `benchmark-run-${run.id}.csv`;
    }
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = name;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="max-w-[1240px] mx-auto p-6 font-baloo">
        <h2 className="text-2xl text-proto-ink">Retrieval Benchmark</h2>
        <div className="mt-4 border border-proto-line rounded-[10px] bg-white p-4 text-sm text-proto-muted">
          Loading benchmark runs…
        </div>
      </div>
    );
  }

  const runtime = run?.runtime ?? null;
  const staleFiles = Array.isArray(runtime?.stale_files) ? (runtime?.stale_files as string[]) : [];
  const processed = run ? run.completed_count + run.failed_count : 0;
  const progress = run?.query_count ? Math.min(100, (processed / run.query_count) * 100) : 0;
  const canCancel = run?.status === "queued" || run?.status === "running";
  const canResume = !!run && RESUMABLE_STATUSES.has(run.status);
  const referenceSet = selectedDataset?.reference_sets.find(
    (reference) => reference.version === (run?.reference_set_version ?? referenceSetVersion)
  );

  return (
    <div className="max-w-[1240px] mx-auto p-6 font-baloo">
      <div className="flex items-start gap-4 mb-4 flex-wrap">
        <div>
          <h2 className="text-2xl text-proto-ink leading-tight">Retrieval Benchmark</h2>
          <p className="text-[12.5px] text-proto-muted mt-1 mb-0">
            Score the translated visual-ensemble pipeline against manually reviewed
            Round 1 / Round 2 references. Not the team answer-comparison tool.
          </p>
        </div>
        <label className="ml-auto flex items-center gap-2">
          <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
            Recent run
          </span>
          <select
            className="min-w-[210px] px-2 py-1 rounded-[7px] border border-proto-line bg-white text-[13px] text-proto-ink"
            value={selectedRunId ?? ""}
            disabled={runs.length === 0}
            onChange={(event) => setSelectedRunId(Number(event.target.value))}
          >
            {runs.length === 0 ? (
              <option value="">No runs yet</option>
            ) : (
              runs.map((item) => (
                <option key={item.id} value={item.id}>
                  #{item.id} · {item.dataset_version} · {item.status} ·{" "}
                  {formatDate(item.created_at)}
                </option>
              ))
            )}
          </select>
        </label>
      </div>

      {error && <p className="text-[#c64545] text-sm mb-3">{error}</p>}

      {/* run configuration / start */}
      <div className="border border-proto-line rounded-[10px] bg-white overflow-hidden mb-4">
        <div className="px-4 py-2 bg-proto-soft flex items-center gap-2">
          <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
            New run
          </span>
          {activeRun && (
            <span className="text-[11px] text-[#8a6a0f]">
              Run #{activeRun.id} is {activeRun.status} — one run at a time.
            </span>
          )}
        </div>
        <div className="p-4 grid gap-3 sm:grid-cols-3">
          <label>
            <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-1">
              Dataset
            </div>
            <select
              className="w-full px-2 py-1.5 rounded-[7px] border border-proto-line bg-white text-[13px]"
              value={datasetVersion}
              onChange={(event) => {
                const next = datasets.find((d) => d.version === event.target.value);
                setDatasetVersion(event.target.value);
                setReferenceSetVersion(next?.reference_sets[0]?.version ?? "");
              }}
            >
              {datasets.map((dataset) => (
                <option key={dataset.id} value={dataset.version}>
                  {dataset.display_name} ({dataset.query_count})
                </option>
              ))}
            </select>
          </label>
          <label>
            <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-1">
              Reference set
            </div>
            <select
              className="w-full px-2 py-1.5 rounded-[7px] border border-proto-line bg-white text-[13px]"
              value={referenceSetVersion}
              onChange={(event) => setReferenceSetVersion(event.target.value)}
            >
              {(selectedDataset?.reference_sets ?? []).map((reference) => (
                <option key={reference.id} value={reference.version}>
                  {reference.version}
                </option>
              ))}
            </select>
          </label>
          <label>
            <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-1">
              Translation policy
            </div>
            <select
              className="w-full px-2 py-1.5 rounded-[7px] border border-proto-line bg-white text-[13px]"
              value={selectedPolicy}
              onChange={(event) => setSelectedPolicy(event.target.value)}
            >
              {policies.map((policy) => (
                <option key={policy.id} value={policy.id}>
                  {policy.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="px-4 pb-4 flex items-center gap-2">
          <Button
            size="sm"
            onClick={() => void startRun()}
            loading={busy}
            disabled={!!activeRun || !datasetVersion || !referenceSetVersion}
          >
            Start run
          </Button>
          <span className="text-[11px] text-proto-muted">
            {policies.find((p) => p.id === selectedPolicy)?.description}
          </span>
        </div>
      </div>

      {run && (
        <div className="grid gap-4 min-[1100px]:grid-cols-[1fr_380px]">
          <div className="space-y-4 min-w-0">
            {/* metadata header */}
            <div className="border border-proto-line rounded-[10px] bg-white p-4">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-[12px] text-proto-muted">#{run.id}</span>
                <StatusBadge status={run.status} />
                <span className="text-[12px] text-proto-ink font-semibold">
                  {selectedDataset?.display_name ?? run.dataset_version}
                </span>
                <span className="text-[11px] font-mono text-proto-muted">
                  {run.dataset_version} / {run.reference_set_version}
                </span>
                {run.resume_count > 0 && (
                  <span className="text-[10px] text-proto-muted">· resumed ×{run.resume_count}</span>
                )}
                <span className="ml-auto flex gap-2">
                  {canCancel && (
                    <Button size="xs" variant="outline" onClick={() => void doCancel()} loading={busy}>
                      Cancel
                    </Button>
                  )}
                  {canResume && (
                    <Button size="xs" variant="outline" onClick={() => void doResume()} loading={busy}>
                      Resume
                    </Button>
                  )}
                </span>
              </div>

              {ACTIVE_STATUSES.has(run.status) && (
                <div className="mt-2 h-1.5 rounded-full bg-proto-soft overflow-hidden">
                  <div className="h-full bg-proto-primary" style={{ width: `${progress}%` }} />
                </div>
              )}

              <div className="mt-3 grid gap-x-6 gap-y-1 sm:grid-cols-2 text-[12px] text-proto-muted font-mono">
                <span>
                  policy ·{" "}
                  <b className="text-proto-ink">
                    {policyLabel(run.configuration?.translation_policy, policies)}
                  </b>
                </span>
                <span>
                  models · {(run.configuration?.models ?? []).join(", ") || "—"} · topK{" "}
                  {run.configuration?.top_k} · topM {run.configuration?.top_m}
                </span>
                <span>
                  build · {runtime?.version ?? "—"} @ {runtime?.commit ?? "—"}
                </span>
                <span>
                  {run.completed_count}/{run.query_count} done · {run.failed_count} failed
                </span>
              </div>
              {run.error && (
                <div className="mt-2 text-[12px] font-mono text-[#c64545]">{run.error}</div>
              )}
              {referenceSet?.label_semantics && (
                <p className="mt-3 mb-0 text-[11.5px] text-proto-muted italic leading-snug">
                  {referenceSet.label_semantics}
                </p>
              )}
            </div>

            <CaveatsBlock staleFiles={staleFiles} />

            {run.summary ? (
              <>
                <HeadlineStrip headline={run.summary} />
                <TaskTypeCards run={run} />
              </>
            ) : (
              <div className="border border-proto-line rounded-[10px] bg-white p-4 text-[12.5px] text-proto-muted">
                No summary yet — the run has not produced scored results.
              </div>
            )}

            <div className="border border-proto-line rounded-[10px] bg-white p-4">
              <div className="flex items-center gap-2 mb-2">
                <div className="text-[11px] font-bold uppercase tracking-wide text-proto-ink">
                  Compare datasets
                </div>
                <button
                  type="button"
                  className="text-[11px] underline text-proto-muted"
                  onClick={() => setShowCompare((value) => !value)}
                >
                  {showCompare ? "hide" : "show"}
                </button>
              </div>
              {showCompare && <CompareSection runs={runs} datasets={datasets} />}
            </div>

            {/* per-query table */}
            <div className="border border-proto-line rounded-[10px] bg-white overflow-hidden">
              <div className="px-4 py-2 bg-proto-soft flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
                  Per query
                </span>
                <select
                  className="text-[11px] px-1.5 py-0.5 rounded-[6px] border border-proto-line bg-white"
                  value={taskFilter}
                  onChange={(event) => setTaskFilter(event.target.value as "all" | TaskType)}
                >
                  <option value="all">all types</option>
                  <option value="KIS">KIS</option>
                  <option value="QA">QA</option>
                  <option value="TRAKE">TRAKE</option>
                </select>
                <select
                  className="text-[11px] px-1.5 py-0.5 rounded-[6px] border border-proto-line bg-white"
                  value={filter}
                  onChange={(event) => setFilter(event.target.value as ResultFilter)}
                >
                  <option value="all">all</option>
                  <option value="video-miss">video miss</option>
                  <option value="interval-miss">interval miss</option>
                  <option value="video-hit-interval-miss">video hit / interval miss</option>
                  <option value="failed">failed</option>
                  <option value="has-note">has note</option>
                </select>
                <span className="ml-auto flex gap-2">
                  <button
                    type="button"
                    className="text-[11px] underline text-proto-muted"
                    onClick={() => downloadTable(false)}
                  >
                    CSV
                  </button>
                  <button
                    type="button"
                    className="text-[11px] underline text-proto-muted"
                    onClick={() => downloadTable(true)}
                  >
                    JSON
                  </button>
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-[12px] border-collapse">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-wide text-proto-muted">
                      <th className="px-3 py-1.5 font-semibold">Query</th>
                      <th className="px-3 py-1.5 font-semibold">Type</th>
                      <th className="px-3 py-1.5 font-semibold">Video</th>
                      <th className="px-3 py-1.5 font-semibold">Interval</th>
                      <th className="px-3 py-1.5 font-semibold">R@1/5/20/50/100</th>
                      <th className="px-3 py-1.5 font-semibold">Final</th>
                      <th className="px-3 py-1.5 font-semibold">Total</th>
                      <th className="px-3 py-1.5 font-semibold">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredResults.map((result) => {
                      const selected = result.query_key === selectedQueryKey;
                      return (
                        <tr
                          key={result.query_key}
                          onClick={() => setSelectedQueryKey(result.query_key)}
                          className={`border-t border-proto-line cursor-pointer ${
                            selected ? "bg-proto-soft" : "hover:bg-proto-soft/50"
                          }`}
                        >
                          <td className="px-3 py-1.5 font-mono">
                            {result.query_key}
                            {result.reference_notes.trim() && (
                              <span
                                className="ml-1 text-[#8a6a0f]"
                                title={result.reference_notes}
                              >
                                ⚠
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-1.5">{result.task_type}</td>
                          <td className="px-3 py-1.5 font-mono">
                            {result.reference_video_rank === null ? (
                              <span className="text-proto-muted">—</span>
                            ) : (
                              `#${result.reference_video_rank}`
                            )}
                          </td>
                          <td className="px-3 py-1.5 font-mono">
                            {result.task_type === "TRAKE" ? (
                              <span className="text-proto-muted">tier 0</span>
                            ) : result.interval_rank === null ? (
                              <span className="text-proto-muted">miss</span>
                            ) : (
                              <span className="text-[#3d7a4d]">
                                #{result.interval_rank}
                                {result.matched_interval_index !== null &&
                                  ` (iv ${result.matched_interval_index + 1})`}
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-1.5 font-mono">
                            {result.task_type === "TRAKE"
                              ? "—"
                              : R_AT_CUTS.map((cut) =>
                                  result.interval_rank !== null && result.interval_rank <= cut
                                    ? "✓"
                                    : "×"
                                ).join(" ")}
                          </td>
                          <td className="px-3 py-1.5 font-mono">
                            {result.task_type === "TRAKE" ? "—" : score(result.final_score)}
                          </td>
                          <td className="px-3 py-1.5 font-mono">{seconds(result.total_ms)}</td>
                          <td className="px-3 py-1.5">
                            {result.status === "failed" ? (
                              <span className="text-[#c64545]">failed</span>
                            ) : (
                              result.status
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {filteredResults.length === 0 && (
                <p className="px-4 py-3 text-[12px] text-proto-muted m-0">No matching queries.</p>
              )}
            </div>
          </div>

          <RetrievalBenchmarkDetail
            result={detail}
            translationPolicyLabel={policyLabel(run.configuration?.translation_policy, policies)}
          />
        </div>
      )}
    </div>
  );
}
