import { useState } from "react";

import { thumbUrl } from "../../helpers/thumb";

// Ảnh keyframe có thể chưa tải về — trên máy dev chỉ có 35 481 / 868 524 ảnh,
// và toàn bộ prefix L2x không có ảnh nào. Một <img> trần sẽ vẽ icon ảnh vỡ,
// nên mọi chỗ hiện keyframe phải đi qua đây.
export default function KeyframeImg({
  src,
  alt,
  className,
  title,
  onClick,
  thumb = false,
}: {
  src?: string;
  alt: string;
  className?: string;
  title?: string;
  onClick?: () => void;
  /** Ô nhỏ: thử thumbnail 384 px trước, chưa có thì lùi về ảnh gốc. */
  thumb?: boolean;
}) {
  const [broken, setBroken] = useState(false);
  // Nhớ THEO src: thẻ được dùng lại cho ảnh khác thì thử thumbnail lại từ đầu.
  const [thumbFailedFor, setThumbFailedFor] = useState<string | null>(null);
  const tryThumb = thumb && !!src && thumbFailedFor !== src && thumbUrl(src) !== src;

  if (broken || !src) {
    return (
      <div
        className={`${className ?? ""} bg-proto-dark flex items-center justify-center`}
        title={title}
        onClick={onClick}
      >
        <span className="text-[9px] text-neutral-400 px-1 text-center leading-tight">
          Chưa tải ảnh
        </span>
      </div>
    );
  }

  return (
    <img
      src={tryThumb ? thumbUrl(src) : src}
      alt={alt}
      title={title}
      loading="lazy"
      decoding="async"
      onClick={onClick}
      // Thumbnail lỗi (chưa tạo tới) thì thử ảnh gốc; ảnh gốc lỗi mới là vỡ.
      onError={() => (tryThumb ? setThumbFailedFor(src) : setBroken(true))}
      className={className}
    />
  );
}
