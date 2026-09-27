import { useState } from "react";

import { fpsOf } from "../../helpers/frameIdentity";
import { parseFrameRef } from "../../helpers/frameRef";
import { usePopupStore } from "../../store/popupStore";

/**
 * "Look at L01_V001 1234" in chat, and one paste later the video is open there.
 *
 * The video is checked against fps_map.json before anything opens, because a
 * popup on a video with no fps seeks to zero and says nothing about why.
 */
export default function GotoFrame() {
  const open = usePopupStore((state) => state.open);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const go = () => {
    const ref = parseFrameRef(text);
    if (!ref) {
      setError("Không đọc được. Ví dụ: L01_V001 1234");
      return;
    }
    if (!fpsOf(ref.videoId)) {
      setError(`Không có video ${ref.videoId}`);
      return;
    }
    setError(null);
    open(ref.videoId, ref.frameIdx);
  };

  return (
    // `relative` để câu báo lỗi treo ở dưới mà không đội thanh điều hướng lên
    // cao thêm một dòng — ô này giờ nằm TRONG thanh đó, nên mọi thay đổi chiều
    // cao của nó đều đẩy cả trang xuống.
    <div className="font-baloo relative">
      <input
        type="text"
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          setError(null);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            go();
          }
        }}
        placeholder="Tới frame — L01_V001 1234"
        title="Dán video + frame, hoặc tên file keyframe, rồi Enter"
        className="w-[210px] px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-mono text-proto-ink"
      />
      {error && (
        <p className="absolute left-0 top-full mt-1 z-30 w-[230px] rounded-[6px] border border-[#c64545] bg-white px-2 py-1 text-[11px] text-[#c64545] shadow-sm">
          {error}
        </p>
      )}
    </div>
  );
}
