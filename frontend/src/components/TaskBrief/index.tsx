import { useState, type ReactNode } from "react";

import type { BoardTask } from "../../api/board";
import { expandQuery, type ExpansionResult } from "../../api/expansion";
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
  trailing,
}: {
  task: BoardTask;
  variant?: "page" | "popup";
  /**
   * Thêm vào cuối khối, BÊN TRONG phần dính.
   *
   * Có mặt vì popup video cần thẻ "đang chốt mốc E mấy" đi theo khi cuộn, mà
   * khối này đã dính sẵn ở `top-0`. Cách còn lại là cho thẻ đó tự dính với
   * `top` bằng đúng chiều cao khối này — một con số phải đo bằng ref và đo
   * lại mỗi lần bấm "Mở rộng". Cho nó vào chung thì không có con số nào để
   * sai.
   */
  trailing?: ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  const isPopup = variant === "popup";

  // Expand: đề bài → câu EN đã mở rộng, ghi thẳng xuống ô search (cùng cơ chế
  // với nút "Chép đề bài" bên cạnh), và treo kèm check_units dưới đề để phân
  // tích lúc soi kết quả. Chỉ làm ở biến thể page — trong popup người ta đang
  // xem video, không phải đang soạn truy vấn.
  const [expansion, setExpansion] = useState<ExpansionResult | null>(null);
  const [expanding, setExpanding] = useState(false);
  const [expandError, setExpandError] = useState<string | null>(null);

  const handleExpand = async () => {
    if (expanding || !task.query_text) return;
    setExpanding(true);
    setExpandError(null);
    try {
      const result = await expandQuery(
        task.query_text,
        task.type.toUpperCase()
      );
      useQueryStore.getState().setQueryText(result.eng_query);
      setExpansion(result);
    } catch (err) {
      setExpandError(
        err instanceof Error ? err.message : "Không mở rộng được đề bài"
      );
    } finally {
      setExpanding(false);
    }
  };

  return (
    <div
      className={
        isPopup
          ? "sticky top-0 z-20 -mx-6 -mt-6 mb-3 px-6 py-3 bg-white border-b-2 border-proto-primary/40 font-baloo"
          : // top theo chiều cao thật của thanh nav, không phải 0: nav giờ cũng
            // dính, nên top-0 sẽ khiến hai khối chồng lên nhau. z thấp hơn nav
            // vì nav phải nằm trên cùng.
            "sticky top-[var(--nav-h)] z-40 max-w-[98%] mx-auto mb-3 px-4 py-3 rounded-[10px] bg-proto-card border-l-4 border-l-proto-primary border border-proto-line font-baloo shadow-sm"
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
          <>
            <button
              type="button"
              className="text-[12.5px] text-proto-primary-active underline"
              onClick={handleExpand}
              disabled={expanding}
              title="Dịch + mở rộng đề bài (Gemini, fallback Ollama local) rồi chép xuống ô search"
            >
              {expanding ? "Đang mở rộng..." : "Expand"}
            </button>
            <button
              type="button"
              className="text-[12.5px] text-proto-primary-active underline"
              onClick={() =>
                useQueryStore.getState().setQueryText(taskQueryForSearch(task))
              }
            >
              Chép đề bài xuống ô search
            </button>
          </>
        )}
      </div>

      <div
        className={`text-[16px] text-proto-ink leading-snug whitespace-pre-wrap font-medium ${
          expanded ? "" : "line-clamp-2"
        }`}
      >
        {task.query_text}
      </div>

      {/* Sản phẩm của nút Expand: check_units để soi bằng mắt khi phân tích kết
          quả tìm kiếm, kèm nhãn provider để biết đường nào đang phục vụ
          (gemini hay fallback ollama). Chỉ hiện sau khi bấm — không phải
          thành phần cố định của đề bài. */}
      {expandError && (
        <p className="text-[12.5px] text-red-600 leading-snug mt-1">
          {expandError}
        </p>
      )}
      {!expandError && expansion && (
        <div className="mt-1">
          <p
            className="text-[12.5px] text-proto-muted leading-snug"
            title={expansion.check_units.join(", ")}
          >
            {`Check units (${expansion.provider}, ${
              expansion.elapsed_ms
            }ms): ${expansion.check_units.join(", ")}`}
          </p>
        </div>
      )}

      {/* Dãy chip E1..EN đã bỏ.

          Nó vẽ `task.event_labels`, mà cột đó do trình đọc gói tách ra từ đề
          bài bằng regex `^E(\d+)[:.]`. Trình đọc thôi tách — đề bài giờ vào
          nguyên văn và nằm trọn trong khối chữ ngay trên — nên `event_labels`
          luôn rỗng và khối này không bao giờ vẽ gì.

          Các mốc vẫn đọc được: chúng nằm nguyên trong đề bài. Bấm "Mở rộng"
          để thấy đủ thay vì hai dòng bị cắt. */}

      {trailing && <div className="mt-2">{trailing}</div>}
    </div>
  );
}
