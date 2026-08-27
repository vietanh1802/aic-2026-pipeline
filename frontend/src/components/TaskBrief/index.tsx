import { useState } from "react";

import type { BoardTask } from "../../api/board";
import { taskQueryForSearch } from "../../helpers/taskBrief";
import { useQueryStore } from "../../store/queryStore";

/**
 * The open task's brief, verbatim and read-only. Never translated, never mixed
 * with what the user types into the search box.
 *
 * Rendered in two places for two different reasons, which is why it is a
 * component rather than markup inside the search screen:
 *
 *  - `page` pins itself to the top of the search screen, so scrolling through a
 *    hundred results does not scroll the question away.
 *  - `popup` repeats it inside the video popup. Pinning alone cannot help
 *    there: the popup is a `fixed inset-0` overlay covering the whole viewport,
 *    so anything on the page behind it is hidden no matter where it sits.
 *
 * Both clamp to two lines and expand on click. The brief is the one thing
 * always worth a glance and rarely worth the whole screen.
 */
export default function TaskBrief({
  task,
  variant = "page",
}: {
  task: BoardTask;
  variant?: "page" | "popup";
}) {
  const [expanded, setExpanded] = useState(false);
  const isPopup = variant === "popup";

  return (
    <div
      className={
        isPopup
          ? "sticky top-0 z-20 -mx-6 -mt-6 mb-3 px-6 py-3 bg-white border-b-2 border-proto-primary/40 font-baloo"
          : "sticky top-0 z-[100] max-w-[98%] mx-auto mb-3 px-4 py-3 rounded-[10px] bg-proto-card border-l-4 border-l-proto-primary border border-proto-line font-baloo shadow-sm"
      }
    >
      <div className="flex items-center gap-2 mb-1 flex-wrap">
        <span
          className="text-[11px] font-extrabold px-2.5 py-0.5 rounded-full bg-proto-dark text-proto-canvas"
        >
          {task.type === "qa" ? "Q&A" : task.type.toUpperCase()}
        </span>
        <b
          className="text-[15px] text-proto-ink font-mono"
        >
          Task {task.code}
        </b>

        <button
          type="button"
          className="text-[12.5px] text-proto-muted underline ml-auto"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "Thu gọn" : "Mở rộng"}
        </button>

        {!isPopup && (
          <button
            type="button"
            className="text-[12.5px] text-proto-primary-active underline"
            onClick={() =>
              useQueryStore.getState().setQueryText(taskQueryForSearch(task))
            }
          >
            Chép đề bài xuống ô search
          </button>
        )}
      </div>

      <div
        className={`text-[16px] text-proto-ink leading-snug whitespace-pre-wrap font-medium ${
          expanded ? "" : "line-clamp-2"
        }`}
      >
        {task.query_text}
      </div>

      {task.event_labels.length > 0 && (
        <div
          className={
            isPopup ? "flex flex-wrap gap-1 mt-1.5" : "flex flex-col gap-1 mt-2"
          }
        >
          {task.event_labels.map((label, index) => (
            <div
              key={index}
              className={`bg-proto-canvas border border-proto-line rounded-[6px] px-2 py-1 ${
                isPopup ? "text-[13px]" : "text-[13.5px]"
              }`}
            >
              <b className="text-proto-primary-active">E{index + 1}</b> {label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
