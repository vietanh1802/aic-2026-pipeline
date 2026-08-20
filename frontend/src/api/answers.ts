import { apiFetch } from "./base";
import type { Person } from "./board";

export interface AnswerRow {
  id: number;
  task_id: number;
  rank: number;
  video_id: string;
  frames: number[];
  answer_text: string | null;
  origin: "auto" | "manual";
  created_by: Person | null;
  updated_by: Person | null;
  updated_at: string;
  version: number;
}

export function getAnswers(taskId: number): Promise<{ answers: AnswerRow[] }> {
  return apiFetch(`/api/tasks/${taskId}/answers`);
}

export function addAnswer(
  taskId: number,
  payload: {
    video_id: string;
    frames: number[];
    answer_text?: string | null;
    position?: "top" | { after_id: number };
  }
): Promise<{ answer: AnswerRow }> {
  return apiFetch(`/api/tasks/${taskId}/answers`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function patchAnswer(
  answerId: number,
  payload: Partial<Pick<AnswerRow, "video_id" | "frames" | "answer_text">> & {
    version: number;
  }
): Promise<{ answer: AnswerRow }> {
  return apiFetch(`/api/answers/${answerId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteAnswer(answerId: number): Promise<{ ok: boolean }> {
  return apiFetch(`/api/answers/${answerId}`, { method: "DELETE" });
}

/**
 * Empties one task's basket, manual pins included.
 *
 * Not the same as autofill's `clear`, which spares the manual rows so the
 * spread can be redone with a different step. This is the export screen's
 * "start this query over".
 */
export function clearAnswers(
  taskId: number
): Promise<{ removed: number; total: number }> {
  return apiFetch(`/api/tasks/${taskId}/answers`, { method: "DELETE" });
}

export function reorderAnswer(
  taskId: number,
  payload: { answer_id: number; before_id?: number; after_id?: number }
): Promise<{ answers: AnswerRow[] }> {
  return apiFetch(`/api/tasks/${taskId}/answers/reorder`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function autofillAnswers(
  taskId: number,
  payload: {
    limit?: number;
    step?: number;
    // clear drops the generated rows and stops; replace_auto drops and refills
    // in one call, which reads as a no-op from the UI.
    mode?: "append" | "replace_auto" | "clear";
  }
): Promise<{ added: number; removed?: number; total: number }> {
  return apiFetch(`/api/tasks/${taskId}/answers/autofill`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ── Export ───────────────────────────────────────────────────────────────────

export interface ExportIssue {
  task_code: string;
  severity: "warning" | "info";
  message: string;
}

export function validateExport(
  packId: number
): Promise<{ ready: boolean; issues: ExportIssue[] }> {
  return apiFetch(`/api/export/validate?pack_id=${packId}`);
}

export function previewExport(taskId: number): Promise<{
  filename: string;
  rows: number;
  bytes: number;
  content: string;
}> {
  return apiFetch(`/api/export/preview?task_id=${taskId}`);
}

export function exportZipUrl(packId: number): string {
  return `/api/export/zip?pack_id=${packId}`;
}
