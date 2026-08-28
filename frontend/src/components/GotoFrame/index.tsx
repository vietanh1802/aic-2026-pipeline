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
    <div className="font-baloo">
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
        className="w-[230px] px-3 py-1.5 rounded-md border border-proto-line bg-white text-[12.5px] font-mono text-proto-ink"
      />
      {error && (
        <p className="mt-1 text-[11px] text-[#c64545] max-w-[230px]">{error}</p>
      )}
    </div>
  );
}
