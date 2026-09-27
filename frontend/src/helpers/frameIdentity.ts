// frontend/src/helpers/frameIdentity.ts

/**
 * Turning a keyframe's identity into the three things the video popup needs.
 *
 * These lived inside App.tsx, which was fine while the search grid was the only
 * caller. TRAKE results open the same popup from a different component, so a
 * second copy would be two places to fix the next time a filename changes shape.
 */
import KeyframeFPS from "../mapping/fps_map.json";
import { VIDEO_ID_PREFIX, parseFrameName } from "./frameRef";

/**
 * "L26_V194-0012-004707.jpg" -> "L26_V194"; "N001-V001-0012-345.jpg" -> "N001-V001".
 *
 * Read from the right (parseFrameName), so a hyphen inside the id is fine. The
 * fallback is the old behaviour for a name that is not scene-frame shaped:
 * whatever video id it STARTS with, or "".
 */
export function videoIdFromFrame(frame: string): string {
  // Old: return frame.match(/^([LK]\d{2}_V\d{3})/)?.[1] ?? "";
  // It only knew the L and K batches with an underscore.
  return parseFrameName(frame)?.videoId ?? frame.match(VIDEO_ID_PREFIX)?.[1] ?? "";
}

/**
 * "L26_V194-0012-004707.jpg" -> "0012-004707" (scene and frame, padding kept).
 *
 * Old behaviour stays as the fallback for names parseFrameName rejects, so a
 * name in a shape nobody planned for gives the same answer as before.
 */
export function frameIdFromName(name: string): string {
  const parsed = parseFrameName(name);
  if (parsed) {
    return parsed.frameId;
  }
  // Old: the only path. Cut at the FIRST hyphen, which is wrong as soon as a
  // video id contains one (N001-V001-0012-345 -> "V001-0012-345").
  const baseName = name.replace(/\.[^/.]+$/, "");
  return baseName.split("-").slice(1).join("-");
}

/** 0 when the video is missing from fps_map.json — callers must check. */
export function fpsOf(videoId: string): number {
  return (KeyframeFPS as Record<string, number | undefined>)[videoId] ?? 0;
}

/**
 * Where the popup should open, in milliseconds.
 *
 * Returns 0 for an unknown fps rather than NaN: opening at the start with the
 * frame number on screen is recoverable, a NaN seek is not.
 */
export function startMsAt(videoId: string, frameIdx: number): number {
  const fps = fpsOf(videoId);
  if (!fps || !Number.isFinite(frameIdx)) {
    return 0;
  }
  return (frameIdx / fps) * 1000;
}

/**
 * Mili-giây của một frame, đúng phép quy đổi server DRES dùng khi nộp
 * (`round(f / fps * 1000)` trong backend/app/routers/dres.py) — nên số ms hiện
 * cạnh số frame chính là số sẽ gửi đi. Khác `frameClock` (floor, khớp
 * `timestamp_ms` của index) ở đúng chỗ làm tròn.
 *
 * null khi không biết fps hoặc frame không dùng được, để chỗ gọi không in ra
 * một con số 0 trông như thật.
 */
export function frameToMs(frameIdx: number | null, fps: number): number | null {
  if (frameIdx === null || !fps || !Number.isFinite(frameIdx) || frameIdx < 0) {
    return null;
  }
  return Math.round((frameIdx / fps) * 1000);
}

/** `frameToMs` với fps tra theo video. */
export function frameMsOf(videoId: string, frameIdx: number | null): number | null {
  return frameToMs(frameIdx, fpsOf(videoId));
}

/**
 * The frame number of a search result: the field the backend sends, else the
 * trailing number of the keyframe filename ("...-0116-36128.jpg" -> 36128).
 * Returns 0 when neither is usable, as it did when it lived in App.tsx.
 */
export function frameIndexFromResult(result: {
  frame: string;
  frame_idx?: number;
}): number {
  if (typeof result.frame_idx === "number") {
    return result.frame_idx;
  }
  const parsed = parseFrameName(result.frame);
  if (parsed) {
    return parsed.frameIdx;
  }
  // Old: the only path. Still the fallback for a name parseFrameName rejects
  // (a video id outside VIDEO_ID_PATTERN): it only needs the trailing number.
  return Number(result.frame.match(/-(\d+)\.jpg$/)?.[1] ?? 0);
}

/**
 * The frame number at the end of a popup `frameId`, which is either
 * "scene-frame" ("0116-36128", from a keyframe name) or just "36128" (opened
 * from a frame number). NaN when there is no trailing number: Number("") is 0,
 * which would read as a real frame at the very start of the video.
 */
export function frameIdxFromFrameId(frameId: string): number {
  const match = /(\d+)$/.exec(frameId);
  return match ? Number(match[1]) : Number.NaN;
}

/**
 * "HH:MM:SS.mmm" for a frame, from frame_idx / fps - the same format as the
 * backend's `timestamp_str` ("00:20:05.472").
 *
 * Milliseconds are floored, not rounded, because the index builder computes
 * `int(frame_idx / fps * 1000)`: floored, this matches `timestamp_ms` for all
 * 360,531 frames of the local keyframe_metadata.json, while rounding would
 * differ by 1 ms on about 8% of them. Same operand order as the builder, so
 * the doubles are identical.
 *
 * This replaces reading the trailing number of the filename as milliseconds
 * (`extractTimestamp`), which is the frame index, not a time. "" when the fps
 * is unknown or the frame is not a usable number, so a caller can tell "no
 * clock" apart from a real 00:00:00.000.
 */
export function frameClock(videoId: string, frameIdx: number): string {
  const fps = fpsOf(videoId);
  if (!fps || !Number.isFinite(frameIdx) || frameIdx < 0) {
    return "";
  }
  const totalMs = Math.floor((frameIdx / fps) * 1000);
  const hours = Math.floor(totalMs / 3_600_000);
  const minutes = Math.floor(totalMs / 60_000) % 60;
  const seconds = Math.floor(totalMs / 1000) % 60;
  const millis = totalMs % 1000;
  const pad = (value: number, width: number) => String(value).padStart(width, "0");
  return `${pad(hours, 2)}:${pad(minutes, 2)}:${pad(seconds, 2)}.${pad(millis, 3)}`;
}
