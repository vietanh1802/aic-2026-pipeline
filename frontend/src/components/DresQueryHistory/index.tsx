import { useCallback, useEffect, useState } from "react";

import {
  DRES_QUERIES_CHANGED,
  listDresQueries,
  type DresQueryList,
} from "../../api/dres";
import { useQueryStore, type SearchType } from "../../store/queryStore";

// Cả đội cùng gõ cho một câu; 5 giây như bảng lịch sử truy vấn của sơ tuyển.
const POLL_MS = 5000;

const TYPE_LABEL: Record<string, string> = {
  single: "1 model",
  temporal: "Temporal",
  trake: "TRAKE",
  ocr: "OCR",
};

function timeOf(iso: string): string {
  return new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

/**
 * Các câu cả đội đã Search cho câu DRES đang chạy, mới nhất ở trên.
 *
 * Chung kết nhả gợi ý dần: gõ theo gợi ý 1 không thấy, tới gợi ý 2 người ta sửa
 * đè lên ô tìm kiếm và câu cũ mất. Ở đây câu cũ vẫn còn — "Nạp lại" đưa nó về ô
 * tìm kiếm (cả loại search), "+ Nối" ghép nó vào sau thứ đang gõ. Không tự chạy
 * Search: người ta nạp về là để sửa tiếp.
 *
 * Không có câu DRES nào đang chạy (chưa cấu hình, ngoài giờ thi) thì không hiện
 * gì cả — màn Search của sơ tuyển giữ nguyên như cũ.
 */
export default function DresQueryHistory() {
  const [data, setData] = useState<DresQueryList | null>(null);

  const refresh = useCallback(async () => {
    try {
      setData(await listDresQueries());
    } catch {
      // Lần sau cách 5 giây; danh sách phụ không đáng một thông báo lỗi.
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    const onChanged = () => void refresh();
    window.addEventListener(DRES_QUERIES_CHANGED, onChanged);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener(DRES_QUERIES_CHANGED, onChanged);
    };
  }, [refresh]);

  if (!data?.task_name) {
    return null;
  }

  const load = (text: string, searchType: string) => {
    const q = useQueryStore.getState();
    q.setQueryText(text);
    q.setSearchType(searchType as SearchType);
  };
  const append = (text: string) => {
    const q = useQueryStore.getState();
    const current = q.queryText.trim();
    q.setQueryText(current ? `${current} ${text}` : text);
  };

  // Số thứ tự theo lúc gõ (lần 1 = gợi ý đầu tiên), hiện mới nhất lên đầu.
  const numbered = data.queries.map((query, i) => ({ query, n: i + 1 })).reverse();

  return (
    <section className="mx-2 mb-3 p-2 rounded-[10px] border border-proto-line bg-proto-soft font-baloo">
      <h3 className="text-[12px] font-bold uppercase tracking-wide text-proto-muted mb-1">
        Đã gõ cho câu <span className="text-proto-primary-active normal-case">{data.task_name}</span>{" "}
        ({data.queries.length})
      </h3>
      {numbered.length === 0 && (
        <p className="text-[12px] text-proto-muted">
          Chưa ai Search cho câu này. Mỗi lần Search sẽ được lưu ở đây.
        </p>
      )}
      <ol className="flex flex-col gap-1.5 max-h-[320px] overflow-y-auto">
        {numbered.map(({ query, n }) => (
          <li key={query.id} className="p-1.5 rounded-[8px] bg-white border border-proto-line">
            <div className="flex items-center gap-2 text-[11px] text-proto-muted">
              <b className="text-proto-primary-active">#{n}</b>
              <span>
                {query.display_name} · {timeOf(query.created_at)}
              </span>
              {TYPE_LABEL[query.search_type] && (
                <span className="px-1.5 rounded-full bg-proto-soft font-bold">
                  {TYPE_LABEL[query.search_type]}
                </span>
              )}
              <button
                type="button"
                className="ml-auto underline text-proto-primary-active"
                title="Đưa câu này về ô tìm kiếm (thay thứ đang gõ)"
                onClick={() => load(query.query_text, query.search_type)}
              >
                Nạp lại
              </button>
              <button
                type="button"
                className="underline text-proto-primary-active"
                title="Ghép câu này vào sau thứ đang gõ"
                onClick={() => append(query.query_text)}
              >
                + Nối
              </button>
            </div>
            <p className="text-[13px] leading-snug break-words line-clamp-3" title={query.query_text}>
              {query.query_text}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}
