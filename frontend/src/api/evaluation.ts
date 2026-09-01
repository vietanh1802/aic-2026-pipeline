import { apiFetch } from "./base";

export type EvaluationRunStatus =
  | "queued"
  | "running"
  | "cancelling"
  | "completed"
  | "partial"
  | "cancelled"
  | "interrupted"
  | "failed";

export type EvaluationResultStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "interrupted";

export interface EvaluationTranslationPolicy {
  id: string;
  label: string;
  description: string;
}

export interface EvaluationReferenceSet {
  id: number;
  version: string;
  label_semantics: string | null;
  interval_annotation: string | null;
  notes: string | null;
  created_at: string;
}

export interface EvaluationDataset {
  id: number;
  slug: string;
  version: string;
  display_name: string;
  query_count: number;
  source_filename: string;
  source_sha256: string;
  created_at: string;
  reference_sets: EvaluationReferenceSet[];
}

export interface EvaluationDatasetQuery {
  id: number;
  query_key: string;
  ordinal: number;
  task_type: string;
  query_vi: string;
}

export interface EvaluationDatasetDetail extends EvaluationDataset {
  queries: EvaluationDatasetQuery[];
}

export interface EvaluationConfiguration {
  models?: string[];
  top_k?: number;
  top_m?: number;
  use_rerank?: boolean;
  translation_policy?: string;
  [key: string]: unknown;
}

export interface EvaluationRuntime {
  version?: string;
  commit?: string;
  device?: string | null;
  active_models?: string[] | null;
  ensemble_weights?: Record<string, number> | null;
  index_files?: unknown;
  stale_files?: unknown;
  error?: string;
  [key: string]: unknown;
}

export interface EvaluationSummary {
  total_queries: number;
  completed_queries: number;
  failed_queries: number;
  top1_accuracy: number;
  recall_at_3: number;
  recall_at_5: number;
  recall_at_10: number;
  mrr: number;
  median_reference_rank: number | null;
  not_retrieved_count: number;
  p50_ms: number | null;
  p95_ms: number | null;
  max_ms: number | null;
  within_10s_rate: number;
}

export interface EvaluationFrameRoute {
  rank?: number;
  score?: number;
  [key: string]: unknown;
}

export interface EvaluationFrameResult {
  frame?: string;
  name?: string;
  url?: string;
  distance?: number;
  video?: string | null;
  video_id?: string | null;
  frame_idx?: number | null;
  timestamp?: string;
  routes?: Record<string, EvaluationFrameRoute>;
  has_image?: boolean;
  [key: string]: unknown;
}

export interface EvaluationRankedVideo {
  rank: number;
  video_id: string;
  best_frame_rank: number;
  frames: EvaluationFrameResult[];
}

export interface EvaluationRun {
  id: number;
  dataset_id: number;
  dataset_version: string;
  reference_set_id: number;
  reference_set_version: string;
  strategy: string;
  video_ranking_policy: string;
  translator: string;
  status: EvaluationRunStatus;
  query_count: number;
  completed_count: number;
  failed_count: number;
  created_by_user_id: number | null;
  configuration: EvaluationConfiguration | null;
  runtime: EvaluationRuntime | null;
  summary: EvaluationSummary | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
  resume_count: number;
}

export interface EvaluationResult {
  id: number;
  run_id: number;
  query_id: number;
  query_key: string;
  ordinal: number;
  task_type: string;
  status: EvaluationResultStatus;
  query_vi: string;
  query_en: string | null;
  translator: string;
  reference_video: string;
  reference_frame_idx: number | null;
  predicted_top1_video: string | null;
  reference_video_rank: number | null;
  hit_at_1: boolean | null;
  hit_at_3: boolean | null;
  hit_at_5: boolean | null;
  hit_at_10: boolean | null;
  reciprocal_rank: number | null;
  not_retrieved: boolean | null;
  translation_ms: number | null;
  retrieval_ms: number | null;
  aggregation_ms: number | null;
  total_ms: number | null;
  frame_results: EvaluationFrameResult[] | null;
  ranked_videos: EvaluationRankedVideo[] | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export function listEvaluationTranslationPolicies(): Promise<{
  default: string;
  policies: EvaluationTranslationPolicy[];
}> {
  return apiFetch("/api/admin/evaluation/translation-policies");
}

export function listEvaluationDatasets(): Promise<{
  datasets: EvaluationDataset[];
}> {
  return apiFetch("/api/admin/evaluation/datasets");
}

export function getEvaluationDataset(
  datasetId: number
): Promise<{ dataset: EvaluationDatasetDetail }> {
  return apiFetch(`/api/admin/evaluation/datasets/${datasetId}`);
}

export function createEvaluationRun(payload: {
  dataset_version: string;
  reference_set_version: string;
  translation_policy: string;
}): Promise<{ run: EvaluationRun }> {
  return apiFetch("/api/admin/evaluation/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listEvaluationRuns(
  limit = 50
): Promise<{ runs: EvaluationRun[] }> {
  return apiFetch(`/api/admin/evaluation/runs?limit=${limit}`);
}

export function getEvaluationRun(
  runId: number
): Promise<{ run: EvaluationRun }> {
  return apiFetch(`/api/admin/evaluation/runs/${runId}`);
}

export function getEvaluationResults(
  runId: number
): Promise<{ results: EvaluationResult[] }> {
  return apiFetch(`/api/admin/evaluation/runs/${runId}/results`);
}

export function getEvaluationResult(
  runId: number,
  queryKey: string
): Promise<{ result: EvaluationResult }> {
  return apiFetch(
    `/api/admin/evaluation/runs/${runId}/results/${encodeURIComponent(queryKey)}`
  );
}

export function cancelEvaluationRun(
  runId: number
): Promise<{ run: EvaluationRun }> {
  return apiFetch(`/api/admin/evaluation/runs/${runId}/cancel`, {
    method: "POST",
  });
}

export function resumeEvaluationRun(
  runId: number
): Promise<{ run: EvaluationRun }> {
  return apiFetch(`/api/admin/evaluation/runs/${runId}/resume`, {
    method: "POST",
  });
}
