import React, { useEffect, useRef, useState } from "react";
import Button from "../Button";
import Dropdown, { type DropdownOption } from "../DropDown";
import { useSubmitStore } from "../../store/submitStore";
interface DriveVideoProps {
  fileId: string;
  apiKey?: string; // cần API key để gọi Drive API
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

interface VideoMetadata {
  width: number;
  height: number;
  durationMillis: string;
  rotation?: number;
}

const VideoDrive: React.FC<DriveVideoProps> = ({
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
  const [metadata, setMetadata] = useState<VideoMetadata | null>(null);
  const [error, setError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [keyframe, setKeyframe] = useState(mapping_frame);
  const [embedUrl, setEmbedUrl] = useState("");
  useEffect(() => {
    setKeyframe(mapping_frame);
  }, [mapping_frame]);

  // Lấy metadata từ Google Drive API
  useEffect(() => {
    async function fetchMetadata() {
      try {
        const url = `https://www.googleapis.com/drive/v3/files/${fileId}?fields=webContentLink,videoMediaMetadata&key=${apiKey}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error("Failed to fetch metadata");
        const data = await res.json();

        setMetadata(data.videoMediaMetadata);
        onDuration(Number(data.videoMediaMetadata.durationMillis) / 1000);

        if (data.webContentLink) {
          setEmbedUrl(data.webContentLink);
        } else {
          // fallback
          setEmbedUrl(
            `https://www.googleapis.com/drive/v3/files/${fileId}?alt=media&key=${apiKey}`
          );
        }
      } catch (err: any) {
        setError(err.message);
      }
    }
    fetchMetadata();
  }, [fileId, apiKey]);
  useEffect(() => {
    if (videoRef.current && jumpTo !== undefined) {
      videoRef.current.currentTime = jumpTo;
    }

    onFrameIdx(jumpTo.toString());
  }, [jumpTo]);
  // const embedUrl = `https://www.googleapis.com/drive/v3/files/${fileId}?alt=media&key=${apiKey}`;

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
        // src={embedUrl}
        src={`http://localhost:5000/video/${fileId}`}
        width={width}
        height={height}
        controls
        className="rounded-xl shadow w-full"
        onError={() => {
          console.warn("Primary video link failed, retrying alt=media...");
          if (embedUrl.includes("webContentLink")) {
            setEmbedUrl(
              `https://www.googleapis.com/drive/v3/files/${fileId}?alt=media&key=${apiKey}`
            );
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
