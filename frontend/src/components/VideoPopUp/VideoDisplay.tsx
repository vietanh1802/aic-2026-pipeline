// frontend/src/components/VideoPopUp/VideoDisplay.tsx

import React, { useEffect, useMemo, useState } from "react";
import Button from "../Button";
import Dropdown, { type DropdownOption } from "../DropDown";
import { useSubmitStore } from "../../store/submitStore";
import { videoUrl } from "../../helpers/videoSource";
import { frameAt } from "../../helpers/frameRange";
import { frameToMs } from "../../helpers/frameIdentity";
import { needsSeek, type SeekRequest } from "../../helpers/seekRequest";

interface DriveVideoProps {
  videoId: string; // e.g. "L30_V095" — builds the key in the video store
  width?: number;
  height?: number;
  onDuration: (duration: number) => void;
  /** Where playback actually is, in seconds. Fires on seek and while playing. */
  onPosition: (seconds: number) => void;
  /** Owned by the popup so the mark buttons can read currentTime exactly. */
  videoRef: React.RefObject<HTMLVideoElement | null>;
  setStartAt: (val: number) => void;
  jumpTo: number;
  /**
   * "Seek there" as an event: a new request moves the player even when its time
   * equals the last one, which `jumpTo` (a value, so it only fires on change)
   * cannot do. Only the candidate strip sends these; every other seek still goes
   * through `jumpTo`. See helpers/seekRequest.ts.
   */
  seekRequest?: SeekRequest | null;
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
  onPosition,
  videoRef,
  setStartAt,
  jumpTo,
  seekRequest = null,
  mapping_frame,
  frame_detect,
}) => {
  const frameIdxSet = useSubmitStore((state) => state.frameIdxSet);
  const setFrameIdxSet = useSubmitStore((state) => state.setFrameIdxSet);
  const [error, setError] = useState<string | null>(null);
  // Where the player is right now, as opposed to where it was last told to go.
  const [position, setPosition] = useState<number>(jumpTo);
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
  const src = useMemo(() => videoUrl(videoId), [videoId]);

  useEffect(() => {
    setError(null);
  }, [videoId]);

  // `jumpTo` is a deliberate seek target — opening on a keyframe, the frame
  // step buttons, a click on the mark strip. It is NOT playback position, and
  // the two are kept apart on purpose: feeding position back into it would make
  // this effect seek backwards to a stale value four times a second and fight
  // the player. Tolerance is half a frame so a single-frame step still lands.
  useEffect(() => {
    const element = videoRef.current;
    if (!element || jumpTo === undefined) return;
    if (Math.abs(element.currentTime - jumpTo) > 0.5 / (frame_detect || 25)) {
      element.currentTime = jumpTo;
    }
    setPosition(jumpTo);
    onPosition(jumpTo);
  }, [jumpTo]);

  // A seek REQUEST (the candidate strip). Runs on the request object, so pressing
  // the same block twice - with the native bar dragged elsewhere in between -
  // seeks twice; the effect above would not, because `jumpTo` never changed.
  // When the request also changed `jumpTo` (a different block) that effect has
  // already moved the player and this one finds it in place.
  useEffect(() => {
    const element = videoRef.current;
    if (!element || !seekRequest) return;
    if (needsSeek(element.currentTime, seekRequest.timeS, frame_detect)) {
      element.currentTime = seekRequest.timeS;
    }
    setPosition(seekRequest.timeS);
    onPosition(seekRequest.timeS);
    // Deliberately keyed on the request alone: `onPosition` is a new closure on
    // every render, so listing it would re-run this on each playback tick and
    // pull the player back to the requested time four times a second (the same
    // reason the jumpTo effect above is keyed on jumpTo only).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seekRequest]);

  // The player moves on its own — the native controls, playback, the keyboard.
  // Nothing used to report that back, so every frame number on screen still
  // described wherever the popup had opened.
  const report = (seconds: number) => {
    setPosition(seconds);
    onPosition(seconds);
  };

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
        onTimeUpdate={(e) => report(e.currentTarget.currentTime)}
        onSeeked={(e) => report(e.currentTarget.currentTime)}
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
              setStartAt((position - parseInt(frameIdxSet) / frame_detect) * 1000)
            }
          >
            -
          </Button>
          <Button
            className="bg-blue-500 hover:bg-blue-600 text-white px-4 rounded-md shadow-sm transition-all duration-300 flex-1 h-7"
            size="xs"
            onClick={() =>
              setStartAt((position + parseInt(frameIdxSet) / frame_detect) * 1000)
            }
          >
            +
          </Button>
          <div>
            {/* ms cạnh frame: DRES chung kết nộp bằng ms (frameToMs = đúng
                phép quy đổi của server). Was: chỉ có Frame_idx. */}
            <p>
              Frame_idx: {frameAt(position, frame_detect) ?? "—"}
              {frameToMs(frameAt(position, frame_detect), frame_detect) !== null &&
                ` · ${frameToMs(frameAt(position, frame_detect), frame_detect)} ms`}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VideoDrive;
