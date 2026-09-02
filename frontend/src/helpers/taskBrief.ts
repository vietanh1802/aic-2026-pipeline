import type { BoardTask } from "../api/board";

/**
 * The text that describes a task — verbatim, exactly the bytes the organizer
 * wrote.
 *
 * Cách cũ có thêm một nhánh dựng lại đề bài từ `event_labels` khi `query_text`
 * rỗng:
 *
 *     if (task.type === "trake" && task.event_labels.length > 0) {
 *       return task.event_labels.map((l, i) => `E${i + 1} · ${l}`).join(" → ");
 *     }
 *
 * Nhánh đó chỉ tồn tại vì trình đọc gói tách E1..EN ra khỏi đề bài rồi để lại
 * một `query_text` rỗng. Giờ nó chép nguyên văn, nên không còn gì để dựng lại.
 */
export function taskBriefText(
  task: Pick<BoardTask, "type" | "query_text" | "event_labels">
): string {
  return task.query_text ?? "";
}

/**
 * The same brief, for the search box.
 *
 * Giống hệt `taskBriefText`, chỉ gộp khoảng trắng cho vừa một dòng input.
 *
 * Cách cũ ghép `event_labels` lại bằng ". " để số đoạn sau khi tách bằng
 * `splitQueryParts` khớp đúng `n_events`, nhưng chỉ khi `query_text` rỗng — và
 * nó im lặng thua ngay khi không rỗng. Bộ SOTUYEN2 làm lộ chuyện đó: mọi file
 * TRAKE ở đó mở đầu bằng một dòng dẫn nhập, nên nhánh `query_text` ăn trước và
 * bốn câu tả thật của câu 8 (sầu riêng, măng cụt, bưởi, dâu bòn bon) không hề
 * đi vào truy vấn — thứ được đem đi tìm là hai câu dẫn nhập không tả một hình
 * ảnh nào.
 *
 * Không cố sửa cho thông minh hơn nữa. Chép đúng chữ ban tổ chức viết rồi để
 * người dùng tự cắt phần thừa: họ đọc được đề, còn hàm này thì không.
 */
export function taskQueryForSearch(
  task: Pick<BoardTask, "type" | "query_text" | "event_labels">
): string {
  return (task.query_text ?? "").replace(/\s+/g, " ").trim();
}
