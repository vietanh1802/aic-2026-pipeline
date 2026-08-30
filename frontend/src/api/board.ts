import { apiFetch } from "./base";

export interface Person {
  id: number;
  username: string;
  display_name: string;
  role: "admin" | "member";
}

export interface BoardTask {
  id: number;
  pack_id: number;
  code: string;
  type: "kis" | "qa" | "trake";
  query_text: string;
  question_text: string | null;
  n_events: number | null;
  event_labels: string[];
  owner: Person | null;
  answer_count: number;
  verified_count: number;
  updated_at: string | null;
  claimed_at: string | null;
  version: number;
  viewers: { id: number; display_name: string; last_seen_at: string }[];
}

export interface BoardRound {
  id: number;
  label: string;
  source_filename: string;
  /** False when looking at a retired round rather than the live one. */
  active: boolean;
  deadline_at: string | null;
  server_time: string;
  rows_per_query: number;
}

export interface BoardResponse {
  round: BoardRound | null;
  tasks: BoardTask[];
  me: Person | null;
}

export function getBoard(packId?: number): Promise<BoardResponse> {
  const query = packId === undefined ? "" : `?pack_id=${packId}`;
  return apiFetch<BoardResponse>(`/api/board${query}`);
}

export function claimTask(taskId: number): Promise<{ task: BoardTask }> {
  return apiFetch<{ task: BoardTask }>(`/api/tasks/${taskId}/claim`, {
    method: "POST",
  });
}

export function releaseTask(taskId: number): Promise<{ task: BoardTask }> {
  return apiFetch<{ task: BoardTask }>(`/api/tasks/${taskId}/release`, {
    method: "POST",
  });
}

export function heartbeat(taskId: number | null): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>("/api/presence", {
    method: "POST",
    body: JSON.stringify({ task_id: taskId }),
  });
}

// ── Pack import ──────────────────────────────────────────────────────────────

export interface PreviewedFile {
  filename: string;
  matched: boolean;
  error: string | null;
  phase: string | null;
  code: string | null;
  type: "kis" | "qa" | "trake" | null;
  query_text: string;
  question_text: string | null;
  n_events: number | null;
  event_labels: string[];
  warnings: string[];
  lines: number;
}

export interface PreviewResponse {
  preview_token: string;
  source_filename: string;
  files: PreviewedFile[];
}

export const DEFAULT_PATTERN =
  "query-(?P<phase>p\\d+)-(?P<code>\\d+)-(?P<type>kis|qa|trake)\\.txt";

export function previewPack(
  file: File,
  filenamePattern: string
): Promise<PreviewResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("filename_pattern", filenamePattern);
  // No Content-Type here on purpose — apiFetch leaves it off for FormData so the
  // browser can supply the multipart boundary.
  return apiFetch<PreviewResponse>("/api/admin/packs/preview", {
    method: "POST",
    body: form,
  });
}

export function commitPack(payload: {
  preview_token: string;
  round_label: string;
  filename_pattern: string;
  source_filename: string;
  edits: { filename: string; question_text: string | null }[];
}): Promise<{
  pack_id: number;
  round_label: string;
  tasks_created: number;
  skipped: number;
  /** Always false — a new round goes live only from the rounds screen. */
  active: boolean;
}> {
  return apiFetch("/api/admin/packs/commit", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ── Rounds (admin) ───────────────────────────────────────────────────────────
//
// Importing creates a round; it no longer decides which one the team works in.
// That is what these are for.

export interface RoundPack {
  id: number;
  label: string;
  source_filename: string;
  imported_at: string;
  imported_by: Person | null;
  deadline_at: string | null;
  active: boolean;
  /** Non-null means soft-deleted: hidden everywhere, restorable, nothing lost. */
  deleted_at: string | null;
  task_count: number;
  answer_count: number;
}

export function listPacks(): Promise<{ packs: RoundPack[] }> {
  return apiFetch<{ packs: RoundPack[] }>("/api/admin/packs");
}

export function activatePack(packId: number): Promise<{ pack: RoundPack }> {
  return apiFetch<{ pack: RoundPack }>(`/api/admin/packs/${packId}/activate`, {
    method: "POST",
  });
}

export function patchPack(
  packId: number,
  // An empty deadline_at clears the countdown; omitting it leaves it alone.
  payload: { round_label?: string; deadline_at?: string }
): Promise<{ pack: RoundPack }> {
  return apiFetch<{ pack: RoundPack }>(`/api/admin/packs/${packId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deletePack(packId: number): Promise<{ pack: RoundPack }> {
  return apiFetch<{ pack: RoundPack }>(`/api/admin/packs/${packId}`, {
    method: "DELETE",
  });
}

export function restorePack(packId: number): Promise<{ pack: RoundPack }> {
  return apiFetch<{ pack: RoundPack }>(`/api/admin/packs/${packId}/restore`, {
    method: "POST",
  });
}

// ── Audit ────────────────────────────────────────────────────────────────────

export interface AuditEntry {
  id: number;
  at: string;
  action: string;
  target: string;
  summary: string;
  by: { id: number; username: string; display_name: string };
  /** Rows this entry can put back. 0 means nothing to restore. */
  restorable: number;
  restored_at: string | null;
}

export function getAudit(limit = 100): Promise<{ entries: AuditEntry[] }> {
  return apiFetch<{ entries: AuditEntry[] }>(`/api/admin/audit?limit=${limit}`);
}

export function restoreFromAudit(
  entryId: number
): Promise<{ restored: number; skipped: number }> {
  return apiFetch(`/api/admin/audit/${entryId}/restore`, { method: "POST" });
}
