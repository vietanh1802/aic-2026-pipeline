import { useEffect, useState } from "react";

import {
  previewExport,
  validateExport,
  type ExportIssue,
} from "../api/answers";
import { API_BASE_URL, ApiRequestError } from "../api/base";
import { getBoard, type BoardResponse } from "../api/board";
import Button from "../components/Button";
import { useAuthStore } from "../store/authStore";

/**
 * Validate, look at one file, download the round.
 *
 * The Google Sheets path lives here too rather than inside the video popup:
 * exporting is a whole-round action, and the popup is about one frame.
 */
export default function ExportPage() {
  const token = useAuthStore((state) => state.token);
  const [board, setBoard] = useState<BoardResponse | null>(null);
  const [issues, setIssues] = useState<ExportIssue[] | null>(null);
  const [ready, setReady] = useState<boolean | null>(null);
  const [preview, setPreview] = useState<{
    filename: string;
    rows: number;
    content: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void getBoard()
      .then(setBoard)
      .catch(() => undefined);
  }, []);

  const packId = board?.round?.id ?? null;

  const check = async () => {
    if (!packId) return;
    setBusy(true);
    try {
      const result = await validateExport(packId);
      setIssues(result.issues);
      setReady(result.ready);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Không kiểm được");
    } finally {
      setBusy(false);
    }
  };

  const look = async (taskId: number) => {
    try {
      setPreview(await previewExport(taskId));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Không xem được");
    }
  };

  // The zip is a plain GET, but it still needs the bearer token, so it goes
  // through fetch and a blob rather than a bare link.
  const download = async () => {
    if (!packId) return;
    setBusy(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/export/zip?pack_id=${packId}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!response.ok) {
        throw new ApiRequestError(response.status, `HTTP ${response.status}`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${board?.round?.label ?? "submission"}.zip`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Không tải được");
    } finally {
      setBusy(false);
    }
  };

  if (board && !board.round) {
    return (
      <div className="max-w-[1200px] mx-auto p-8 font-baloo">
        <h2 className="text-2xl text-proto-ink mb-2">Chưa có gì để xuất</h2>
        <p className="text-sm text-proto-muted">Nhập gói truy vấn trước đã.</p>
      </div>
    );
  }

  return (
    <div className="max-w-[1200px] mx-auto p-6 font-baloo">
      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <h2 className="text-2xl text-proto-ink">Xuất bài</h2>
        <span className="text-xs font-mono text-proto-muted">
          {board?.round?.label}
        </span>
        <span className="ml-auto flex gap-2">
          <Button variant="outline" disabled={busy} onClick={() => void check()}>
            Kiểm tra
          </Button>
          <Button disabled={busy || !packId} onClick={() => void download()}>
            Tải zip
          </Button>
        </span>
      </div>

      {error && <p className="text-[#c64545] text-sm mb-3">{error}</p>}

      {ready !== null && (
        <div className="border border-proto-line rounded-[10px] bg-white mb-5 overflow-hidden">
          <div className="px-4 py-2 bg-proto-soft text-sm">
            {ready ? (
              <b className="text-[#3d7a4d]">Không có cảnh báo nào.</b>
            ) : (
              <b className="text-proto-ink">{issues?.length} cảnh báo</b>
            )}
          </div>
          {issues?.map((issue, index) => (
            <div
              key={index}
              className="px-4 py-1.5 border-t border-proto-line text-sm flex gap-3"
            >
              <span className="font-mono font-bold text-proto-ink w-10">
                {issue.task_code}
              </span>
              <span
                className={
                  issue.severity === "warning"
                    ? "text-[#8a5a15]"
                    : "text-proto-muted"
                }
              >
                {issue.message}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-5">
        <div className="border border-proto-line rounded-[10px] bg-white overflow-hidden">
          <div className="px-4 py-2 bg-proto-soft text-[10px] font-bold uppercase tracking-wide text-proto-muted">
            Xem trước một file
          </div>
          <div className="p-3 max-h-[320px] overflow-y-auto">
            <div className="flex flex-wrap gap-1 mb-3">
              {board?.tasks.map((task) => (
                <button
                  key={task.id}
                  type="button"
                  onClick={() => void look(task.id)}
                  className="text-[11px] font-mono px-2 py-0.5 rounded border border-proto-line text-proto-muted hover:border-proto-primary"
                >
                  {task.code}
                </button>
              ))}
            </div>
            {preview && (
              <>
                <div className="text-xs font-mono text-proto-ink mb-1">
                  {preview.filename} · {preview.rows} dòng
                </div>
                <pre className="text-[11px] font-mono bg-proto-soft border border-proto-line rounded p-2 overflow-x-auto whitespace-pre">
                  {preview.content.split("\n").slice(0, 12).join("\n")}
                  {preview.content.split("\n").length > 12 ? "\n…" : ""}
                </pre>
              </>
            )}
          </div>
        </div>

        <div className="border border-proto-line rounded-[10px] bg-white overflow-hidden">
          <div className="px-4 py-2 bg-proto-soft text-[10px] font-bold uppercase tracking-wide text-proto-muted">
            Google Sheets
          </div>
          <div className="p-4 text-sm text-proto-muted leading-relaxed">
            Đường nộp qua Google Sheets vẫn giữ. Nó cần ba biến môi trường{" "}
            <span className="font-mono text-xs">VITE_GOOGLE_CLIENT_ID</span>,{" "}
            <span className="font-mono text-xs">VITE_GOOGLE_API_KEY</span>,{" "}
            <span className="font-mono text-xs">VITE_DRIVE_FOLDER_ID</span>. Ba
            giá trị cũ đã nằm trong git history nên phải coi là đã lộ và thu hồi
            ở Google Cloud Console.
          </div>
        </div>
      </div>
    </div>
  );
}
