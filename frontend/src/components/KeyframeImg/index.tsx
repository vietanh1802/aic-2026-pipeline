import { useState } from "react";

// Ảnh keyframe có thể chưa tải về — trên máy dev chỉ có 35 481 / 868 524 ảnh,
// và toàn bộ prefix L2x không có ảnh nào. Một <img> trần sẽ vẽ icon ảnh vỡ,
// nên mọi chỗ hiện keyframe phải đi qua đây.
export default function KeyframeImg({
  src,
  alt,
  className,
  title,
  onClick,
}: {
  src?: string;
  alt: string;
  className?: string;
  title?: string;
  onClick?: () => void;
}) {
  const [broken, setBroken] = useState(false);

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
      src={src}
      alt={alt}
      title={title}
      loading="lazy"
      decoding="async"
      onClick={onClick}
      onError={() => setBroken(true)}
      className={className}
    />
  );
}
