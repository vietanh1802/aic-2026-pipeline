import { apiFetch } from "./base";

/**
 * Kết quả của POST /api/expansion — dịch + mở rộng một đề bài tiếng Việt.
 *
 * `provider` nói đường nào đã thắng: "gemini" (một call) hay "ollama" (fallback
 * local hai bước). `translated_query` chỉ có ở nhánh ollama; gemini làm trọn
 * gói trong một call nên không có bản dịch rời.
 */
export interface ExpansionResult {
  eng_query: string;
  check_units: string[];
  translated_query: string | null;
  provider: string;
  elapsed_ms: number;
}

/**
 * Đề bài VI → câu tìm kiếm EN đã mở rộng.
 *
 * Backend trả 502 khi cả Gemini lẫn Ollama đều không gọi được — apiFetch ném
 * lỗi với detail trong message; caller bắt và hiện inline, không ghi đè ô
 * search bằng chuỗi rỗng.
 */
export function expandQuery(
  queryText: string,
  taskType: string
): Promise<ExpansionResult> {
  return apiFetch<ExpansionResult>("/api/expansion", {
    method: "POST",
    body: JSON.stringify({
      query_text: queryText,
      task_type: taskType,
    }),
  });
}
