import { useEffect, useRef } from "react";

import { logout } from "../../api/auth";
import ApiStatus from "../ApiStatus";
import { useSearchStore } from "../../store/useSearchStore";
import GotoFrame from "../GotoFrame";
import type { BoardTask } from "../../api/board";
import type { AuthUser } from "../../types/auth";

export type Screen =
  | "search"
  | "history"
  | "board"
  | "evaluation"
  | "retrieval-benchmark"
  | "import"
  | "export";

// Thứ tự công việc trong một vòng thi, từ trái sang: nhập đề → chọn câu → tìm →
// đọ bài → nộp.
//
// Import đứng đầu vì nó là việc ĐẦU TIÊN của mỗi vòng, và là việc duy nhất phải
// xong trước khi bốn màn còn lại có gì để hiển thị — chưa nhập gói thì Board,
// Evaluation và Export đều chỉ nói "chưa có gói truy vấn". Chỉ admin thấy nó,
// nên với bốn người còn lại thanh này bắt đầu bằng Board.
//
// Board đứng trước Search vì đó là thứ tự thao tác thật: mở một câu từ bảng rồi
// mới đi tìm. Vào thẳng Search khi chưa mở câu nào thì chỉ nhận được dòng "Chưa
// mở task — vào Board để nhận", tức là phải quay lại đúng chỗ vừa đi qua. Root
// cũng mở Board làm màn đầu tiên sau khi đăng nhập.
const NAV: { id: Screen; label: string; adminOnly?: boolean }[] = [
  // "Vòng" đã gộp vào Import: bảng vòng nằm ngay dưới khung thả file, vì
  // nhập gói xong thì việc kế tiếp luôn là kích hoạt nó.
  { id: "import", label: "Import", adminOnly: true },
  { id: "board", label: "Board" },
  { id: "search", label: "Search" },
  { id: "evaluation", label: "Evaluation" },
  { id: "retrieval-benchmark", label: "Benchmark", adminOnly: true },
  { id: "export", label: "Export" },
];

export default function AppNav({
  screen,
  onNavigate,
  user,
  task,
  answerCount,
  rowsPerQuery,
  onOpenBasket,
}: {
  screen: Screen;
  onNavigate: (screen: Screen) => void;
  user: AuthUser;
  task: BoardTask | null;
  answerCount: number;
  rowsPerQuery: number;
  onOpenBasket: () => void;
}) {
  // Tab "Lịch sử" không nằm trong NAV vì nó không phải một màn cố định: nó
  // thuộc về MỘT câu, và chỉ có nghĩa khi đang ở khu vực tìm kiếm. Ở Board hay
  // Export thì "lịch sử của câu nào" không có câu trả lời.
  //
  // Điều kiện phải kể cả `history`, nếu không tab tự biến mất ngay khi bấm vào
  // nó và không còn đường quay lại.
  const showHistory =
    task !== null && (screen === "search" || screen === "history");
  const summary = useSearchStore((state) => state.summary);
  const items = NAV.filter((item) => !item.adminOnly || user.role === "admin");

  // Thanh này dính ở đỉnh trang, nên mọi khối dính khác — đề bài ở màn Search,
  // khối video ở màn Evaluation — phải đậu ngay DƯỚI nó. Chúng đọc chiều cao
  // qua biến CSS `--nav-h`.
  //
  // Đo thật thay vì viết cứng một con số: thanh có flex-wrap, và trên màn hẹp
  // cụm bên phải rơi xuống dòng thứ hai làm nó cao gấp đôi. Một hằng số 40px
  // sẽ để đề bài chui một nửa xuống gầm đúng lúc màn hình đã chật nhất.
  const bar = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const node = bar.current;
    if (!node) {
      return;
    }
    const publish = () =>
      document.documentElement.style.setProperty(
        "--nav-h",
        `${Math.round(node.getBoundingClientRect().height)}px`
      );
    publish();
    const observer = new ResizeObserver(publish);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={bar}
      className="sticky top-0 z-50 flex flex-wrap items-center gap-y-1 gap-x-1 px-4 py-1.5 border-b border-proto-line bg-proto-soft font-baloo"
    >
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={() => onNavigate(item.id)}
          className={`text-[12.5px] px-3 py-1 rounded-[7px] border ${
            screen === item.id
              ? "bg-proto-card border-proto-cream-strong text-proto-ink font-semibold"
              : "border-transparent text-proto-muted"
          }`}
        >
          {item.label}
        </button>
      ))}

      {showHistory && (
        <button
          type="button"
          // Bật/tắt, không phải điều hướng một chiều: lịch sử giờ là một lớp
          // phủ lên màn Search, nên nút mở nó cũng phải đóng được nó.
          onClick={() => onNavigate(screen === "history" ? "search" : "history")}
          title={
            screen === "history"
              ? "Đóng lịch sử"
              : `Mọi truy vấn cả nhóm đã gõ cho câu ${task.code}`
          }
          className={`text-[12.5px] px-3 py-1 rounded-[7px] border ${
            screen === "history"
              ? "bg-proto-card border-proto-cream-strong text-proto-ink font-semibold"
              : "border-transparent text-proto-muted"
          }`}
        >
          Lịch sử <span className="font-mono">{task.code}</span>
        </button>
      )}

      {/* Chỉ ở khu vực tìm kiếm. Giỏ đáp án là việc của lúc đang tìm; đứng ở
          Board thì bảng đã có cột số dòng của từng câu, còn ở Import/Export nó
          chỉ là một ô đếm không dùng tới.

          Trong khu vực đó thì luôn chiếm chỗ, kể cả khi chưa mở task nào: ẩn
          hẳn sẽ làm giỏ — và nút Điền tự động bên trong nó — không còn đường
          vào nếu không biết phải quay lại Board. */}
      {(screen === "search" || screen === "history") &&
        (task ? (
          <button
            type="button"
            onClick={onOpenBasket}
            title="Mở giỏ đáp án · Autofill"
            className="ml-3 flex items-center gap-2 text-[12px] px-3 py-1 rounded-[7px] border border-proto-primary bg-white"
          >
            <span className="text-proto-muted">
              Task <b className="text-proto-ink font-mono">{task.code}</b>
            </span>
            <span className="font-mono font-bold text-proto-ink">
              {answerCount}
              <span className="text-proto-muted font-normal">/{rowsPerQuery}</span>
            </span>
            <span className="text-proto-primary-active font-semibold">Giỏ</span>
          </button>
        ) : (
          <button
            type="button"
            onClick={() => onNavigate("board")}
            className="ml-3 text-[12px] px-3 py-1 rounded-[7px] border border-dashed border-proto-line text-proto-muted"
          >
            Chưa mở task — vào Board để nhận
          </button>
        ))}

      {/* "50 khung · 1.8s" — trước đây là một khối riêng nằm giữa đề bài và
          lưới ảnh, cao chừng 40px chỉ để nói hai con số, lại đi kèm ô "Sorted
          By" đã bỏ. Ở đây nó không tốn thêm dòng nào.

          Chỉ hiện ở khu vực tìm kiếm: đứng ở Board hay Export thì con số của
          lượt tìm gần nhất không nói lên điều gì. */}
      {summary !== null && (screen === "search" || screen === "history") && (
        <span className="ml-3 text-[12px] text-proto-muted">
          <b className="font-mono text-proto-ink">{summary.count}</b>{" "}
          {summary.unit === "videos" ? "video" : "khung"} ·{" "}
          <span className="font-mono">{summary.seconds.toFixed(1)}s</span>
        </span>
      )}

      {/* Ô "Tới frame" và badge trạng thái backend, dồn từ khối header riêng
          của màn Search lên đây.

          Khối cũ cao gần 90px và chỉ có ở màn Search, nên nó vừa ăn mất một
          hàng kết quả vừa giấu hai thứ đáng thấy ở mọi màn: dán mã frame đồng
          đội gửi là mở được video ngay, và backend chết thì phải biết dù đang
          đứng ở Board hay Export. Phần bỏ đi chỉ là logo với chữ "Scavenger" —
          không gắn hành động nào. */}
      <span className="ml-auto flex items-center gap-2">
        <GotoFrame />
        <ApiStatus />
      </span>

      <span className="ml-3 flex items-center gap-3 text-[12px] text-proto-muted">
        <span
          className="hidden lg:inline text-[10.5px] font-mono opacity-70"
          title={`Build ${__APP_VERSION__} · commit ${__APP_COMMIT__}`}
        >
          v{__APP_VERSION__}
        </span>
        <span>
          <b className="text-proto-ink">{user.display_name}</b>
          {user.role === "admin" && (
            <span className="ml-1.5 text-[9.5px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-proto-cream-strong">
              admin
            </span>
          )}
        </span>
        <button
          type="button"
          onClick={() => void logout()}
          className="underline text-proto-muted"
        >
          Đăng xuất
        </button>
      </span>
    </div>
  );
}
