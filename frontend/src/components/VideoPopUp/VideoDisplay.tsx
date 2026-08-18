import React, { useEffect, useMemo, useRef, useState } from "react";
import Button from "../Button";
import Dropdown, { type DropdownOption } from "../DropDown";
import { useSubmitStore } from "../../store/submitStore";

const env = (import.meta as { env?: Record<string, string | undefined> }).env;

// The only video store. Empty in local dev, which disables playback there.
const VIDEO_BASE_URL = env?.VITE_VIDEO_BASE_URL ?? "";

interface DriveVideoProps {
  videoId: string; // e.g. "L30_V095" — builds the key in the video store
  width?: number;
  height?: number;
  onDuration: (duration: number) => void;
  onFrameIdx: (frameIdx: string) => void;
  setStartAt: (val: number) => void;
  jumpTo: number;
  mapping_frame: {
    smaller: string;
    larger: string;
  };
  frame_detect: number;
}

const VideoDrive: React.FC<DriveVideoProps> = ({
  videoId,
  width = 160,
  height = 120,
  onDuration,
  onFrameIdx,
  setStartAt,
  jumpTo,
  mapping_frame,
  frame_detect,
}) => {
  const frameIdxSet = useSubmitStore((state) => state.frameIdxSet);
  const setFrameIdxSet = useSubmitStore((state) => state.setFrameIdxSet);
  const [error, setError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [keyframe, setKeyframe] = useState(mapping_frame);
  useEffect(() => {
    setKeyframe(mapping_frame);
  }, [mapping_frame]);

  // S3 is the only source. All 1,478 videos are uploaded and remuxed with
  // `-movflags +faststart`, so the moov atom sits ahead of the media data and a
  // seek costs one range request.
  //
  // The Drive fallback that used to follow this was removed. The originals on
  // Drive are not faststart, so `preload="metadata"` had to pull most of a
  // 400 MB file before the player could report a duration. Whenever the S3
  // request failed the player fell through to Drive and stalled for minutes with
  // no indication of why. Failing here instead is both faster and legible, and
  // the Link button in VideoPopUp still opens the file on Drive.
  const src = useMemo(
    () =>
      VIDEO_BASE_URL && videoId
        ? `${VIDEO_BASE_URL.replace(/\/$/, "")}/${videoId}.mp4`
        : "",
    [videoId]
  );

  useEffect(() => {
    setError(null);
  }, [videoId]);

  useEffect(() => {
    if (videoRef.current && jumpTo !== undefined) {
      videoRef.current.currentTime = jumpTo;
    }

    onFrameIdx(jumpTo.toString());
  }, [jumpTo]);

  const frameIdxSetOptions: DropdownOption[] = [
    { id: 0, label: "1", value: "1" },
    { id: 1, label: "5", value: "5" },
    { id: 2, label: "10", value: "10" },
    { id: 3, label: "15", value: "15" },
  ];

  return (
    <div className="space-y-2 w-full font-baloo">
      <video
        ref={videoRef}
        key={src}
        src={src}
        width={width}
        height={height}
        controls
        preload="metadata"
        className="rounded-xl shadow w-full"
        // Duration comes from the element, not from the Drive metadata call.
        // VideoPopUp gates the whole submission form on it, so tying it to a
        // third-party request would take the form down with Drive.
        onLoadedMetadata={(e) => {
          const d = e.currentTarget.duration;
          if (Number.isFinite(d) && d > 0) onDuration(d);
          setError(null);
          if (jumpTo !== undefined) e.currentTarget.currentTime = jumpTo;
        }}
        onError={() => {
          console.warn(`video ${videoId} could not be loaded from ${src}`);
          setError(
            `Không tải được ${videoId}.mp4 từ kho video. Dùng nút Link để mở trên Drive.`
          );
        }}
      />

      {error && <p className="text-red-500">Error: {error}</p>}
      <div className="flex flex-row items-center justify-between">
        <div className="flex items-center justify-center gap-2">
          <div>
            <p>
              Keyframe Match{" "}
              <span className="text-red-500 font-bold"> Lower</span>:{" "}
              {keyframe.smaller}
            </p>
            <p>
              Keyframe Match{" "}
              <span className="text-green-500 font-bold"> Higher</span>:{" "}
              {keyframe.larger}
            </p>{" "}
          </div>
          <Dropdown
            options={frameIdxSetOptions}
            value={frameIdxSet}
            onChange={(opt) => setFrameIdxSet(opt.value)}
            dropDownWidth={100}
            dropDirection="up"
            size="sm"
          />
        </div>
        <div className="flex items-center justify-center gap-2">
          <Button
            className="bg-blue-500 hover:bg-blue-600 text-white px-4 rounded-md shadow-sm transition-all duration-300 flex-1 h-7"
            size="xs"
            onClick={() =>
              setStartAt((jumpTo - parseInt(frameIdxSet) / frame_detect) * 1000)
            }
          >
            -
          </Button>
          <Button
            className="bg-blue-500 hover:bg-blue-600 text-white px-4 rounded-md shadow-sm transition-all duration-300 flex-1 h-7"
            size="xs"
            onClick={() =>
              setStartAt((jumpTo + parseInt(frameIdxSet) / frame_detect) * 1000)
            }
          >
            +
          </Button>
          <div>
            <p>Frame_idx: {Math.floor(jumpTo * frame_detect)}</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VideoDrive;
