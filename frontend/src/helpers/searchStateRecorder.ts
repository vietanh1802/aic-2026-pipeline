import { saveSearchState } from "../api/searchState";
import { usePickedFrameStore } from "../store/pickedFrameStore";
import { useQueryStore } from "../store/queryStore";

/**
 * Ghi lại "tôi đang tìm bằng gì, và tôi dừng ở khung nào".
 *
 * Sống ở đây thay vì trong App.tsx vì có HAI đường dẫn tới một lần chốt khung
 * và chúng nằm ở hai cây component khác nhau: bấm thẳng trên thẻ kết quả
 * (App.tsx), và chốt trong popup video sau khi đã tua tới lui (SubmitForm).
 * Đường thứ hai trước đây không ghi gì, nên lịch sử luôn dừng ở cái thẻ được
 * bấm chứ không phải khung thật sự được lấy.
 *
 * Đọc thẳng từ store, không nhận truy vấn qua tham số: hàm này hay được gọi
 * ngay sau khi trạng thái vừa đổi, mà closure của nơi gọi thì còn giữ giá trị
 * cũ.
 *
 * Gửi đi rồi quên. Không chờ, không báo lỗi: mất một lần ghi thì đồng đội thấy
 * truy vấn cũ hơn vài giây, còn chặn thao tác chính lại vì nó thì hỏng đúng
 * việc đang làm.
 */
export interface PickedFrame {
  /**
   * Tên keyframe của THẺ được bấm trong lưới, vd "L21_V001-0028-3175.jpg".
   *
   * Đây là thứ vòng khoanh đỏ so khớp, nên nó phải giữ nguyên cái thẻ có thật
   * trong lưới. Khung chốt sau khi tua (3180 chẳng hạn) thường không trùng
   * keyframe nào, nên nếu ghi đè vào đây thì không thẻ nào được khoanh nữa.
   */
  name?: string | null;
  video: string;
  /**
   * Số frame THẬT SỰ được lấy. Bằng số của thẻ khi bấm thẳng, và bằng khung đã
   * tua tới khi chốt trong popup. Nút "▶ video · frame" ở bảng lịch sử đọc số
   * này, vì thứ đáng mở lại là chỗ người ta dừng chân, không phải chỗ họ bắt
   * đầu.
   */
  frameIdx: number;
  /**
   * Cả N mốc của một dòng TRAKE, theo thứ tự sự kiện.
   *
   * Có nó thì bảng lịch sử bày ra N nút "▶ video · frame" cho một cú bấm
   * "Chọn", mỗi nút mở video tại một hành động. Không có thì dòng TRAKE nằm
   * trong lịch sử mà không kèm khung nào — truy vấn thì lấy lại được, còn thứ
   * người dùng đã chốt thì không.
   *
   * `frameIdx` vẫn phải có và là mốc ĐẦU: ba cột số ít trong CSDL dùng chung
   * hình dạng với bảng "cả nhóm đang tìm gì", và ở đó một dòng chỉ có chỗ cho
   * một khung.
   */
  frames?: number[];
}

export function recordSearchState(
  taskId: number | null | undefined,
  picked?: PickedFrame
): void {
  if (!taskId) {
    return;
  }
  const query = useQueryStore.getState();
  // Chốt trong popup thì không có tên keyframe mới; giữ lại tên của thẻ đã bấm
  // để vòng khoanh đỏ không mất, miễn là vẫn cùng một video.
  const ring = usePickedFrameStore.getState().frame;
  void saveSearchState(taskId, {
    query_text: query.queryText,
    search_type: query.searchType,
    params: {
      resultLimit: query.resultLimit,
      topM: query.topM,
      useRerank: query.useRerank,
      singleModel: query.singleModel,
      ocrStripDiacritics: query.ocrStripDiacritics,
    },
    picked_frame: picked ? picked.name ?? ring : null,
    picked_video: picked?.video ?? null,
    picked_frame_idx: picked?.frameIdx ?? null,
    picked_frames: picked?.frames ?? null,
  }).catch(() => undefined);
}
