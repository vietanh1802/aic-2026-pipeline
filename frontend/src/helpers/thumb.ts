/**
 * Thumbnail 384 px của một keyframe: ".../images/<tên>.jpg" -> ".../images/t/<tên>.jpg".
 *
 * Ảnh batch 2 là 1920x1080, 160–415 KB, hiện trong ô ~240 px; trên mạng phòng
 * thi ~2,7 Mbit/s một trang 100 ảnh mất 1–2 phút. Thumbnail ~15 KB. Chúng được
 * tạo dần trên EC2 (script thumbs.py), nên chỗ nào dùng cũng PHẢI lùi về ảnh
 * gốc khi thumbnail chưa có. URL không đúng dạng thì trả nguyên như cũ.
 */
export function thumbUrl(url: string): string;
export function thumbUrl(url: string | undefined): string | undefined;
export function thumbUrl(url: string | undefined): string | undefined {
  if (!url) {
    return url;
  }
  return url.replace(/\/images\/([^/]+\.jpg)$/i, "/images/t/$1");
}
