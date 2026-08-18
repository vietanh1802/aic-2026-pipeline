import React, { useEffect, useMemo, useRef, useState } from "react";
import Button from "../Button";
import Dropdown, { type DropdownOption } from "../DropDown";
import { useSubmitStore } from "../../store/submitStore";

const env = (import.meta as { env?: Record<string, string | undefined> }).env;

// Primary video store. Empty (local dev) falls straight through to Drive.
const VIDEO_BASE_URL = env?.VITE_VIDEO_BASE_URL ?? "";
// drive-video-proxy, needed only for videos that are not publicly shared:
// public files stream from the Drive API directly (verified: HTTP 206, ranged).
const PROXY_BASE_URL = env?.VITE_PROXY_BASE_URL ?? "";

interface DriveVideoProps {
  videoId: string; // e.g. "L30_V095" — builds the key in the video store
  fileId: string; // Drive id, used by the fallback chain
  apiKey?: string; // required to call the Drive API
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
  fileId,
  apiKey = "AIzaSyAWUVtVvwOTA52orDVhTU9b9xrBwx7pWH0",
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

  // Sources tried in order. While the seed job runs (hours), a video not yet
  // uploaded 404s and falls through to Drive, so there is no single cutover.
  const sources = useMemo(
    () =>
      [
        VIDEO_BASE_URL && videoId
          ? `${VIDEO_BASE_URL.replace(/\/$/, "")}/${videoId}.mp4`
          : null,
        fileId
          ? `https://www.googleapis.com/drive/v3/files/${fileId}?alt=media&key=${apiKey}`
          : null,
        PROXY_BASE_URL && fileId
          ? `${PROXY_BASE_URL.replace(/\/$/, "")}/video/${fileId}`
          : null,
      ].filter((s): s is string => Boolean(s)),
    [videoId, fileId, apiKey]
  );

  const [srcIdx, setSrcIdx] = useState(0);
  useEffect(() => {
    setSrcIdx(0);
    setError(null);
  }, [videoId, fileId]);

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
        key={sources[srcIdx]}
        src={sources[srcIdx]}
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
          if (srcIdx < sources.length - 1) {
            console.warn(
              `video source ${srcIdx + 1}/${sources.length} failed, trying next`
            );
            setSrcIdx((i) => i + 1);
          } else {
            setError("No working video source");
          }
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
