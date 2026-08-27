import type { AnswerRow } from "../../api/answers";
import type { BoardTask } from "../../api/board";
import type { MarkedRange } from "../../helpers/basketMath";
import BasketBody from "../Basket/BasketBody";

/**
 * The task's real answers, beside the video, refreshed the moment one is added.
 *
 * The panel this replaces rendered the Zustand basket, while `SubmitForm` — for
 * any task opened from the board — writes through `addAnswer()` to the server
 * and never touches that store. So the list sat there unchanged after every
 * click, and the only way to confirm an answer had landed was to close the
 * popup and open the basket. Reading the same source the button writes to is
 * the whole fix; `reloadKey` is how the popup says "I just added one".
 *
 * The row list itself — fetching, autofill, the manual-entry escape hatch —
 * lives in `BasketBody`, shared with the standalone basket dialog.
 */
export default function AnswerPanel({
  task,
  rowsPerQuery,
  reloadKey,
  onRowClick,
  onChanged,
  activeRowId = null,
  markedRange = null,
}: {
  task: BoardTask;
  rowsPerQuery: number;
  /** Bumped by the popup after every successful add. */
  reloadKey: number;
  onRowClick: (row: AnswerRow) => void;
  onChanged: () => void;
  /** The row the user last clicked, highlighted so they know what they are checking. */
  activeRowId?: number | null;
  /** The mark-in/mark-out interval, in frames. Null when either mark is unset. */
  markedRange?: MarkedRange | null;
}) {
  return (
    <div className="relative flex flex-col h-full w-full font-baloo">
      <BasketBody
        task={task}
        rowsPerQuery={rowsPerQuery}
        variant="panel"
        reloadKey={reloadKey}
        onRowClick={onRowClick}
        onChanged={onChanged}
        activeRowId={activeRowId}
        markedRange={markedRange}
      />
    </div>
  );
}
