import { useEffect, useState } from "react";

import {
  listSearchStates,
  type SearchState,
} from "../../api/searchState";
import { usePeerViewStore } from "../../store/peerViewStore";
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
  const viewing = usePeerViewStore((state) => state.viewing);
  const clearViewing = usePeerViewStore((state) => state.clear);
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

  // Trước đây chỗ này `return null` khi chưa ai khác tìm câu này. Gọn, nhưng
  // nhìn từ ngoài thì "chưa ai tìm" và "tính năng hỏng" giống hệt nhau — không
  // có gì trên màn hình để phân biệt. Nên vẫn hiện một dòng, nói rõ là đang
  // theo dõi mà chưa có ai.
  if (others.length === 0 && !viewing) {
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
          {others.length} người
        </span>

        {/* Dải báo "đang xem bài người khác". Không có nó thì lưới kết quả của
            X trông hệt kết quả của mình, và rất dễ tưởng mình vừa tìm ra. */}
        {viewing && (
          <span className="ml-2 flex items-center gap-2 text-[11.5px] px-2 py-0.5 rounded-full bg-[#c64545]/10 text-[#c64545] font-semibold">
            Đang xem đường tìm của {viewing.displayName}
            <button
              type="button"
              onClick={clearViewing}
              className="underline decoration-dotted"
              title="Bỏ khoanh đỏ, quay lại việc của mình"
            >
              thoát
            </button>
          </span>
        )}

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
          {others.map((state) => {
            const isViewing = viewing?.userId === state.user.id;
            return (
              <div
                key={state.user.id}
                className={`flex items-center gap-3 px-3 py-1.5 text-xs ${
                  isViewing ? "bg-[#c64545]/5" : ""
                }`}
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

                <button
                  type="button"
                  onClick={() => onOpenState(state)}
                  disabled={!state.query_text}
                  className={`shrink-0 px-2 py-0.5 rounded-[6px] border font-semibold ${
                    isViewing
                      ? "border-[#c64545] text-[#c64545]"
                      : "border-proto-primary text-proto-primary-active"
                  } disabled:opacity-40`}
                >
                  Coi {state.user.display_name} làm
                </button>
              </div>
            );
          })}

          {/* Của chính mình, để đối chiếu. Nằm cuối và mờ hơn: nó là thứ bạn
              đã biết, có mặt chỉ để so với hàng trên. */}
          {mine && (
            <div className="flex items-center gap-3 px-3 py-1.5 text-xs bg-proto-soft/50">
              <b className="text-proto-muted w-20 shrink-0 truncate">
                bạn
              </b>
              <span
                className="text-proto-muted truncate flex-1 min-w-0"
                title={mine.query_text}
              >
                {mine.query_text || (
                  <i className="text-proto-line">chưa gõ gì</i>
                )}
              </span>
              <span className="text-proto-muted shrink-0">
                {ago(mine.updated_at)}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
