import { useEffect, useState } from "react";

import {
  clearSearchHistory,
  listSearchHistory,
  type ClearHistoryScope,
  type SearchHistoryEntry,
  type SearchState,
} from "../../api/searchState";
import { useAuthStore } from "../../store/authStore";

const POLL_MS = 5000;

const TYPE_LABEL: Record<string, string> = {
  ensemble: "BEiT3+CLIP",
  single: "1 model",
  temporal: "Temporal",
  trake: "TRAKE",
  ocr: "OCR",
};

function ago(iso: string): string {
  const seconds = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (seconds < 60) return "vừa xong";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} phút trước`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} giờ trước`;
  return `${Math.floor(seconds / 86400)} ngày trước`;
}

/**
 * Mọi truy vấn cả nhóm đã từng gõ cho MỘT câu.
 *
 * Trước đây đây là một khối gấp/mở nhét dưới bảng "Cả nhóm đang tìm câu này",
 * và hai bảng dính liền nhau trông như dữ liệu lặp — cùng một truy vấn hiện
 * hai lần, một vì đó là câu đang gõ, một vì đó là mục mới nhất trong lịch sử.
 * Tách hẳn ra một màn riêng thì mỗi bảng trả lời đúng một câu hỏi, và bảng này
 * có trọn chiều ngang để in hết truy vấn thay vì cắt ở giữa.
 *
 * Mỗi câu một lịch sử riêng: `taskId` đổi thì tải lại từ đầu.
 */
export default function SearchHistory({
  taskId,
  taskCode,
  onOpenState,
  onOpenVideo,
}: {
  taskId: number;
  taskCode: string;
  /** Lấy truy vấn này làm của mình rồi chạy lại — quay về màn Search. */
  onOpenState: (state: SearchState) => void;
  onOpenVideo: (videoId: string, frameIdx: number) => void;
}) {
  const me = useAuthStore((state) => state.user);
  const [entries, setEntries] = useState<SearchHistoryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // id của người đang được lọc, null là xem hết. Một người một lúc: câu hỏi
  // thật sự là "Bằng đã thử những gì rồi", chứ không phải "Bằng hoặc Nam".
  const [onlyUser, setOnlyUser] = useState<number | null>(null);
  // Phạm vi đang chờ xác nhận, null là không có thẻ nào mở. Giữ chính phạm vi
  // chứ không phải một cờ bật/tắt: admin có hai nút xoá, và thẻ phải nói đúng
  // cái nào vừa được bấm.
  const [confirming, setConfirming] = useState<ClearHistoryScope | null>(null);
  const [clearing, setClearing] = useState(false);
  // Tăng lên một là useEffect chạy lại. Xoá xong mà chỉ chờ nhịp poll 5 giây
  // thì bảng còn nguyên các dòng vừa bỏ, trông y như cú bấm không ăn.
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setEntries(null);
    const load = async () => {
      try {
        const result = await listSearchHistory(taskId);
        if (!cancelled) {
          setEntries(result.entries);
          setError(null);
        }
      } catch {
        if (!cancelled) setError("Không tải được lịch sử");
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [taskId, refreshTick]);

  const shown = (entries ?? []).filter(
    (entry) => onlyUser === null || entry.user.id === onlyUser
  );

  // Một nút cho mỗi người CÓ MẶT trong lịch sử câu này, theo thứ tự xuất hiện
  // (mới nhất trước). Không lấy từ danh sách thành viên: người chưa đụng vào
  // câu này thì nút của họ chỉ lọc ra một bảng rỗng.
  //
  // Bộ lọc cũ ở chỗ này là "Chỉ mục đã chọn khung" — nó trả lời "ai đã tìm ra
  // cái gì đó", nhưng khi cần dò lại đường của một người cụ thể thì vẫn phải
  // đọc lướt cả bảng.
  const people: { id: number; label: string }[] = [];
  for (const entry of entries ?? []) {
    if (people.some((person) => person.id === entry.user.id)) continue;
    people.push({
      id: entry.user.id,
      label: entry.user.id === me?.id ? "tôi" : entry.user.display_name,
    });
  }
  people.sort((a, b) => (a.label === "tôi" ? -1 : b.label === "tôi" ? 1 : 0));

  // Hai con số này đi vào thẻ xác nhận. Nói "xoá 3 dòng" thay vì "xoá lịch sử"
  // là khác biệt giữa một cú bấm biết mình đang bỏ gì và một cú bấm mù.
  const mineCount = (entries ?? []).filter(
    (entry) => entry.user.id === me?.id
  ).length;
  const allCount = (entries ?? []).length;
  const isAdmin = me?.role === "admin";
  const pendingCount = confirming === "all" ? allCount : mineCount;

  const runClear = async (scope: ClearHistoryScope) => {
    setClearing(true);
    try {
      await clearSearchHistory(taskId, scope);
      setConfirming(null);
      // Bộ lọc "Chỉ của X" có thể đang trỏ vào một người vừa bị xoá sạch; bỏ
      // lọc để bảng không hiện ra rỗng và trông như xoá nhầm ai đó.
      setOnlyUser(null);
      setRefreshTick((tick) => tick + 1);
    } catch {
      setError("Không xoá được lịch sử");
      setConfirming(null);
    } finally {
      setClearing(false);
    }
  };

  const clearButton = (scope: ClearHistoryScope, label: string) => (
    <button
      type="button"
      onClick={() => setConfirming(scope)}
      className="text-[12.5px] px-3 py-1 rounded-[7px] border border-[#c64545]/50 text-[#c64545] hover:bg-[#c64545]/10"
    >
      {label}
    </button>
  );

  return (
    <div className="max-w-[1400px] mx-auto p-6 font-baloo">
      <div className="flex items-center gap-3 mb-1 flex-wrap">
        <h2 className="text-2xl text-proto-ink">Lịch sử tìm</h2>
        <span className="text-sm text-proto-muted">
          câu <b className="font-mono text-proto-ink">{taskCode}</b>
        </span>
        <span className="text-sm text-proto-muted ml-auto">
          {entries === null ? "…" : `${shown.length}/${entries.length} truy vấn`}
        </span>
      </div>
      <p className="text-sm text-proto-muted mb-4">
        Mọi truy vấn cả nhóm đã gõ cho riêng câu này, kể cả những câu đã bỏ. Bấm{" "}
        <b>Coi … làm</b> để lấy lại nguyên truy vấn và tham số rồi chạy lại.
      </p>

      <div className="flex gap-1 mb-3 flex-wrap">
        {people.map((person) => (
          <button
            key={person.id}
            type="button"
            // Bấm lại nút đang bật thì bỏ lọc — không cần thêm nút "Tất cả".
            onClick={() =>
              setOnlyUser((current) =>
                current === person.id ? null : person.id
              )
            }
            className={`text-[12.5px] px-3 py-1 rounded-[7px] border ${
              onlyUser === person.id
                ? "bg-proto-cream-strong border-proto-cream-strong text-proto-ink font-semibold"
                : "border-proto-line text-proto-muted"
            }`}
          >
            Chỉ của {person.label}
          </button>
        ))}

        {/* Đặt ở hàng bộ lọc chứ không phải hàng tiêu đề: nút × đóng lớp phủ
            nằm absolute ở góc trên bên phải, thêm nút vào đó là hai thứ chồng
            nhau và bấm nhầm "xoá" khi định đóng.

            Admin có HAI nút. Nếu chỉ để nút xoá cả nhóm thì admin — cũng là
            một người ngồi thi, cũng có dòng trong bảng — mất mất việc dọn
            riêng phần mình mà mọi thành viên khác đều làm được. */}
        <div className="ml-auto flex gap-1">
          {mineCount > 0 && clearButton("mine", `Xoá ${mineCount} dòng của tôi`)}
          {isAdmin &&
            allCount > 0 &&
            clearButton("all", `Xoá hết (${allCount})`)}
        </div>
      </div>

      {/* Thẻ xác nhận. `fixed` chứ không phải chèn thẳng vào bảng: lớp lịch sử
          cuộn được, một thẻ nằm trong dòng chảy sẽ trôi khỏi tầm nhìn ngay khi
          người ta lỡ lăn chuột, và câu hỏi "có chắc không" mà không nhìn thấy
          thì vô nghĩa.

          Esc ở đây đóng cả lớp lịch sử (handler đăng ký trong App.tsx) chứ
          không riêng thẻ này. Để nguyên: kết quả vẫn là không xoá gì. */}
      {confirming !== null && (
        <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-xl border border-proto-line shadow-2xl w-full max-w-md p-5">
            <h3 className="text-lg text-proto-ink mb-2">
              {confirming === "all"
                ? "Xoá lịch sử tìm của cả nhóm?"
                : "Xoá lịch sử tìm của bạn?"}
            </h3>
            <p className="text-[13px] text-proto-body mb-1">
              Bỏ đi <b>{pendingCount}</b> truy vấn trên câu{" "}
              <b className="font-mono">{taskCode}</b>
              {confirming === "all" ? ", kể cả của người khác" : ""}. Không lấy
              lại được.
            </p>
            {/* Nói trước, để không ai tưởng cú bấm bị trôi mất. */}
            <p className="text-[12.5px] text-proto-muted mb-4">
              Khung đang chọn và truy vấn đang gõ vẫn còn — chỉ danh sách các
              lần tìm cũ bị xoá.
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirming(null)}
                disabled={clearing}
                className="text-[13px] px-3 py-1.5 rounded-[7px] border border-proto-line text-proto-ink disabled:opacity-50"
              >
                Huỷ
              </button>
              <button
                type="button"
                onClick={() => void runClear(confirming)}
                disabled={clearing}
                className="text-[13px] px-3 py-1.5 rounded-[7px] bg-[#c64545] text-white font-semibold disabled:opacity-50"
              >
                {clearing ? "Đang xoá…" : `Xoá ${pendingCount} dòng`}
              </button>
            </div>
          </div>
        </div>
      )}

      {error && <p className="text-[#c64545] text-sm mb-2">{error}</p>}

      {entries === null ? (
        <p className="text-sm text-proto-muted">Đang tải…</p>
      ) : shown.length === 0 ? (
        <p className="text-sm text-proto-muted">
          {entries.length === 0
            ? "Chưa ai search câu này. Mỗi lần bấm Search sẽ ghi lại một mục ở đây."
            : "Không có mục nào khớp bộ lọc."}
        </p>
      ) : (
        <div className="border border-proto-line rounded-[10px] overflow-hidden bg-white divide-y divide-proto-line">
          {shown.map((entry) => (
            <div
              key={entry.id}
              className={`flex items-start gap-3 px-3 py-2 text-[13px] ${
                entry.user.id === me?.id ? "bg-proto-soft/40" : ""
              }`}
            >
              <b className="w-20 shrink-0 truncate text-proto-ink">
                {entry.user.id === me?.id ? "bạn" : entry.user.display_name}
              </b>
              <span className="text-[9.5px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-proto-cream-strong text-proto-ink shrink-0 mt-0.5">
                {TYPE_LABEL[entry.search_type] ?? entry.search_type}
              </span>
              {/* Trọn chiều ngang, xuống dòng thay vì cắt: một truy vấn dài là
                  thứ đáng đọc hết trước khi quyết định có thử lại hay không. */}
              <span className="text-proto-body flex-1 min-w-0 break-words">
                {entry.query_text}
              </span>
              <span className="text-proto-muted shrink-0 hidden md:inline mt-0.5">
                {ago(entry.updated_at)}
              </span>
              {/* MỘT nút cho MỖI khung đã chốt, theo thứ tự bấm — thứ tự đó
                  chính là thứ tự người dùng tự xếp hạng.

                  Trước đây chỗ này đọc `entry.picked_*`, tức chỉ một khung, và
                  đó là khung CUỐI CÙNG: gõ một câu rồi bấm ba thẻ thì hai thẻ
                  đầu không còn dấu vết nào ở đây, dù cả ba đã nằm trong giỏ.

                  `flex-wrap` vì ba bốn nút cộng lại dài hơn một dòng, mà cắt
                  bớt thì đúng những khung sau cùng biến mất — lặp lại chính
                  cái lỗi vừa sửa, chỉ bằng CSS. */}
              {entry.picks.length > 0 && (
                <span className="shrink-0 flex flex-wrap justify-end gap-1 max-w-[46%]">
                  {entry.picks.map((pick) => (
                    <button
                      key={`${pick.video}-${pick.frame}`}
                      type="button"
                      onClick={() => onOpenVideo(pick.video, pick.frame)}
                      className="px-2 py-0.5 rounded-[6px] border border-proto-line text-proto-ink"
                      title="Mở video tại khung này"
                    >
                      ▶ {pick.video} · {pick.frame}
                    </button>
                  ))}
                </span>
              )}
              <button
                type="button"
                onClick={() => onOpenState(entry)}
                className="shrink-0 px-2 py-0.5 rounded-[6px] border border-proto-primary text-proto-primary-active font-semibold"
                title="Lấy truy vấn này làm của bạn và chạy lại"
              >
                Coi {entry.user.id === me?.id ? "lại" : entry.user.display_name}{" "}
                làm
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
