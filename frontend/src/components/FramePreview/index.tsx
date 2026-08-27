import KeyframeImg from "../KeyframeImg";
import { nearestKeyframeFor } from "../../helpers/keyframes";
import { keyframeUrl } from "../../helpers/videoSource";

/**
 * The still nearest a frame number.
 *
 * A basket row knows only a video and a frame — there is no URL on it, and
 * asking the backend for one would be a request per row. The keyframe index
 * answers it locally, and an arbitrary frame lands on the keyframe beside it.
 *
 * Positioning is the caller's: the basket uses `thumb` inline and `large`
 * floating on hover.
 */
export default function FramePreview({
  videoId,
  frameIdx,
  size = "thumb",
  className,
}: {
  videoId: string;
  frameIdx: number;
  size?: "thumb" | "large";
  className?: string;
}) {
  const keyframe = nearestKeyframeFor(videoId, frameIdx);
  const box = size === "large" ? "w-[360px] h-[240px]" : "w-12 h-8";
  const exact = keyframe?.frameIdx === frameIdx;

  return (
    <KeyframeImg
      src={keyframe ? keyframeUrl(keyframe.name) : undefined}
      alt={`${videoId} · frame ${frameIdx}`}
      title={
        keyframe
          ? exact
            ? keyframe.name
            : `${keyframe.name} — keyframe gần frame ${frameIdx} nhất`
          : `${videoId} · frame ${frameIdx} — không có keyframe`
      }
      className={`${box} shrink-0 rounded-[4px] object-cover bg-proto-dark ${
        className ?? ""
      }`}
    />
  );
}
