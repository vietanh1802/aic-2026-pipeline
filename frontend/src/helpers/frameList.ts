import { frameToMs } from "./frameIdentity";
import { frameAt } from "./frameRange";
import { parseFrameName } from "./frameRef";
import { parseClock } from "./youtube";

/**
 * Danh sách frame gõ tay cho một bài TRAKE.
 *
 * TRAKE nộp SỐ FRAME (`TR-<video>-<f1>,<f2>,...`), nên điền tay số frame là
 * đường chính xác nhất — không qua quy đổi ms nào. Nhận:
 *   - số trần, cách nhau bằng dấu phẩy, chấm phẩy, dấu cách hoặc xuống dòng;
 *   - tên keyframe dán nguyên ("M05_V019-0193-15697.jpg") — lấy số frame cuối,
 *     vì người ta hay chép tên thẻ kết quả hơn là gõ lại số.
 * Thứ tự giữ nguyên: đó là thứ tự E1, E2, ... của câu hỏi.
 */
export interface FrameList {
  frames: number[];
  /** Lỗi chặn nộp; null khi đọc được hết. */
  error: string | null;
  /** Đáng xem lại nhưng không chặn. */
  warnings: string[];
}

export function parseFrameList(text: string, videoId: string): FrameList {
  const tokens = text.split(/[\s,;]+/).filter(Boolean);
  const frames: number[] = [];
  for (const token of tokens) {
    if (/^\d+$/.test(token)) {
      frames.push(Number(token));
      continue;
    }
    const parsed = parseFrameName(token);
    if (!parsed) {
      return { frames, error: `"${token}" không phải số frame hay tên keyframe`, warnings: [] };
    }
    // Dán nhầm keyframe của video khác là nộp một số frame vô nghĩa cho video này.
    if (parsed.videoId !== videoId) {
      return {
        frames,
        error: `"${token}" thuộc video ${parsed.videoId}, không phải ${videoId}`,
        warnings: [],
      };
    }
    frames.push(parsed.frameIdx);
  }

  const seen = new Set<number>();
  for (const frame of frames) {
    if (seen.has(frame)) {
      // Server cũng từ chối ("TRAKE có hai mốc trùng frame"); báo ngay ở đây.
      return { frames, error: `Frame ${frame} bị lặp`, warnings: [] };
    }
    seen.add(frame);
  }

  const warnings: string[] = [];
  if (frames.some((frame, i) => i > 0 && frame < frames[i - 1])) {
    warnings.push("Các frame không tăng dần — TRAKE nộp theo thứ tự E1, E2, …; kiểm lại thứ tự.");
  }
  return { frames, error: null, warnings };
}

/**
 * MỘT thời điểm điền tay cho câu KIS / Q&A, kèm bộ chuyển đổi frame ↔ thời
 * gian ↔ ms.
 *
 * Hai đơn vị, chọn tường minh chứ không đoán: "627" là frame 627 hay giây
 * thứ 627 thì chỉ người gõ biết.
 *   - "frame": số frame, hoặc dán tên keyframe của đúng video này.
 *   - "time":  thời gian trong video như đồng hồ trình phát — "10:27",
 *              "1:02:03.5"; một số trần là GIÂY ("627.88").
 * Mọi thứ quy về MỘT frame rồi mới ra ms (frameToMs), đúng đường ms của nút
 * "tại thời điểm đang phát" — nên cùng một khoảnh khắc thì cùng một bài nộp.
 */
export type PointUnit = "frame" | "time";

export interface ManualPoint {
  frame: number | null;
  ms: number | null;
  /** Vị trí của chính frame đó (frame / fps), để hiện đồng hồ. */
  seconds: number | null;
  error: string | null;
}

const EMPTY: ManualPoint = { frame: null, ms: null, seconds: null, error: null };

export function parseManualPoint(
  text: string,
  unit: PointUnit,
  videoId: string,
  fps: number
): ManualPoint {
  if (!text.trim()) {
    return EMPTY;
  }
  if (!fps) {
    return { ...EMPTY, error: `Không biết fps của ${videoId} — không quy đổi được` };
  }
  let frame: number | null;
  if (unit === "frame") {
    const list = parseFrameList(text, videoId);
    if (list.error) {
      return { ...EMPTY, error: list.error };
    }
    if (list.frames.length !== 1) {
      return { ...EMPTY, error: "KIS / Q&A nộp đúng MỘT frame" };
    }
    frame = list.frames[0];
  } else {
    const seconds = parseClock(text);
    if (seconds === null) {
      return { ...EMPTY, error: "Không đọc được thời gian — gõ như 10:27, 1:02:03.5 hoặc số giây" };
    }
    frame = frameAt(seconds, fps);
  }
  if (frame === null) {
    return { ...EMPTY, error: "Không quy ra được frame" };
  }
  return { frame, ms: frameToMs(frame, fps), seconds: frame / fps, error: null };
}
