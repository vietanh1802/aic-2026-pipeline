// Hai giá trị duy nhất client tự tính cho phần auto-discovery. Mọi thứ khác
// đọc thẳng từ response.

// Phải khớp preprocess.py:_split_query_text từng ký tự, nếu không nhãn E1…EN
// sẽ lệch so với danh sách event backend trả về:
//     parts = re.split(r"\.\s+", text.strip())
//     [p.strip().rstrip(".").strip() for p in parts if p.strip()]
export function splitQueryParts(text: string): string[] {
  return text
    .trim()
    .split(/\.\s+/)
    .map((part) => part.trim().replace(/\.+$/, "").trim())
    .filter((part) => part.length > 0);
}

export function frameGap(
  from: number,
  to: number,
  fps: number
): { frames: number; seconds: number } {
  const frames = Math.abs(to - from);
  const usable = Number.isFinite(fps) && fps > 0;
  return {
    frames,
    seconds: usable ? Math.round((frames / fps) * 10) / 10 : 0,
  };
}
