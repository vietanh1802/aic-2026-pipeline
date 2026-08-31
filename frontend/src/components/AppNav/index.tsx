import { logout } from "../../api/auth";
import type { BoardTask } from "../../api/board";
import type { AuthUser } from "../../types/auth";

export type Screen =
  | "search"
  | "board"
  | "evaluation"
  | "import"
  | "export";

// Thứ tự này là thứ tự công việc: tìm → phân công → đọ bài → nộp. Evaluation
// đứng trước Export vì phải chọn xong bài của ai thì file nộp mới có nội dung.
const NAV: { id: Screen; label: string; adminOnly?: boolean }[] = [
  { id: "search", label: "Search" },
  { id: "board", label: "Board" },
  { id: "evaluation", label: "Evaluation" },
  // "Vòng" đã gộp vào Import: bảng vòng nằm ngay dưới khung thả file, vì
  // nhập gói xong thì việc kế tiếp luôn là kích hoạt nó.
  { id: "import", label: "Import", adminOnly: true },
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
  const items = NAV.filter((item) => !item.adminOnly || user.role === "admin");

  return (
    <div className="flex items-center gap-1 px-4 py-1.5 border-b border-proto-line bg-proto-soft font-baloo">
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

      {/* Always occupies the slot. Hiding it when no task is open made the
          basket - and autofill with it - unreachable without knowing that the
          Board is the way in. */}
      {task ? (
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
      )}

      <span className="ml-auto flex items-center gap-3 text-[12px] text-proto-muted">
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
