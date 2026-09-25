import {
  approveDresSubmission,
  describePayload,
  type DresSubmission,
} from "../api/dres";
import { ApiRequestError } from "../api/base";

/**
 * Nội dung hộp xác nhận trước khi admin gửi một bài lên DRES.
 *
 * Hiện ĐÚNG chuỗi sẽ ra mạng chứ không phải một bản diễn giải của nó: nộp sai
 * là −10 điểm, và thứ admin cần soát là chính chuỗi đó (tên video, mili-giây,
 * dấu gạch nối) chứ không phải "câu KIS của Vanh".
 */
export function approveConfirmMessage(submission: DresSubmission): string {
  const lines = [
    `Gửi lên DRES bài #${submission.id} (${submission.task_type.toUpperCase()}, đề xuất bởi ${submission.proposed_by_name})?`,
    "",
    describePayload(submission),
    "",
  ];
  if (submission.dres_task_name) {
    lines.push(`Câu lúc đề xuất: ${submission.dres_task_name}`);
  }
  for (const warning of submission.warnings) {
    lines.push(`⚠ ${warning}`);
  }
  lines.push("Nộp SAI bị trừ 10 điểm. Chỉ lần đúng đầu tiên được tính.");
  return lines.join("\n");
}

/**
 * Hỏi, gửi, và xử lý trường hợp câu đã đổi.
 *
 * Server từ chối (409) khi DRES đã sang câu khác so với lúc đề xuất. Không tự
 * ép gửi: phải hỏi lần hai, vì gần như luôn đó là đáp án của câu trước.
 * Trả null khi admin huỷ.
 */
export async function approveWithConfirm(
  submission: DresSubmission
): Promise<DresSubmission | null> {
  if (!window.confirm(approveConfirmMessage(submission))) {
    return null;
  }
  try {
    return await approveDresSubmission(submission.id);
  } catch (error) {
    const taskChanged =
      error instanceof ApiRequestError &&
      error.status === 409 &&
      error.message.includes("đang chạy câu");
    if (
      taskChanged &&
      window.confirm(`${error.message}.\n\nVẫn gửi? Gần như chắc chắn đây là đáp án của câu trước.`)
    ) {
      return approveDresSubmission(submission.id, true);
    }
    throw error;
  }
}
