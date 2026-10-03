import { API_BASE_URL, apiFetch } from "./base";
import { useAuthStore } from "../store/authStore";

// The retrieval benchmark. Backend still lives under /api/admin/evaluation —
// only the frontend module name changed, to keep it clearly apart from the
// unrelated team answer-comparison tool at pages/Evaluation.tsx.

export const R_AT_CUTS = [1, 5, 20, 50, 100] as const;

export type RunStatus =
  | "queued"
  | "running"
  | "cancelling"
  | "completed"
  | "partial"
  | "cancelled"
  | "interrupted"
  | "failed";

export type ResultStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "interrupted";

export type TaskType = "KIS" | "QA" | "TRAKE";

export interface TranslationPolicy {
  id: string;
  label: string;
  description: string;
}

export interface ReferenceSet {
  id: number;
  version: string;
  label_semantics: string | null;
  interval_annotation: string | null;
  notes: string | null;
  created_at: string;
}

export interface Dataset {
  id: number;
  slug: string;
  version: string;
  display_name: string;
  query_count: number;
  source_filename: string | null;
  source_sha256: string | null;
  created_at: string;
  reference_sets: ReferenceSet[];
}

export interface DatasetQuery {
  id: number;
  query_key: string;
  ordinal: number;
  task_type: TaskType;
  query_vi: string;
  video_id: string | null;
  interval_count: number | null;
  reference_frame_idx: number | null;
  notes: string | null;
}

export interface DatasetDetail extends Dataset {
  queries: DatasetQuery[];
}

export interface RunConfiguration {
  models?: string[];
  top_k?: number;
  top_m?: number;
  use_rerank?: boolean;
  translation_policy?: string;
  [key: string]: unknown;
}

export interface RunRuntime {
  version?: string;
  commit?: string;
  device?: string | null;
  active_models?: string[] | null;
  ensemble_weights?: Record<string, number> | null;
  stale_files?: string[] | null;
  index_files?: unknown;
  error?: string;
  [key: string]: unknown;
}

/** {"1": rate, "5": rate, ...} keyed by the R@k cut-offs. */
export type RAt = Record<string, number>;

export interface IntervalMetrics {
  final_score: number;
  r_at: RAt;
  interval_hit_rate: number;
  video_hit_interval_miss: number;
}

export interface VideoMetrics {
  total: number;
  completed: number;
  failed: number;
  hit_at_1: number;
  recall_at_3: number;
  recall_at_5: number;
  recall_at_10: number;
  mrr: number;
  median_reference_rank: number | null;
  not_retrieved_count: number;
}

export interface LatencyMetrics {
  p50_ms: number | null;
  p95_ms: number | null;
  max_ms: number | null;
  within_10s_rate: number;
}

export interface RunHeadline {
  total_queries: number;
  scored_queries: number;
  final_score_kis_qa: number;
  final_score_kis: number;
  r_at_kis_qa: RAt;
  r_at_kis: RAt;
  interval: IntervalMetrics;
  video: VideoMetrics;
  latency: LatencyMetrics;
}

export interface TaskTypeSummary {
  KIS: { video: VideoMetrics; interval: IntervalMetrics };
  QA: { video: VideoMetrics; interval: IntervalMetrics };
  TRAKE: { scoring_tier: 0; video: VideoMetrics };
}

export interface BenchmarkRun {
  id: number;
  dataset_id: number;
  dataset_version: string;
  reference_set_id: number;
  reference_set_version: string;
  strategy: string;
  video_ranking_policy: string;
  interval_scoring_policy: string;
  translator: string;
  status: RunStatus;
  query_count: number;
  completed_count: number;
  failed_count: number;
  created_by_user_id: number | null;
  configuration: RunConfiguration | null;
  runtime: RunRuntime | null;
  summary: RunHeadline | null;
  task_type_summary: TaskTypeSummary | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
  resume_count: number;
}

export interface FrameInterval {
  start: number;
  end: number;
}

export interface FrameResult {
  frame?: string;
  name?: string;
  url?: string;
  distance?: number;
  video?: string | null;
  video_id?: string | null;
  frame_idx?: number | null;
  timestamp?: string;
  has_image?: boolean;
  [key: string]: unknown;
}

export interface RankedVideo {
  rank: number;
  video_id: string;
  best_frame_rank: number;
  frames: FrameResult[];
}

export interface QueryResult {
  id: number;
  run_id: number;
  query_id: number;
  query_key: string;
  ordinal: number;
  task_type: TaskType;
  status: ResultStatus;
  query_vi: string;
  query_en: string | null;
  translator: string;
  reference_video: string;
  reference_intervals: FrameInterval[] | null;
  reference_frame_idx: number | null;
  reference_notes: string;
  predicted_top1_video: string | null;
  reference_video_rank: number | null;
  hit_at_1: boolean | null;
  hit_at_3: boolean | null;
  hit_at_5: boolean | null;
  hit_at_10: boolean | null;
  reciprocal_rank: number | null;
  not_retrieved: boolean | null;
  interval_hit: boolean | null;
  interval_rank: number | null;
  matched_interval_index: number | null;
  final_score: number | null;
  translation_ms: number | null;
  retrieval_ms: number | null;
  aggregation_ms: number | null;
  total_ms: number | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface TrakeEvent {
  event_id: string;
  description_vi: string;
  reference_frame_idx: number | null;
  valid_start_frame: number | null;
  valid_end_frame: number | null;
}

/** Only the single-query endpoint carries the evidence blobs, plus the
 *  reference answer / events, which are shown labelled "not scored". */
export interface QueryResultDetail extends QueryResult {
  frame_results: FrameResult[] | null;
  ranked_videos: RankedVideo[] | null;
  qa_answer: string | null;
  trake_events: TrakeEvent[] | null;
}

export function listTranslationPolicies(): Promise<{
  default: string;
  policies: TranslationPolicy[];
}> {
  return apiFetch("/api/admin/evaluation/translation-policies");
}

export function listDatasets(): Promise<{ datasets: Dataset[] }> {
  return apiFetch("/api/admin/evaluation/datasets");
}

export function getDataset(datasetId: number): Promise<{ dataset: DatasetDetail }> {
  return apiFetch(`/api/admin/evaluation/datasets/${datasetId}`);
}

export function createRun(payload: {
  dataset_version: string;
  reference_set_version: string;
  translation_policy: string;
}): Promise<{ run: BenchmarkRun }> {
  return apiFetch("/api/admin/evaluation/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listRuns(limit = 50): Promise<{ runs: BenchmarkRun[] }> {
  return apiFetch(`/api/admin/evaluation/runs?limit=${limit}`);
}

export function getRun(runId: number): Promise<{ run: BenchmarkRun }> {
  return apiFetch(`/api/admin/evaluation/runs/${runId}`);
}

export function getRunResults(runId: number): Promise<{ results: QueryResult[] }> {
  return apiFetch(`/api/admin/evaluation/runs/${runId}/results`);
}

export function getRunResult(
  runId: number,
  queryKey: string
): Promise<{ result: QueryResultDetail }> {
  return apiFetch(
    `/api/admin/evaluation/runs/${runId}/results/${encodeURIComponent(queryKey)}`
  );
}

export function cancelRun(runId: number): Promise<{ run: BenchmarkRun }> {
  return apiFetch(`/api/admin/evaluation/runs/${runId}/cancel`, { method: "POST" });
}

export function resumeRun(runId: number): Promise<{ run: BenchmarkRun }> {
  return apiFetch(`/api/admin/evaluation/runs/${runId}/resume`, { method: "POST" });
}

// ── ablation suites ─────────────────────────────────────────────────────────
// A suite is a list of runs, one per (configuration, dataset). The report is
// computed on the server from the runs that have results so far.

export interface SuiteSummary {
  suite_id: string;
  name: string | null;
  runs: number;
  created_at: string;
}

export interface SuiteStatus {
  suite_id: string;
  runs: number;
  by_status: Record<string, number>;
  queries_total: number;
  queries_done: number;
  finished: boolean;
}

export interface SuiteDetail {
  suite: SuiteStatus;
  runs: BenchmarkRun[];
}

/** One slice of one configuration: pooled benchmark, flag mode, task type, video prefix. */
export interface SuiteReportRow {
  config: string;
  benchmark: string;
  flags: string;
  task_type: string;
  prefix: string;
  n: number;
  failed: number;
  hit_at_1: number;
  r_at_5: number;
  r_at_10: number;
  mrr: number;
  median_rank: number | null;
  interval_final_score: number | null;
  event_accuracy: number | null;
  event_queries: number | null;
}

export interface SuiteReport {
  configs: string[];
  table: SuiteReportRow[];
}

export interface SuiteSlice {
  benchmark: string;
  flags: string;
  task_type: string;
  prefix: string;
}

export function listSuites(): Promise<{ suites: SuiteSummary[] }> {
  return apiFetch("/api/admin/evaluation/suites");
}

export function startSuite(payload: {
  name: string;
  preset: string;
}): Promise<{ suite: { suite_id: string; run_ids: number[] } }> {
  return apiFetch("/api/admin/evaluation/suites", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getSuite(suiteId: string): Promise<SuiteDetail> {
  return apiFetch(`/api/admin/evaluation/suites/${suiteId}`);
}

export function cancelSuite(suiteId: string): Promise<{ suite: SuiteStatus }> {
  return apiFetch(`/api/admin/evaluation/suites/${suiteId}/cancel`, { method: "POST" });
}

export function resumeSuite(suiteId: string): Promise<{ suite: SuiteStatus }> {
  return apiFetch(`/api/admin/evaluation/suites/${suiteId}/resume`, { method: "POST" });
}

export function getSuiteReport(suiteId: string): Promise<SuiteReport> {
  return apiFetch(`/api/admin/evaluation/suites/${suiteId}/report`);
}

/** The CSV or LaTeX text of a suite's report. apiFetch parses JSON, so this reads the body as text. */
export async function getSuiteReportText(
  suiteId: string,
  format: "csv" | "latex",
  slice: SuiteSlice
): Promise<string> {
  const { token } = useAuthStore.getState();
  const query = new URLSearchParams({
    format,
    benchmark: slice.benchmark,
    flags: slice.flags,
    task_type: slice.task_type,
    prefix: slice.prefix,
  });
  const response = await fetch(
    `${API_BASE_URL}/api/admin/evaluation/suites/${suiteId}/report?${query.toString()}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} }
  );
  if (!response.ok) {
    throw new Error(`Report download failed (HTTP ${response.status})`);
  }
  return response.text();
}
