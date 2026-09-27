import YoutubeMap from "../mapping/youtube_map.json";

/**
 * Bản YouTube của một video, từ media-info BTC (notebooks/123_youtube_map_frontend).
 *
 * Có cho L, M, S — không có N (camera giao thông không lên YouTube) và không có
 * S01-V005 (media-info ghi nhầm link của V004). null thì popup không hiện gì.
 */
export interface YoutubeInfo {
  id: string;
  /** Giây, theo YouTube. Khớp file mp4 trong ±0,5 s ở mọi mẫu đã đo. */
  length: number;
}

export function youtubeOf(videoId: string): YoutubeInfo | null {
  return (YoutubeMap as Record<string, YoutubeInfo | undefined>)[videoId] ?? null;
}

/** Mở đúng giây đó. YouTube chỉ nhận `t` nguyên giây, nên làm tròn xuống. */
export function youtubeUrlAt(id: string, seconds: number): string {
  const t = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0));
  return `https://www.youtube.com/watch?v=${id}&t=${t}s`;
}

/**
 * Giờ người dùng gõ, đọc như đồng hồ YouTube đang hiện: "10:27", "1:02:03",
 * "10:27.88", hoặc số giây trần "627.88". Dấu phẩy thập phân cũng nhận (bàn
 * phím tiếng Việt). null khi không đọc được — không đoán.
 */
export function parseClock(text: string): number | null {
  const raw = text.trim().replace(",", ".");
  if (!raw) {
    return null;
  }
  if (/^\d+(\.\d+)?$/.test(raw)) {
    return Number(raw);
  }
  const match = /^(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)$/.exec(raw);
  if (!match) {
    return null;
  }
  const hours = match[1] === undefined ? 0 : Number(match[1]);
  const minutes = Number(match[2]);
  const seconds = Number(match[3]);
  // "10:75" hay "1:75:00" gần như chắc là gõ nhầm; YouTube không bao giờ hiện vậy.
  if (seconds >= 60 || (match[1] !== undefined && minutes >= 60)) {
    return null;
  }
  return hours * 3600 + minutes * 60 + seconds;
}

/** "10:27.880" hoặc "1:02:03.500" — cùng kiểu đồng hồ YouTube, thêm mili-giây. */
export function formatClock(seconds: number): string {
  const totalMs = Math.max(0, Math.round((Number.isFinite(seconds) ? seconds : 0) * 1000));
  const h = Math.floor(totalMs / 3_600_000);
  const m = Math.floor(totalMs / 60_000) % 60;
  const s = Math.floor(totalMs / 1000) % 60;
  const ms = totalMs % 1000;
  const pad = (value: number, width: number) => String(value).padStart(width, "0");
  const tail = `${pad(s, 2)}.${pad(ms, 3)}`;
  return h > 0 ? `${h}:${pad(m, 2)}:${tail}` : `${m}:${tail}`;
}
