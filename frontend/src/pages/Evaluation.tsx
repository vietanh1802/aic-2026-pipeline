import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiRequestError } from "../api/base";
import {
  cancelEvaluationRun,
  createEvaluationRun,
  getEvaluationResults,
  getEvaluationRun,
  listEvaluationDatasets,
  listEvaluationRuns,
  listEvaluationTranslationPolicies,
  resumeEvaluationRun,
  type EvaluationDataset,
  type EvaluationResult,
  type EvaluationRun,
  type EvaluationRunStatus,
  type EvaluationSummary,
  type EvaluationTranslationPolicy,
} from "../api/evaluation";
import Button from "../components/Button";
import EvaluationDetail from "../components/EvaluationDetail";

const POLL_MS = 2000;

const ACTIVE_STATUSES = new Set<EvaluationRunStatus>([
  "queued",
  "running",
  "cancelling",
]);

const RESUMABLE_STATUSES = new Set<EvaluationRunStatus>([
  "partial",
  "failed",
  "cancelled",
  "interrupted",
]);

type ResultFilter = "all" | "top1" | "miss10" | "failed";

function errorMessage(error: unknown): string {
  return error instanceof ApiRequestError
    ? error.message
    : "Evaluation request failed";
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatSeconds(ms: number | null): string {
  if (ms === null) return "—";
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function strategyLabel(value: string): string {
  return value === "ensemble_search_en_v1" ? "Ensemble Search" : value;
}

function translatorLabel(value: string): string {
  if (value.toLowerCase().includes("gemini")) return "Gemini · VI → EN";
  return value;
}

function translationPolicyLabel(
  value: string | null | undefined,
  policies: EvaluationTranslationPolicy[]
): string {
  if (!value) return "Not recorded";
  return policies.find((policy) => policy.id === value)?.label ?? value;
}

function rankingLabel(value: string): string {
  return value === "first_frame_occurrence_v1"
    ? "First-frame occurrence"
    : value;
}

function statusClasses(status: EvaluationRunStatus): string {
  if (status === "completed") return "bg-[#3d7a4d]/10 text-[#3d7a4d]";
  if (status === "running") return "bg-proto-teal/15 text-[#317d6e]";
  if (status === "queued") return "bg-proto-soft text-proto-muted";
  if (status === "partial" || status === "cancelling") {
    return "bg-[#d4a017]/20 text-[#8a6a0f]";
  }
  if (status === "failed") return "bg-[#c64545]/10 text-[#c64545]";
  return "bg-proto-card text-proto-muted";
}

function StatusBadge({ status }: { status: EvaluationRunStatus }) {
  return (
    <span
      className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full uppercase tracking-wide ${statusClasses(
        status
      )}`}
    >
      {status}
    </span>
  );
}

function MetricCard({
  label,
  value,
  count,
  primary = false,
}: {
  label: string;
  value: string;
  count: string;
  primary?: boolean;
}) {
  return (
    <div className="border border-proto-line rounded-[10px] bg-white p-4 min-h-[112px]">
      <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
        {label}
      </div>
      <div
        className={`font-mono font-bold text-proto-ink leading-none mt-3 ${
          primary ? "text-[30px]" : "text-[27px]"
        }`}
      >
        {value}
      </div>
      <div className="text-[11.5px] font-mono text-proto-muted mt-2">{count}</div>
    </div>
  );
}

function hitCell(value: boolean | null) {
  if (value === null) return <span className="text-proto-muted">—</span>;
  return value ? (
    <span className="text-[#3d7a4d] font-bold" title="Hit">
      ✓
    </span>
  ) : (
    <span className="text-proto-muted" title="Miss">
      ×
    </span>
  );
}

function metricCount(rate: number, total: number): string {
  return `${Math.round(rate * total)} / ${total}`;
}

function SummaryMetrics({ summary }: { summary: EvaluationSummary }) {
  if (summary.completed_queries === 0) {
    return (
      <div className="border border-proto-line rounded-[10px] bg-white p-4">
        <div className="text-sm font-semibold text-proto-ink">
          No retrieval metrics available
        </div>
        <p className="text-[12.5px] text-proto-muted mt-1 mb-0">
          {summary.failed_queries} / {summary.total_queries} queries failed before scoring.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 min-[1050px]:grid-cols-4 gap-3">
        <MetricCard
          label="Top-1 video"
          value={formatPercent(summary.top1_accuracy)}
          count={metricCount(summary.top1_accuracy, summary.total_queries)}
          primary
        />
        <MetricCard
          label="Recall @3"
          value={formatPercent(summary.recall_at_3)}
          count={metricCount(summary.recall_at_3, summary.total_queries)}
        />
        <MetricCard
          label="Recall @5"
          value={formatPercent(summary.recall_at_5)}
          count={metricCount(summary.recall_at_5, summary.total_queries)}
        />
        <MetricCard
          label="Recall @10"
          value={formatPercent(summary.recall_at_10)}
          count={metricCount(summary.recall_at_10, summary.total_queries)}
        />
      </div>

      <div className="mt-3 border border-proto-line rounded-[10px] bg-white px-4 py-2.5 text-[12px] text-proto-muted">
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          <span>
            MRR <b className="font-mono text-proto-ink">{summary.mrr.toFixed(3)}</b>
          </span>
          <span>·</span>
          <span>
            Median ref. rank{" "}
            <b className="font-mono text-proto-ink">
              {summary.median_reference_rank ?? "—"}
            </b>
          </span>
          <span>·</span>
          <span>
            Not retrieved{" "}
            <b className="font-mono text-proto-ink">
              {summary.not_retrieved_count}
            </b>
          </span>
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1">
          <span>
            P50 <b className="font-mono text-proto-ink">{formatSeconds(summary.p50_ms)}</b>
          </span>
          <span>·</span>
          <span>
            P95 <b className="font-mono text-proto-ink">{formatSeconds(summary.p95_ms)}</b>
          </span>
          <span>·</span>
          <span>
            Max <b className="font-mono text-proto-ink">{formatSeconds(summary.max_ms)}</b>
          </span>
          <span>·</span>
          <span>
            ≤10s{" "}
            <b className="font-mono text-proto-ink">
              {formatPercent(summary.within_10s_rate)}
            </b>
          </span>
        </div>
      </div>
    </>
  );
}

export default function Evaluation() {
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([]);
  const [policies, setPolicies] = useState<EvaluationTranslationPolicy[]>([]);
  const [selectedPolicy, setSelectedPolicy] = useState("");
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [run, setRun] = useState<EvaluationRun | null>(null);
  const [results, setResults] = useState<EvaluationResult[]>([]);
  const [selectedQueryKey, setSelectedQueryKey] = useState<string | null>(null);
  const [filter, setFilter] = useState<ResultFilter>("all");
  const [datasetVersion, setDatasetVersion] = useState("");
  const [referenceSetVersion, setReferenceSetVersion] = useState("");
  const [loading, setLoading] = useState(true);
  const [runLoading, setRunLoading] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      try {
        const [datasetResponse, runResponse, policyResponse] = await Promise.all([
          listEvaluationDatasets(),
          listEvaluationRuns(),
          listEvaluationTranslationPolicies(),
        ]);
        if (cancelled) return;

        setDatasets(datasetResponse.datasets);
        setPolicies(policyResponse.policies);
        setSelectedPolicy(policyResponse.default);
        setRuns(runResponse.runs);

        const latestRun = runResponse.runs[0] ?? null;
        const firstDataset = datasetResponse.datasets[0] ?? null;
        if (latestRun) {
          setSelectedRunId(latestRun.id);
          setRun(latestRun);
          setDatasetVersion(latestRun.dataset_version);
          setReferenceSetVersion(latestRun.reference_set_version);
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

  const patchRun = useCallback((next: EvaluationRun) => {
    setRuns((current) => {
      const exists = current.some((item) => item.id === next.id);
      const updated = exists
        ? current.map((item) => (item.id === next.id ? next : item))
        : [next, ...current];
      return updated.sort((a, b) => b.id - a.id);
    });
  }, []);

  const refreshSelectedRun = useCallback(
    async (showLoading = false) => {
      if (selectedRunId === null) return;
      if (showLoading) setRunLoading(true);
      try {
        const [runResponse, resultResponse] = await Promise.all([
          getEvaluationRun(selectedRunId),
          getEvaluationResults(selectedRunId),
        ]);
        setRun(runResponse.run);
        setResults(resultResponse.results);
        patchRun(runResponse.run);
        setDatasetVersion(runResponse.run.dataset_version);
        setReferenceSetVersion(runResponse.run.reference_set_version);
        setError(null);
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        if (showLoading) setRunLoading(false);
      }
    },
    [patchRun, selectedRunId]
  );

  useEffect(() => {
    if (selectedRunId === null) {
      setRun(null);
      setResults([]);
      setSelectedQueryKey(null);
      return;
    }
    setSelectedQueryKey(null);
    void refreshSelectedRun(true);
  }, [refreshSelectedRun, selectedRunId]);

  const pollingRunId = run?.id ?? null;
  const pollingRunStatus = run?.status ?? null;

  useEffect(() => {
    if (
      pollingRunId !== selectedRunId ||
      pollingRunStatus === null ||
      !ACTIVE_STATUSES.has(pollingRunStatus)
    ) {
      return;
    }

    let cancelled = false;
    let timer: number | undefined;

    const poll = async () => {
      await refreshSelectedRun(false);
      if (!cancelled) {
        timer = window.setTimeout(() => void poll(), POLL_MS);
      }
    };

    timer = window.setTimeout(() => void poll(), POLL_MS);

    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, [
    pollingRunId,
    pollingRunStatus,
    refreshSelectedRun,
    selectedRunId,
  ]);

  const selectedDataset = useMemo(
    () => datasets.find((dataset) => dataset.version === datasetVersion) ?? null,
    [datasetVersion, datasets]
  );

  const selectedReference = useMemo(
    () =>
      selectedDataset?.reference_sets.find(
        (reference) => reference.version === referenceSetVersion
      ) ?? null,
    [referenceSetVersion, selectedDataset]
  );

  const selectedPolicyDefinition =
    policies.find((policy) => policy.id === selectedPolicy) ?? null;

  const activeRun = runs.find((item) => ACTIVE_STATUSES.has(item.status)) ?? null;

  const selectedResult =
    results.find((result) => result.query_key === selectedQueryKey) ?? null;

  const counts = useMemo(
    () => ({
      all: results.length,
      top1: results.filter(
        (result) => result.status === "completed" && result.hit_at_1 === false
      ).length,
      miss10: results.filter(
        (result) => result.status === "completed" && result.hit_at_10 === false
      ).length,
      failed: results.filter((result) => result.status === "failed").length,
    }),
    [results]
  );

  const filteredResults = useMemo(() => {
    if (filter === "top1") {
      return results.filter(
        (result) => result.status === "completed" && result.hit_at_1 === false
      );
    }
    if (filter === "miss10") {
      return results.filter(
        (result) => result.status === "completed" && result.hit_at_10 === false
      );
    }
    if (filter === "failed") {
      return results.filter((result) => result.status === "failed");
    }
    return results;
  }, [filter, results]);

  const startRun = async () => {
    const targetDatasetVersion = run?.dataset_version ?? datasetVersion;
    const targetReferenceVersion =
      run?.reference_set_version ?? referenceSetVersion;
    if (!targetDatasetVersion || !targetReferenceVersion || !selectedPolicy) return;

    setActionBusy(true);
    try {
      const freshRuns = await listEvaluationRuns();
      setRuns(freshRuns.runs);
      const alreadyActive = freshRuns.runs.find((item) =>
        ACTIVE_STATUSES.has(item.status)
      );
      if (alreadyActive) {
        setSelectedRunId(alreadyActive.id);
        setError(`Run #${alreadyActive.id} is already active.`);
        return;
      }

      const response = await createEvaluationRun({
        dataset_version: targetDatasetVersion,
        reference_set_version: targetReferenceVersion,
        translation_policy: selectedPolicy,
      });
      patchRun(response.run);
      setRun(response.run);
      setResults([]);
      setSelectedQueryKey(null);
      setSelectedRunId(response.run.id);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setActionBusy(false);
    }
  };

  const cancelRun = async () => {
    if (!run) return;
    setActionBusy(true);
    try {
      const response = await cancelEvaluationRun(run.id);
      setRun(response.run);
      patchRun(response.run);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setActionBusy(false);
    }
  };

  const resumeRun = async () => {
    if (!run) return;
    setActionBusy(true);
    try {
      const response = await resumeEvaluationRun(run.id);
      setRun(response.run);
      patchRun(response.run);
      setSelectedQueryKey(null);
      setError(null);
      await refreshSelectedRun(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setActionBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-[1200px] mx-auto p-6 font-baloo">
        <h2 className="text-2xl text-proto-ink">Evaluation</h2>
        <div className="mt-4 border border-proto-line rounded-[10px] bg-white p-4 text-sm text-proto-muted">
          Loading evaluation runs…
        </div>
      </div>
    );
  }

  const configuration = run?.configuration;
  const processed = run ? run.completed_count + run.failed_count : 0;
  const progress = run?.query_count
    ? Math.min(100, (processed / run.query_count) * 100)
    : 0;
  const canCancel = run?.status === "queued" || run?.status === "running";
  const canResume = !!run && RESUMABLE_STATUSES.has(run.status);
  const datasetName =
    datasets.find((dataset) => dataset.version === (run?.dataset_version ?? datasetVersion))
      ?.display_name ??
    run?.dataset_version ??
    datasetVersion;

  return (
    <div className="max-w-[1200px] mx-auto p-6 font-baloo">
      <div className="flex items-start gap-4 mb-4 flex-wrap">
        <div>
          <h2 className="text-2xl text-proto-ink leading-tight">Evaluation</h2>
          <p className="text-[12.5px] text-proto-muted mt-1 mb-0">
            Measure the current retrieval pipeline against the persisted Round 1 references.
          </p>
        </div>

        <label className="ml-auto flex items-center gap-2">
          <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
            Recent run
          </span>
          <select
            className="min-w-[190px] px-2 py-1 rounded-[7px] border border-proto-line bg-white text-[13px] text-proto-ink"
            value={selectedRunId ?? ""}
            disabled={runs.length === 0}
            onChange={(event) => setSelectedRunId(Number(event.target.value))}
          >
            {runs.length === 0 ? (
              <option value="">No runs yet</option>
            ) : (
              runs.map((item) => (
                <option key={item.id} value={item.id}>
                  #{item.id} · {translationPolicyLabel(
                    item.configuration?.translation_policy,
                    policies
                  )} · {item.status} · {formatDate(item.created_at)}
                </option>
              ))
            )}
          </select>
        </label>
      </div>

      {error && <p className="text-[#c64545] text-sm mb-3">{error}</p>}

      <div className="border border-proto-line rounded-[10px] bg-white overflow-hidden">
        <div className="px-4 py-2 bg-proto-soft flex items-center gap-2">
          <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
            Run configuration
          </span>
          {run && (
            <>
              <span className="font-mono text-[11px] text-proto-muted">#{run.id}</span>
              <StatusBadge status={run.status} />
            </>
          )}
        </div>

        <div className="p-4">
          {!run && datasets.length > 1 ? (
            <div className="grid sm:grid-cols-2 gap-4 mb-4">
              <label>
                <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-1">
                  Dataset
                </div>
                <select
                  className="w-full px-2 py-1.5 rounded-[7px] border border-proto-line bg-white text-[13px] text-proto-ink"
                  value={datasetVersion}
                  onChange={(event) => {
                    const nextVersion = event.target.value;
                    const nextDataset = datasets.find(
                      (dataset) => dataset.version === nextVersion
                    );
                    setDatasetVersion(nextVersion);
                    setReferenceSetVersion(
                      nextDataset?.reference_sets[0]?.version ?? ""
                    );
                  }}
                >
                  {datasets.map((dataset) => (
                    <option key={dataset.id} value={dataset.version}>
                      {dataset.display_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-1">
                  Reference
                </div>
                <select
                  className="w-full px-2 py-1.5 rounded-[7px] border border-proto-line bg-white text-[13px] text-proto-ink"
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
            </div>
          ) : null}

          <div className="grid sm:grid-cols-2 gap-x-6 gap-y-3 text-[13px]">
            <div>
              <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-0.5">
                Dataset
              </div>
              <div className="text-proto-ink">{datasetName || "—"}</div>
              <div className="text-[10.5px] font-mono text-proto-muted mt-0.5">
                {run?.dataset_version ?? datasetVersion}
              </div>
            </div>
            <div>
              <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-0.5">
                Reference
              </div>
              <div className="font-mono text-proto-ink">
                {(run?.reference_set_version ?? referenceSetVersion) || "—"}
              </div>
              {!run && selectedReference?.label_semantics && (
                <div className="text-[10.5px] text-proto-muted mt-0.5 line-clamp-1">
                  {selectedReference.label_semantics}
                </div>
              )}
            </div>
            <div>
              <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-0.5">
                Pipeline
              </div>
              <div className="text-proto-ink">
                {run ? strategyLabel(run.strategy) : "Recorded when the run starts"}
              </div>
              {run?.configuration?.models && (
                <div className="text-[10.5px] text-proto-muted mt-0.5">
                  {run.configuration.models.join(" + ")}
                </div>
              )}
            </div>
            <div>
              <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-0.5">
                Translation
              </div>
              <div className="text-proto-ink">
                {run ? translatorLabel(run.translator) : "Recorded when the run starts"}
              </div>
              {run && (
                <>
                  <div className="text-[10.5px] font-mono text-proto-muted mt-0.5">
                    {run.translator}
                  </div>
                  <div className="text-[10.5px] text-proto-muted mt-0.5">
                    Policy used · <b className="text-proto-ink font-medium">
                      {translationPolicyLabel(
                        run.configuration?.translation_policy,
                        policies
                      )}
                    </b>
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-proto-line">
            <div className="grid sm:grid-cols-[220px_minmax(0,1fr)] gap-3 items-start">
              <label>
                <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-1">
                  Policy for next run
                </div>
                <select
                  className="w-full px-2 py-1.5 rounded-[7px] border border-proto-line bg-white text-[13px] text-proto-ink"
                  value={selectedPolicy}
                  disabled={policies.length === 0 || actionBusy}
                  onChange={(event) => setSelectedPolicy(event.target.value)}
                >
                  {policies.map((policy) => (
                    <option key={policy.id} value={policy.id}>
                      {policy.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="text-[11.5px] text-proto-muted leading-relaxed pt-[17px]">
                {selectedPolicyDefinition?.description ??
                  "Choose the translation policy that will be frozen into the next evaluation run."}
              </div>
            </div>
          </div>

          {run && (
            <div className="mt-3 text-[11.5px] text-proto-muted flex flex-wrap gap-x-2 gap-y-1">
              {configuration?.top_k !== undefined && (
                <span>Top {String(configuration.top_k)}</span>
              )}
              {configuration?.top_m !== undefined && (
                <><span>·</span><span>Top-M {String(configuration.top_m)}</span></>
              )}
              {configuration?.use_rerank !== undefined && (
                <><span>·</span><span>{configuration.use_rerank ? "Rerank" : "No rerank"}</span></>
              )}
              <span>·</span>
              <span>{rankingLabel(run.video_ranking_policy)}</span>
              {run.runtime?.version && (
                <>
                  <span>·</span>
                  <span className="font-mono">
                    v{run.runtime.version}
                    {run.runtime.commit ? ` · ${run.runtime.commit}` : ""}
                  </span>
                </>
              )}
            </div>
          )}

          {run && ACTIVE_STATUSES.has(run.status) && (
            <div className="mt-4 pt-4 border-t border-proto-line">
              <div className="flex items-center gap-3 text-[12px]">
                <span className="text-proto-ink font-semibold">
                  {processed} / {run.query_count}
                </span>
                <span className="text-proto-muted">
                  {run.completed_count} completed · {run.failed_count} failed
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-proto-card overflow-hidden mt-2">
                <div
                  className="h-full bg-proto-primary transition-[width] duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <div className="flex items-center gap-3 mt-2.5">
                <p className="text-[11.5px] text-proto-muted m-0">
                  {run.status === "cancelling"
                    ? "Cancelling after the current query finishes."
                    : "The run continues on the backend if you leave this page."}
                </p>
                {canCancel && (
                  <Button
                    size="xs"
                    variant="danger"
                    loading={actionBusy}
                    className="ml-auto"
                    onClick={() => void cancelRun()}
                  >
                    Cancel
                  </Button>
                )}
              </div>
            </div>
          )}

          {run && !ACTIVE_STATUSES.has(run.status) && (
            <div className="mt-4 pt-4 border-t border-proto-line flex items-center gap-3 flex-wrap">
              <span className="text-[11.5px] text-proto-muted">
                {run.completed_count} completed · {run.failed_count} failed
              </span>
              {canResume ? (
                <Button
                  size="sm"
                  loading={actionBusy}
                  disabled={!!activeRun && activeRun.id !== run.id}
                  className="ml-auto"
                  onClick={() => void resumeRun()}
                >
                  Resume unfinished
                </Button>
              ) : (
                <Button
                  size="sm"
                  loading={actionBusy}
                  disabled={!!activeRun}
                  className="ml-auto"
                  onClick={() => void startRun()}
                >
                  Run evaluation
                </Button>
              )}
            </div>
          )}

          {!run && (
            <div className="mt-4 pt-4 border-t border-proto-line flex items-center gap-3">
              <span className="text-[11.5px] text-proto-muted">
                {selectedDataset?.query_count ?? 0} queries
              </span>
              <Button
                size="sm"
                loading={actionBusy}
                disabled={!!activeRun || !datasetVersion || !referenceSetVersion || !selectedPolicy}
                className="ml-auto"
                onClick={() => void startRun()}
              >
                Run evaluation
              </Button>
            </div>
          )}
        </div>
      </div>

      {run?.status === "partial" && (
        <div className="mt-4 px-4 py-2.5 rounded-[10px] border border-[#d4a017]/35 bg-[#d4a017]/10 text-[12px] text-[#8a6a0f]">
          Partial run · {run.completed_count} of {run.query_count} completed · {run.failed_count} failed
        </div>
      )}

      {run?.summary && (
        <div className="mt-4">
          <SummaryMetrics summary={run.summary} />
        </div>
      )}

      {run && (
        <div className="mt-4">
          <div className="flex gap-1 mb-3 flex-wrap">
            {(
              [
                ["all", `All ${counts.all}`],
                ["top1", `Top-1 misses ${counts.top1}`],
                ["miss10", `Miss@10 ${counts.miss10}`],
                ["failed", `Failed ${counts.failed}`],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => {
                  setFilter(id);
                  setSelectedQueryKey(null);
                }}
                className={`text-[12.5px] px-3 py-1 rounded-[7px] border ${
                  filter === id
                    ? "bg-proto-cream-strong border-proto-cream-strong text-proto-ink font-semibold"
                    : "border-proto-line text-proto-muted bg-white"
                }`}
              >
                {label}
              </button>
            ))}
            {runLoading && (
              <span className="ml-auto text-[11.5px] text-proto-muted self-center">
                Refreshing…
              </span>
            )}
          </div>

          <div className="grid min-[1100px]:grid-cols-[minmax(0,1fr)_360px] gap-4 items-start">
            <div className="border border-proto-line rounded-[10px] overflow-hidden bg-white min-w-0">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-sm">
                  <thead>
                    <tr className="bg-proto-soft text-[10px] uppercase tracking-wide text-proto-muted">
                      <th className="text-left px-3 py-2 w-16">Query</th>
                      <th className="text-left px-3 py-2 w-16">Type</th>
                      <th className="text-left px-3 py-2 w-24">Reference</th>
                      <th className="text-left px-3 py-2 w-24">Top-1</th>
                      <th className="text-right px-3 py-2 w-20">Ref. rank</th>
                      <th className="text-center px-2 py-2 w-10">@1</th>
                      <th className="text-center px-2 py-2 w-10">@3</th>
                      <th className="text-center px-2 py-2 w-10">@5</th>
                      <th className="text-center px-2 py-2 w-10">@10</th>
                      <th className="text-right px-3 py-2 w-20">Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredResults.map((result) => {
                      const selected = result.query_key === selectedQueryKey;
                      const failed = result.status === "failed";
                      const incomplete =
                        result.status !== "completed" && result.status !== "failed";
                      return (
                        <tr
                          key={result.id}
                          role="button"
                          tabIndex={0}
                          aria-pressed={selected}
                          onClick={() => setSelectedQueryKey(result.query_key)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              setSelectedQueryKey(result.query_key);
                            }
                          }}
                          className={`border-t border-proto-line cursor-pointer align-middle outline-none focus:bg-proto-soft ${
                            selected
                              ? "bg-proto-cream-strong"
                              : "hover:bg-proto-soft/70"
                          }`}
                        >
                          <td className="px-3 py-2 font-mono font-bold text-proto-ink whitespace-nowrap">
                            {result.query_key}
                          </td>
                          <td className="px-3 py-2">
                            <span className="text-[9.5px] font-extrabold px-2 py-0.5 rounded-full bg-proto-dark text-proto-canvas">
                              {result.task_type}
                            </span>
                          </td>
                          <td className="px-3 py-2 font-mono text-[12px] text-proto-ink whitespace-nowrap">
                            {result.reference_video}
                          </td>
                          <td className="px-3 py-2 font-mono text-[12px] whitespace-nowrap">
                            {failed ? (
                              <span className="text-[#c64545] font-bold">Failed</span>
                            ) : incomplete ? (
                              <span className="text-proto-muted capitalize">
                                {result.status}…
                              </span>
                            ) : (
                              result.predicted_top1_video ?? "—"
                            )}
                          </td>
                          <td
                            className={`px-3 py-2 text-right font-mono text-[12px] ${
                              result.status === "completed" &&
                              result.reference_video_rank === null
                                ? "text-[#c64545]"
                                : result.reference_video_rank !== null &&
                                  result.reference_video_rank > 10
                                ? "text-[#c64545]"
                                : result.reference_video_rank !== null &&
                                  result.reference_video_rank >= 4
                                ? "text-[#8a6a0f]"
                                : "text-proto-ink"
                            }`}
                          >
                            {result.reference_video_rank ?? "—"}
                          </td>
                          <td className="px-2 py-2 text-center">{hitCell(result.hit_at_1)}</td>
                          <td className="px-2 py-2 text-center">{hitCell(result.hit_at_3)}</td>
                          <td className="px-2 py-2 text-center">{hitCell(result.hit_at_5)}</td>
                          <td className="px-2 py-2 text-center">{hitCell(result.hit_at_10)}</td>
                          <td className="px-3 py-2 text-right font-mono text-[12px] text-proto-muted whitespace-nowrap">
                            {formatSeconds(result.total_ms)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {filteredResults.length === 0 && (
                <div className="px-4 py-8 text-center text-[12px] text-proto-muted border-t border-proto-line">
                  No queries match this filter.
                </div>
              )}
            </div>

            <EvaluationDetail
              result={selectedResult}
              translationPolicy={run.configuration?.translation_policy ?? null}
            />
          </div>
        </div>
      )}
    </div>
  );
}
