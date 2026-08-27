import { useCallback, useEffect, useState } from "react";

import { deleteAnswer, getAnswers, type AnswerRow } from "../../api/answers";
import { ApiRequestError } from "../../api/base";
import type { BoardTask } from "../../api/board";
import Button from "../Button";
import FramePreview from "../FramePreview";
import { useAuthStore } from "../../store/authStore";
import { usePopupStore } from "../../store/popupStore";

/**
 * The task's real answers, beside the video, refreshed the moment one is added.
 *
 * The panel this replaces rendered the Zustand basket, while `SubmitForm` — for
 * any task opened from the board — writes through `addAnswer()` to the server
 * and never touches that store. So the list sat there unchanged after every
 * click, and the only way to confirm an answer had landed was to close the
 * popup and open the basket. Reading the same source the button writes to is
 * the whole fix; `reloadKey` is how the popup says "I just added one".
 */
export default function AnswerPanel({
  task,
  reloadKey,
  onChanged,
}: {
  task: BoardTask;
  /** Bumped by the popup after every successful add. */
  reloadKey: number;
  onChanged: () => void;
}) {
  const me = useAuthStore((state) => state.user);
  const openPopup = usePopupStore((state) => state.open);
  const readOnly = Boolean(task.owner) && task.owner?.id !== me?.id;
  const [rows, setRows] = useState<AnswerRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [hovered, setHovered] = useState<AnswerRow | null>(null);

  const reload = useCallback(async () => {
    try {
      setRows((await getAnswers(task.id)).answers);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Không tải được");
    }
  }, [task.id]);

  useEffect(() => {
    void reload();
  }, [reload, reloadKey]);

  const last = rows[rows.length - 1];

  const removeLast = async () => {
    if (!last) return;
    setBusy(true);
    try {
      await deleteAnswer(last.id);
      await reload();
      onChanged();
      setError(null);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Không xoá được");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative w-1/5 h-[70%] bg-white rounded-sm p-4 shadow-lg flex flex-col font-baloo">
      <div className="flex items-center justify-between mb-2">
        <b className="text-sm text-proto-ink font-mono">Task {task.code}</b>
        <span className="font-mono text-sm text-proto-ink">{rows.length}</span>
      </div>

      {error && <p className="text-[#c64545] text-xs mb-2">{error}</p>}

      <div className="flex-1 overflow-y-auto">
        {rows.length === 0 && (
          <p className="text-xs text-proto-muted">
            Chưa có dòng nào. Bấm <b>Add Answer</b> để thêm.
          </p>
        )}
        {rows.map((row, index) => (
          <div
            key={row.id}
            className={`group relative flex items-baseline gap-2 px-1.5 py-1 rounded-[6px] border border-proto-line mb-1 text-[11px] cursor-pointer ${
              index === 0 ? "bg-proto-primary/10" : "bg-proto-soft"
            }`}
            onClick={() => openPopup(row.video_id, row.frames[0])}
            onMouseEnter={() => setHovered(row)}
            onMouseLeave={() => setHovered(null)}
            title={
              row.origin === "auto"
                ? "Dòng tự sinh"
                : `Thêm bởi ${row.created_by?.display_name ?? "—"}`
            }
          >
            <FramePreview videoId={row.video_id} frameIdx={row.frames[0]} />
            <i className="not-italic w-5 text-right font-mono font-extrabold text-proto-muted">
              {row.rank}
            </i>
            <span className="font-mono text-proto-muted">{row.video_id}</span>
            <span className="font-mono text-proto-ink font-semibold">
              {row.frames.join(" · ")}
            </span>
          </div>
        ))}
      </div>

      {hovered && (
        <div className="pointer-events-none absolute right-full top-0 z-[1000] mr-2">
          <FramePreview
            videoId={hovered.video_id}
            frameIdx={hovered.frames[0]}
            size="large"
            className="shadow-2xl border-2 border-white"
          />
        </div>
      )}

      <div className="flex justify-end mt-3">
        {readOnly ? (
          <span className="text-[11px] text-proto-muted">
            Giỏ của {task.owner?.display_name} — chỉ đọc
          </span>
        ) : (
          <Button size="xs" disabled={busy || !last} onClick={() => void removeLast()}>
            Xoá dòng cuối
          </Button>
        )}
      </div>
    </div>
  );
}
