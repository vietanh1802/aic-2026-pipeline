import type { AnswerRow } from "../../api/answers";
import type { BoardTask } from "../../api/board";
import BasketBody from "../Basket/BasketBody";

/**
 * The dialog chrome around a task's basket: backdrop, box, close button.
 * Everything below that — fetching, autofill, the row list — lives in
 * `BasketBody`, shared with the popup's side panel.
 */
export default function AnswerBasket({
  task,
  rowsPerQuery,
  open,
  onClose,
  onOpenVideo,
}: {
  task: BoardTask | null;
  rowsPerQuery: number;
  open: boolean;
  onClose: () => void;
  onOpenVideo: (videoId: string, frameIdx: number) => void;
}) {
  if (!open || !task) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[999] bg-black/40 flex items-center justify-center p-4">
      <div className="bg-proto-canvas rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col font-baloo">
        <div className="flex items-center justify-end px-5 py-3 border-b border-proto-line">
          <button
            type="button"
            onClick={onClose}
            className="flex h-10 w-10 items-center justify-center text-[#c64545] hover:bg-[#c64545]/15 rounded-full font-bold"
          >
            ×
          </button>
        </div>

        <BasketBody
          task={task}
          rowsPerQuery={rowsPerQuery}
          variant="dialog"
          onRowClick={(row: AnswerRow) => onOpenVideo(row.video_id, row.frames[0])}
        />
      </div>
    </div>
  );
}
