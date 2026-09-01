import { useEffect, useState } from "react";

import {
  listSearchStates,
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

/** "2 phút trước". Đủ chính xác để biết ai vừa gõ và ai gõ từ sáng. */
function ago(iso: string): string {
  const seconds = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (seconds < 60) return "vừa xong";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} phút trước`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} giờ trước`;
  return `${Math.floor(seconds / 86400)} ngày trước`;
}

/**
 * Cả nhóm đang tìm câu này bằng truy vấn gì.
 *
 * Có mặt vì cái đắt nhất khi 5 người cùng làm một câu là gõ lại đúng thứ người
 * bên cạnh vừa gõ. Bảng này cho thấy điều đó trước khi phí công, và "Coi X
 * làm" dựng lại nguyên màn hình của họ.
 */
export default function PeerSearchPanel({
  taskId,
  onOpenState,
  onOpenVideo,
}: {
  taskId: number;
  /** Áp truy vấn của người đó vào ô search rồi chạy lại. */
  onOpenState: (state: SearchState) => void;
  /** Mở popup video đúng khung người đó đã bấm. */
  onOpenVideo: (videoId: string, frameIdx: number) => void;
}) {
  const me = useAuthStore((state) => state.user);
  const [states, setStates] = useState<SearchState[]>([]);
  const [open, setOpen] = useState(true);

  // Poll: truy vấn của người khác đổi liên tục trong lúc thi, mà một socket
  // chết lặng lẽ thì để lại màn hình cũ trông y như còn sống. Năm giây là đủ
  // nhanh để không gõ trùng nhau.
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const result = await listSearchStates(taskId);
        if (!cancelled) setStates(result.states);
      } catch {
        // Hụt một nhịp không đáng báo; nhịp sau cách 5 giây.
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [taskId]);

  const others = states.filter((state) => state.user.id !== me?.id);
  const mine = states.find((state) => state.user.id === me?.id) ?? null;

  // "Cả nhóm" nghĩa là CẢ MÌNH.
  //
  // Trước đây dòng này đếm `others`, mà `others` là danh sách đã loại chính
  // mình ra để dựng các hàng "Coi X làm" — nên con số đứng im dù mình vừa
  // search hay vừa chọn khung. Ba người cùng làm mà mãi chỉ hiện "2 người".
  //
  // Bỏ qua ai có dòng nhưng chưa gõ gì: mở câu lên rồi đóng lại không phải là
  // đang tìm câu này.
  const working = states.filter((state) => state.query_text.trim() !== "");

  // Trước đây chỗ này `return null` khi chưa ai khác tìm câu này. Gọn, nhưng
  // nhìn từ ngoài thì "chưa ai tìm" và "tính năng hỏng" giống hệt nhau — không
  // có gì trên màn hình để phân biệt. Nên vẫn hiện một dòng, nói rõ là đang
  // theo dõi mà chưa có ai.
  if (others.length === 0) {
    return (
      <div className="max-w-[98%] mx-auto mb-3 px-3 py-1.5 border border-dashed border-proto-line rounded-[10px] bg-white font-baloo text-[11.5px] text-proto-muted">
        Chưa ai khác tìm câu này. Khi có người search, truy vấn của họ hiện ở
        đây kèm nút <b>Coi … làm</b>.
      </div>
    );
  }

  return (
    <div className="max-w-[98%] mx-auto mb-3 border border-proto-line rounded-[10px] bg-white font-baloo overflow-hidden">
      <div className="px-3 py-1.5 bg-proto-soft flex items-center gap-2">
        <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
          Cả nhóm đang tìm câu này
        </span>
        <span className="text-[11px] text-proto-muted">
          {working.length} người
        </span>

        {/* Dải "Đang xem đường tìm của X — thoát" đã bỏ. Nó mô tả một chế
            độ không còn tồn tại: bấm "Coi X làm" giờ LẤY LUÔN trạng thái của X
            làm của mình, nên không có gì để thoát khỏi. Hàng "bạn" ở cuối bảng
            sẽ đổi theo, đó mới là chỗ nói bạn đang ở đâu. */}

        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="ml-auto text-[11.5px] text-proto-muted underline"
        >
          {open ? "Thu gọn" : "Mở"}
        </button>
      </div>

      {open && (
        <div className="divide-y divide-proto-line">
          {others.map((state) => (
              <div
                key={state.user.id}
                className="flex items-center gap-3 px-3 py-1.5 text-xs"
              >
                <b className="text-proto-ink w-20 shrink-0 truncate">
                  {state.user.display_name}
                </b>
                <span className="text-[9.5px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-proto-cream-strong text-proto-ink shrink-0">
                  {TYPE_LABEL[state.search_type] ?? state.search_type}
                </span>
                <span
                  className="text-proto-body truncate flex-1 min-w-0"
                  title={state.query_text}
                >
                  {state.query_text || (
                    <i className="text-proto-line">chưa gõ gì</i>
                  )}
                </span>
                <span className="text-proto-muted shrink-0 hidden md:inline">
                  {ago(state.updated_at)}
                </span>

                {/* Chỉ hiện khi người đó THỰC SỰ đã bấm vào một khung. Nút mở
                    video mà không có khung nào thì mở vào đâu. */}
                {state.picked_video && state.picked_frame_idx !== null && (
                  <button
                    type="button"
                    onClick={() =>
                      onOpenVideo(
                        state.picked_video as string,
                        state.picked_frame_idx as number
                      )
                    }
                    className="shrink-0 px-2 py-0.5 rounded-[6px] border border-proto-line text-proto-ink"
                    title={`Mở video tại khung ${state.user.display_name} đã chọn`}
                  >
                    ▶ {state.picked_video} · {state.picked_frame_idx}
                  </button>
                )}

                {/* Không còn trạng thái "đang xem người này", nên nút không
                    còn hai kiểu tô màu. Bấm là lấy luôn, xong. */}
                <button
                  type="button"
                  onClick={() => onOpenState(state)}
                  disabled={!state.query_text}
                  className="shrink-0 px-2 py-0.5 rounded-[6px] border border-proto-primary text-proto-primary-active font-semibold disabled:opacity-40"
                  title={`Lấy truy vấn và khung đã chọn của ${state.user.display_name} làm của bạn`}
                >
                  Coi {state.user.display_name} làm
                </button>
              </div>
          ))}

          {/* Của chính mình, để đối chiếu. Nằm cuối và nền mờ hơn.

              Bố cục phải GIỐNG HỆT các hàng trên — cùng huy hiệu loại search,
              cùng nút mở video. Bản trước viết gọn hơn, thiếu cả hai, nên nhìn
              xuống thấy người khác có "BEIT3+CLIP" còn mình thì không và tưởng
              mình đang chạy kiểu search khác. Hàng này có mặt để SO SÁNH, mà
              thiếu đúng hai ô đáng so thì nó phản tác dụng.

              Chỉ thiếu nút "Coi … làm", vì đó đã là màn hình bạn đang đứng. */}
          {mine && (
            <div className="flex items-center gap-3 px-3 py-1.5 text-xs bg-proto-soft/50">
              <b className="text-proto-muted w-20 shrink-0 truncate">bạn</b>
              <span className="text-[9.5px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-proto-cream-strong text-proto-muted shrink-0">
                {TYPE_LABEL[mine.search_type] ?? mine.search_type}
              </span>
              <span
                className="text-proto-muted truncate flex-1 min-w-0"
                title={mine.query_text}
              >
                {mine.query_text || (
                  <i className="text-proto-line">chưa gõ gì</i>
                )}
              </span>
              <span className="text-proto-muted shrink-0 hidden md:inline">
                {ago(mine.updated_at)}
              </span>
              {mine.picked_video && mine.picked_frame_idx !== null && (
                <button
                  type="button"
                  onClick={() =>
                    onOpenVideo(
                      mine.picked_video as string,
                      mine.picked_frame_idx as number
                    )
                  }
                  className="shrink-0 px-2 py-0.5 rounded-[6px] border border-proto-line text-proto-muted"
                  title="Mở video tại khung bạn đã chọn"
                >
                  ▶ {mine.picked_video} · {mine.picked_frame_idx}
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
