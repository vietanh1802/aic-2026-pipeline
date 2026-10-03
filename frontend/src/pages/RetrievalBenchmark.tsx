import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiRequestError } from "../api/base";
import {
  cancelRun,
  cancelSuite,
  createRun,
  getRun,
  getRunResult,
  getRunResults,
  getSuite,
  getSuiteReport,
  getSuiteReportText,
  listDatasets,
  listRuns,
  listSuites,
  listTranslationPolicies,
  resumeRun,
  resumeSuite,
  startSuite,
} from "../api/retrievalBenchmark";
import type {
  BenchmarkRun,
  Dataset,
  LatencyMetrics,
  QueryResult,
  QueryResultDetail,
  RunHeadline,
  RunStatus,
  SuiteDetail,
  SuiteReport,
  SuiteReportRow,
  SuiteSlice,
  SuiteSummary,
  TaskType,
  TranslationPolicy,
} from "../api/retrievalBenchmark";
import Button from "../components/Button";
import RetrievalBenchmarkDetail from "../components/RetrievalBenchmarkDetail";
import { RAtHeatStrip, ResultIndicator, perQueryRAt } from "../components/RetrievalBenchmarkDetail/visuals";

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

// A run's p95/max only matter as an outlier signal, not a number anyone
// watches per run — flag it instead of always showing all four latency
// figures at equal weight (previously P50/P95/Max/≤10s sat in their own
// full-width row on every run).
function isSlow(latency: LatencyMetrics): boolean {
  return (latency.p95_ms ?? 0) > 10000 || (latency.max_ms ?? 0) > 15000;
}

function outlierClass(ms: number | null, p50: number | null): string {
  if (ms === null || p50 === null || p50 <= 0) return "";
  return ms > p50 * 3 && ms > 3000 ? "text-[#c64545] font-bold" : "";
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

function ScoreBar({ value, tone = "primary" }: { value: number; tone?: "primary" | "muted" }) {
  const width = `${Math.max(0, Math.min(1, value)) * 100}%`;
  return (
    <div className="h-2 rounded-full bg-proto-soft overflow-hidden w-full">
      <div
        className={`h-full rounded-full ${tone === "primary" ? "bg-proto-primary" : "bg-proto-teal"}`}
        style={{ width }}
      />
    </div>
  );
}

// ── report sections ───────────────────────────────────────────────────────
//
// Previously this whole area was a single CaveatsBlock: four standing
// paragraphs (stale-index warning, "QA answer text not checked", "TRAKE is
// Tier 0", "translations aren't frozen") shown in full every time any run
// was viewed, regardless of whether that run even had QA/TRAKE queries or
// was being compared to anything. Each caveat now lives next to the metric
// it actually qualifies instead of in a standing block everyone reads every
// time: stale-index stays a real-time conditional banner below; the QA/TRAKE
// notes are captions on their own rows in TaskTypeBars; the
// translation-not-frozen note is a tooltip on the policy field in the
// "New run" panel; the live-round warning sits next to the Start button —
// see the JSX further down.

function HeadlineStrip({ headline }: { headline: RunHeadline }) {
  return (
    <div className="border border-proto-line rounded-[10px] bg-white p-4">
      <div className="flex flex-wrap items-start gap-8">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
            Final score
          </div>
          <div className="font-mono font-bold text-proto-ink text-[34px] leading-none mt-1">
            {score(headline.final_score_kis_qa)}
          </div>
          <div className="text-[11px] text-proto-muted mt-1.5">
            {headline.scored_queries} scored ·{" "}
            <span className="font-mono">KIS only {score(headline.final_score_kis)}</span>{" "}
            <span
              className="cursor-help"
              title="The blended score includes QA, but QA's answer text is never checked — only video + frame. KIS-only excludes QA so you can see how much that shifts the blended number."
            >
              ⓘ
            </span>
          </div>
        </div>

        <div>
          <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-2">
            R@k
          </div>
          <RAtHeatStrip rAt={headline.r_at_kis_qa} />
        </div>

        <div>
          <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
            Right video, wrong frame
          </div>
          <div className="font-mono font-bold text-[#c9962b] text-[22px] mt-1 leading-none">
            {headline.interval.video_hit_interval_miss}
          </div>
        </div>
      </div>

      <div className="mt-3 pt-3 border-t border-proto-line flex flex-wrap items-center gap-x-6 gap-y-1.5 text-[11.5px] text-proto-muted">
        <span>
          Found the video · <b className="text-proto-ink font-mono">{pct(headline.video.hit_at_1)}</b>{" "}
          at rank 1
        </span>
        <details>
          <summary className="cursor-pointer inline">more video-ranking detail</summary>
          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 font-mono">
            <span>R@3 <b className="text-proto-ink">{pct(headline.video.recall_at_3)}</b></span>
            <span>R@5 <b className="text-proto-ink">{pct(headline.video.recall_at_5)}</b></span>
            <span>R@10 <b className="text-proto-ink">{pct(headline.video.recall_at_10)}</b></span>
            <span>MRR <b className="text-proto-ink">{headline.video.mrr.toFixed(3)}</b></span>
            <span>median rank {headline.video.median_reference_rank ?? "—"}</span>
          </div>
        </details>
        <span className="ml-auto">
          Typical{" "}
          <b
            className="text-proto-ink font-mono cursor-help"
            title={`p95 ${seconds(headline.latency.p95_ms)} · within 10s ${pct(headline.latency.within_10s_rate)}`}
          >
            {seconds(headline.latency.p50_ms)}
          </b>
          {isSlow(headline.latency) && (
            <span className="ml-1 text-[#c64545] font-bold">
              · slowest {seconds(headline.latency.max_ms)}
            </span>
          )}
        </span>
      </div>
    </div>
  );
}

function TaskTypeRow({
  label,
  count,
  value,
  valueLabel,
  caption,
  tone = "primary",
}: {
  label: string;
  count: number;
  value: number;
  valueLabel: string;
  caption?: string;
  tone?: "primary" | "muted";
}) {
  return (
    <div>
      <div className="flex items-center gap-3 text-[12px]">
        <span className="font-bold text-proto-ink w-12">{label}</span>
        <span className="text-proto-muted text-[11px] w-20 shrink-0">{count} queries</span>
        <div className="flex-1">
          <ScoreBar value={value} tone={tone} />
        </div>
        <span className="font-mono font-bold text-proto-ink w-14 text-right shrink-0">
          {valueLabel}
        </span>
      </div>
      {/* QA and TRAKE captions are always-visible text, not a hover tooltip —
          QA alone is roughly a quarter of every dataset, so the caveat that
          its answer text isn't graded needs to survive a skim, not require a
          deliberate hover. */}
      {caption && <div className="mt-1 ml-[6.5rem] text-[11px] text-proto-muted">{caption}</div>}
    </div>
  );
}

function TaskTypeBars({ run }: { run: BenchmarkRun }) {
  const byType = run.task_type_summary;
  if (!byType) return null;
  return (
    <div className="border border-proto-line rounded-[10px] bg-white p-4 space-y-3">
      <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
        By question type
      </div>
      <TaskTypeRow
        label="KIS"
        count={byType.KIS.video.total}
        value={byType.KIS.interval.final_score}
        valueLabel={score(byType.KIS.interval.final_score)}
      />
      <TaskTypeRow
        label="QA"
        count={byType.QA.video.total}
        value={byType.QA.interval.final_score}
        valueLabel={score(byType.QA.interval.final_score)}
        caption="Answer text isn't graded — only video + frame."
      />
      <TaskTypeRow
        label="TRAKE"
        count={byType.TRAKE.video.total}
        value={byType.TRAKE.video.mrr}
        valueLabel={score(byType.TRAKE.video.mrr)}
        tone="muted"
        caption="Video match only — individual moments aren't checked."
      />
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
              <div className="space-y-2">
                <div className="flex items-baseline gap-2">
                  <span className="font-mono font-bold text-[22px] text-proto-ink">
                    {score(run.summary.final_score_kis_qa)}
                  </span>
                  <span className="text-[11px] text-proto-muted">
                    KIS only {score(run.summary.final_score_kis)}
                  </span>
                </div>
                <RAtHeatStrip rAt={run.summary.r_at_kis_qa} size="sm" />
              </div>
            ) : (
              <p className="text-[12px] text-proto-muted m-0">No summary.</p>
            )}
          </div>
        ))}
      </div>

      {mismatch ? (
        <div className="rounded-[8px] border border-[#d4a017]/40 bg-[#d4a017]/10 px-3 py-2 text-[12px] text-[#7a5c0c]">
          These two runs used a different translation policy or model config, so a
          combined number would average incompatible measurements. Pick runs with
          matching config to see it.
        </div>
      ) : (
        <div className="border border-proto-line rounded-[10px] bg-white px-4 py-3 text-[13px] flex items-baseline gap-2">
          <span className="text-proto-muted">Combined score</span>
          <b
            className="font-mono text-proto-ink text-[16px] cursor-help"
            title="A portfolio figure across both datasets pooled — Round 1 and Round 2 aren't equally difficult, so treat this as a rough blend, not an apples-to-apples score."
          >
            {score(combined)}
          </b>
          <span className="text-proto-muted text-[11px] cursor-help">ⓘ</span>
        </div>
      )}
    </div>
  );
}

// ── page ──────────────────────────────────────────────────────────────────

// ── ablation suite view ────────────────────────────────────────────────────

const SUITE_PRESETS = ["core", "trake", "extras"];
const SUITE_BENCHMARKS = [
  { id: "A", label: "Benchmark A (rounds 1-3, 86)" },
  { id: "B", label: "Benchmark B (final, 28)" },
  { id: "round1", label: "Round 1" },
  { id: "round2", label: "Round 2" },
  { id: "round3", label: "Round 3" },
];
const SUITE_TASKS = ["all", "KIS", "QA", "TRAKE"];
const SUITE_PREFIXES = ["all", "L", "M", "N", "S"];

function signed(value: number, digits: number): string {
  const text = value.toFixed(digits);
  return value > 0 ? `+${text}` : text;
}

function saveText(text: string, name: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

function ViewToggle({
  view,
  onChange,
}: {
  view: "single" | "suite";
  onChange: (view: "single" | "suite") => void;
}) {
  return (
    <div className="flex gap-1 mb-4">
      {(["single", "suite"] as const).map((item) => (
        <button
          key={item}
          type="button"
          onClick={() => onChange(item)}
          className={`px-3 py-1 rounded-[7px] border text-[12.5px] font-semibold ${
            view === item
              ? "bg-proto-primary text-white border-proto-primary"
              : "bg-white text-proto-muted border-proto-line"
          }`}
        >
          {item === "single" ? "Single run" : "Ablation suite"}
        </button>
      ))}
    </div>
  );
}

// One configuration of the real system per row, one component varied at a time. The numbers come
// from the server's report, computed from the runs that have results so far.
function AblationSuiteView() {
  const [suites, setSuites] = useState<SuiteSummary[]>([]);
  const [suiteId, setSuiteId] = useState("");
  const [detail, setDetail] = useState<SuiteDetail | null>(null);
  const [report, setReport] = useState<SuiteReport | null>(null);
  const [preset, setPreset] = useState("core");
  const [slice, setSlice] = useState<SuiteSlice>({
    benchmark: "A",
    flags: "all",
    task_type: "all",
    prefix: "all",
  });
  const [reloadKey, setReloadKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSuites()
      .then((response) => {
        setSuites(response.suites);
        setSuiteId((current) => current || (response.suites[0]?.suite_id ?? ""));
      })
      .catch((err) => setError(errorMessage(err)));
  }, []);

  // Same polling loop as the single-run view: refresh until the suite is finished.
  useEffect(() => {
    if (!suiteId) return;
    let cancelled = false;
    let done = false;
    const refresh = async () => {
      try {
        const [next, nextReport] = await Promise.all([getSuite(suiteId), getSuiteReport(suiteId)]);
        if (cancelled) return;
        done = next.suite.finished;
        setDetail(next);
        setReport(nextReport);
        setError(null);
      } catch (err) {
        if (!cancelled) setError(errorMessage(err));
      }
    };
    void refresh();
    const timer = window.setInterval(() => {
      if (!done) void refresh();
    }, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [suiteId, reloadKey]);

  const act = async (action: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await action();
      setReloadKey((key) => key + 1);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const doStart = () =>
    act(async () => {
      const created = await startSuite({ name: `${preset} ${new Date().toLocaleString()}`, preset });
      setDetail(null);
      setReport(null);
      setSuiteId(created.suite.suite_id);
      setSuites((await listSuites()).suites);
    });

  const download = (format: "csv" | "latex") =>
    act(async () => {
      const text = await getSuiteReportText(suiteId, format, slice);
      saveText(
        text,
        `suite-${suiteId}-${slice.benchmark}.${format === "csv" ? "csv" : "tex"}`,
        format === "csv" ? "text/csv" : "text/plain"
      );
    });

  const status = detail?.suite ?? null;
  const progress = status && status.queries_total > 0 ? status.queries_done / status.queries_total : 0;
  const active = !!status && !status.finished;
  const resumable =
    !!status && ["interrupted", "partial", "cancelled", "failed"].some((key) => (status.by_status[key] ?? 0) > 0);

  const rows: SuiteReportRow[] = (report?.table ?? []).filter(
    (row) =>
      row.benchmark === slice.benchmark &&
      row.flags === slice.flags &&
      row.task_type === slice.task_type &&
      row.prefix === slice.prefix
  );
  const baseline = rows.find((row) => row.config.startsWith("C01")) ?? rows[0];
  const best = (pick: (row: SuiteReportRow) => number) =>
    rows.length ? Math.max(...rows.map(pick)) : 0;
  const bestHit1 = best((row) => row.hit_at_1);
  const bestR5 = best((row) => row.r_at_5);
  const bestR10 = best((row) => row.r_at_10);
  const bestMrr = best((row) => row.mrr);
  const showEvents = rows.some((row) => row.event_accuracy !== null);

  const cell = (value: number, base: number | undefined, isBest: boolean, scale: number, digits: number) => (
    <td className="px-3 py-1.5 text-right font-mono whitespace-nowrap">
      <span className={isBest ? "font-bold text-proto-ink" : "text-proto-ink"}>
        {(value * scale).toFixed(digits)}
      </span>
      {base !== undefined && value !== base && (
        <span className="ml-1.5 text-[10.5px] text-proto-muted">{signed((value - base) * scale, digits)}</span>
      )}
    </td>
  );

  const selectClass = "w-full px-2 py-1.5 rounded-[7px] border border-proto-line bg-white text-[13px]";
  const labelClass = "block text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-1";

  return (
    <div>
      <p className="text-[12.5px] text-proto-muted mt-0 mb-3">
        Each row is one configuration of the real system with one component varied (encoders, rerank
        placement, text policy, TRAKE-N). Deltas are against the baseline row. Labels are
        team-annotated, not official.
      </p>
      {error && <p className="text-[#c64545] text-sm mb-3">{error}</p>}

      <div className="border border-proto-line rounded-[10px] bg-white p-4 mb-4">
        <div className="grid gap-3 min-[900px]:grid-cols-[1fr_1fr_auto]">
          <label>
            <span className={labelClass}>Suite</span>
            <select
              className={selectClass}
              value={suiteId}
              disabled={suites.length === 0}
              onChange={(event) => {
                setDetail(null);
                setReport(null);
                setSuiteId(event.target.value);
              }}
            >
              {suites.length === 0 && <option value="">No suites yet</option>}
              {suites.map((item) => (
                <option key={item.suite_id} value={item.suite_id}>
                  {item.name ?? item.suite_id} · {item.runs} runs · {formatDate(item.created_at)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className={labelClass}>New suite (preset)</span>
            <select className={selectClass} value={preset} onChange={(event) => setPreset(event.target.value)}>
              {SUITE_PRESETS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-end gap-2">
            <Button size="sm" onClick={() => void doStart()} loading={busy} disabled={active}>
              Start suite
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => void act(() => cancelSuite(suiteId))}
              disabled={!active || busy}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => void act(() => resumeSuite(suiteId))}
              disabled={active || !resumable || busy}
            >
              Resume
            </Button>
          </div>
        </div>
        <p className="text-[11px] text-proto-muted mt-2 mb-0">
          Runs share the live search backend with the app. Texts must be cached first; a missing cache
          without the Gemini key is refused before anything runs.
        </p>
      </div>

      {status && (
        <div className="border border-proto-line rounded-[10px] bg-white p-4 mb-4">
          <div className="flex items-center gap-3 flex-wrap mb-2">
            <span className="text-[13px] text-proto-ink font-semibold">
              {status.queries_done} / {status.queries_total} queries · {status.runs} runs
            </span>
            {Object.entries(status.by_status).map(([name, count]) => (
              <span key={name} className="flex items-center gap-1 text-[12px] text-proto-muted">
                <StatusBadge status={name as RunStatus} /> {count}
              </span>
            ))}
          </div>
          <ScoreBar value={progress} />
        </div>
      )}

      <div className="border border-proto-line rounded-[10px] bg-white p-4">
        <div className="grid gap-3 min-[900px]:grid-cols-4 mb-3">
          <label>
            <span className={labelClass}>Benchmark</span>
            <select
              className={selectClass}
              value={slice.benchmark}
              onChange={(event) => setSlice({ ...slice, benchmark: event.target.value })}
            >
              {SUITE_BENCHMARKS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className={labelClass}>Task type</span>
            <select
              className={selectClass}
              value={slice.task_type}
              onChange={(event) => setSlice({ ...slice, task_type: event.target.value })}
            >
              {SUITE_TASKS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className={labelClass}>Video prefix</span>
            <select
              className={selectClass}
              value={slice.prefix}
              onChange={(event) => setSlice({ ...slice, prefix: event.target.value })}
            >
              {SUITE_PREFIXES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className={labelClass}>Flagged queries</span>
            <select
              className={selectClass}
              value={slice.flags}
              onChange={(event) => setSlice({ ...slice, flags: event.target.value })}
            >
              <option value="all">Included</option>
              <option value="exclude_flagged">Excluded (vfr_times, whole-video interval)</option>
            </select>
          </label>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px] border-collapse">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wide text-proto-muted border-b border-proto-line">
                <th className="px-3 py-1.5">Configuration</th>
                <th className="px-3 py-1.5 text-right">Hit@1</th>
                <th className="px-3 py-1.5 text-right">R@5</th>
                <th className="px-3 py-1.5 text-right">R@10</th>
                <th className="px-3 py-1.5 text-right">MRR</th>
                <th className="px-3 py-1.5 text-right">n</th>
                {showEvents && <th className="px-3 py-1.5 text-right">Event acc.</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.config} className="border-b border-proto-line/60">
                  <td className="px-3 py-1.5 text-proto-ink">
                    {row.config}
                    {row === baseline && <span className="ml-1.5 text-[10.5px] text-proto-muted">baseline</span>}
                  </td>
                  {cell(row.hit_at_1, row === baseline ? undefined : baseline?.hit_at_1, row.hit_at_1 === bestHit1, 100, 1)}
                  {cell(row.r_at_5, row === baseline ? undefined : baseline?.r_at_5, row.r_at_5 === bestR5, 100, 1)}
                  {cell(row.r_at_10, row === baseline ? undefined : baseline?.r_at_10, row.r_at_10 === bestR10, 100, 1)}
                  {cell(row.mrr, row === baseline ? undefined : baseline?.mrr, row.mrr === bestMrr, 1, 3)}
                  <td className="px-3 py-1.5 text-right font-mono text-proto-muted">
                    {row.n}
                    {row.failed > 0 && <span className="text-[#c64545]"> ({row.failed} failed)</span>}
                  </td>
                  {showEvents && (
                    <td className="px-3 py-1.5 text-right font-mono">
                      {row.event_accuracy === null ? "-" : pct(row.event_accuracy)}
                    </td>
                  )}
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={showEvents ? 7 : 6} className="px-3 py-4 text-proto-muted">
                    {suiteId ? "No results for this slice yet." : "Start a suite or pick one above."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center gap-2 mt-3">
          <Button size="sm" variant="secondary" onClick={() => void download("csv")} disabled={!suiteId || busy}>
            Download CSV
          </Button>
          <Button size="sm" variant="secondary" onClick={() => void download("latex")} disabled={!suiteId || busy}>
            Download LaTeX
          </Button>
          <span className="text-[11px] text-proto-muted">
            CSV is every slice; LaTeX is the slice selected above.
          </span>
        </div>
      </div>
    </div>
  );
}

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
  const [view, setView] = useState<"single" | "suite">("single");

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

  if (view === "suite") {
    return (
      <div className="max-w-[1240px] mx-auto p-6 font-baloo">
        <h2 className="text-2xl text-proto-ink leading-tight mb-3">Retrieval Benchmark</h2>
        <ViewToggle view={view} onChange={setView} />
        <AblationSuiteView />
      </div>
    );
  }

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
  const runP50 = run?.summary?.latency.p50_ms ?? null;

  return (
    <div className="max-w-[1240px] mx-auto p-6 font-baloo">
      <ViewToggle view={view} onChange={setView} />
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
            <div
              className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-1 cursor-help"
              title="Translations are captured per run, not frozen across runs — re-running the same policy can yield slightly different English and shift results a little."
            >
              Translation policy ⓘ
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
        <div className="px-4 pb-2 flex items-center gap-2">
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
        {/* Contextual, not a standing disclaimer on every finished run's
            results — this only matters at the moment someone is about to
            start a run, so it lives next to the button that does that. */}
        <div className="px-4 pb-4 text-[11px] text-proto-muted">
          Runs share the live search backend with the app — avoid starting one during a live round.
        </div>
      </div>

      {run && (
        <div className="grid gap-4 min-[1100px]:grid-cols-[1fr_380px]">
          <div className="space-y-4 min-w-0">
            {/* metadata header */}
            <div className="border border-proto-line rounded-[10px] bg-white p-4">
              <div className="flex items-center gap-2 flex-wrap">
                <StatusBadge status={run.status} />
                <span className="text-[12px] text-proto-ink font-semibold">
                  {selectedDataset?.display_name ?? run.dataset_version}
                </span>
                <span className="text-[11.5px] font-mono text-proto-muted">
                  {run.completed_count} of {run.query_count} done
                  {run.failed_count > 0 && (
                    <span className="text-[#c64545]"> · {run.failed_count} failed</span>
                  )}
                </span>
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

              {run.error && (
                <div className="mt-2 text-[12px] font-mono text-[#c64545]">{run.error}</div>
              )}
              {referenceSet?.label_semantics && (
                <p className="mt-3 mb-0 text-[11.5px] text-proto-muted italic leading-snug">
                  {referenceSet.label_semantics}
                </p>
              )}

              {/* Reproducibility metadata (dataset/reference slugs, model
                  config, build commit) — collapsed by default. Every run
                  today uses the same hardcoded ensemble config, so none of
                  this differentiates one run from another yet; it earns a
                  click, not permanent space next to the score. */}
              <details className="mt-3 text-[11.5px] text-proto-muted">
                <summary className="cursor-pointer">Run details</summary>
                <div className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2 font-mono">
                  <span>
                    run #{run.id}
                    {run.resume_count > 0 && ` · resumed ×${run.resume_count}`}
                  </span>
                  <span>
                    {run.dataset_version} / {run.reference_set_version}
                  </span>
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
                </div>
              </details>
            </div>

            {staleFiles.length > 0 && (
              <div className="border border-[#c64545]/30 rounded-[10px] bg-[#c64545]/5 px-4 py-3 text-[12px] text-[#c64545]">
                <b>Index was stale when this run started.</b> These files changed on disk
                without a restart, so results may not reflect current retrieval:{" "}
                <span className="font-mono">{staleFiles.join(", ")}</span>
              </div>
            )}

            {run.summary ? (
              <>
                <HeadlineStrip headline={run.summary} />
                <TaskTypeBars run={run} />
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
                  <option value="video-miss">video missed</option>
                  <option value="interval-miss">wrong frame</option>
                  <option value="video-hit-interval-miss">right video, wrong frame</option>
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
                      <th className="px-3 py-1.5 font-semibold">Result</th>
                      <th className="px-3 py-1.5 font-semibold">R@k</th>
                      <th className="px-3 py-1.5 font-semibold">Final</th>
                      <th className="px-3 py-1.5 font-semibold">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredResults.map((result) => {
                      const selected = result.query_key === selectedQueryKey;
                      const isTrake = result.task_type === "TRAKE";
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
                          <td className="px-3 py-1.5">
                            <ResultIndicator result={result} />
                          </td>
                          <td className="px-3 py-1.5">
                            {isTrake ? (
                              <span className="text-proto-muted">—</span>
                            ) : (
                              <RAtHeatStrip rAt={perQueryRAt(result.interval_rank)} size="sm" />
                            )}
                          </td>
                          <td className="px-3 py-1.5 font-mono">
                            {isTrake ? "—" : score(result.final_score)}
                          </td>
                          <td className={`px-3 py-1.5 font-mono ${outlierClass(result.total_ms, runP50)}`}>
                            {seconds(result.total_ms)}
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
