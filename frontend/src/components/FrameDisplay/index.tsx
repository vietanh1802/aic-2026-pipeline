import type { SearchResult } from "../../types/api";
import Skeleton from "react-loading-skeleton"; // nếu bạn dùng react-loading-skeleton
import "react-loading-skeleton/dist/skeleton.css";

// type FrameDisplayProps = {
//   frame: string;
//   distance: number;
//   url: string;
//   onClick: () => void;
//   maxDistance: number;
// };

type FrameDisplayProps2 = {
  results: SearchResult[];
  maxDistance: number;
  isLoading: boolean;
  onClick: (result: SearchResult) => void;
  // MỚI — optional, không truyền thì nút "⏱" không hiện, không ảnh hưởng
  // chỗ nào đang gọi <FrameDisplay ... /> mà chưa cập nhật. Dùng để chọn
  // 1 frame làm mốc (anchor) cho Temporal Search (Alg.4) — xem
  // TemporalSearchPanel.
  onUseAsAnchor?: (result: SearchResult) => void;
};

// Calculate similarity percentage and return color
// function calculateSimilarityScore(
//   distance: number,
//   maxDistance: number,
//   minDistance: number
// ): {
//   percentage: number;
//   backgroundColor: string;
// } {
//   if (maxDistance === 0) {
//     return { percentage: 100, backgroundColor: "bg-[rgb(0,255,0)]" };
//   }
//   let percentage = 0;
//   if (minDistance == maxDistance) {
//     percentage = 0;
//   } else {
//     percentage = ((maxDistance - distance) / (maxDistance - minDistance)) * 100;
//   }
//   const normalizedScore = percentage / 100;
//   let red: number, green: number;
//   const blue: number = 0;

//   if (normalizedScore <= 0.5) {
//     red = 255;
//     green = Math.round(255 * (normalizedScore * 2));
//   } else {
//     red = Math.round(255 * (1 - (normalizedScore - 0.5) * 2));
//     green = 255;
//   }

//   const backgroundColor = `rgb(${red},${green},${blue})`;

//   return { percentage, backgroundColor };
// }

function calculateSimilarityScore(
  distance: number,
  maxDistance: number,
  minDistance: number
): {
  percentage: number;
  backgroundColor: string;
} {
  // giữ logic cũ, nhưng bỏ qua bằng cách comment
  // if (maxDistance === 0) {
  //   return { percentage: 100, backgroundColor: "bg-[rgb(0,255,0)]" };
  // }
  // let percentage = 0;
  // if (minDistance == maxDistance) {
  //   percentage = 0;
  // } else {
  //   percentage = ((maxDistance - distance) / (maxDistance - minDistance)) * 100;
  // }
  // const normalizedScore = percentage / 100;

  const percentage = distance; // distance đã là %
  const normalizedScore = percentage / 100; // để tái dùng logic màu

  let red: number, green: number;
  const blue: number = 0;

  if (normalizedScore <= 0.5) {
    red = 255;
    green = Math.round(255 * (normalizedScore * 2));
  } else {
    red = Math.round(255 * (1 - (normalizedScore - 0.5) * 2));
    green = 255;
  }

  const backgroundColor = `rgb(${red},${green},${blue})`;

  return { percentage, backgroundColor };
}

// Extract timestamp from frame filename
export function extractTimestamp(filename: string): string {
  const nameWithoutExt = filename.replace(/\.[^/.]+$/, "");
  const timestampMatch = nameWithoutExt.match(/-(\d+)$/);

  if (!timestampMatch) {
    return "Unknown";
  }

  const timestamp = parseInt(timestampMatch[1]);
  const seconds = Math.floor(timestamp / 1000);
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  const milliseconds = timestamp % 1000;

  return `${minutes.toString().padStart(2, "0")}:${remainingSeconds
    .toString()
    .padStart(2, "0")}.${milliseconds.toString().padStart(2, "0")}`;
}

// export default function FrameDisplay({
//   frame,
//   distance,
//   url,
//   onClick,
//   maxDistance,
// }: FrameDisplayProps) {
//   const timestamp = extractTimestamp(frame);
//   const { percentage, backgroundColor } = calculateSimilarityScore(
//     distance,
//     maxDistance
//   );

//   return (
// <div
//   className={`flex flex-col gap-y-1 p-2 pb-1 rounded-[8px] w-full h-full font-baloo`}
//   style={{ backgroundColor: backgroundColor }}
// >
//   <div className="relative w-full h-full ">
//     <img
//       src={url}
//       alt={`Frame at ${timestamp}`}
//       className="w-full h-full rounded-[4px]"
//     />
//     <div className="absolute bottom-0 right-0 mr-1 mb-1 hover:cursor-pointer p-1 bg-[#EFEFEF] w-fit h-fit rounded-[4px] border-2 border-[#E3E3E3]">
//       <img src="/search.svg" alt="search_icon" onClick={onClick} />
//     </div>
//   </div>
//   <div className="flex flex-row justify-between items-center w-full">
//     <div>
//       <span className="font-bold">Timestamp:</span> {timestamp}
//     </div>
//     <div className={`font-medium`}>{percentage.toFixed(1)}%</div>
//   </div>
// </div>
//   );
// }

export default function FrameDisplay({
  results,
  maxDistance,
  isLoading,
  onClick,
  onUseAsAnchor,
}: FrameDisplayProps2) {
  const timestamp = results.map((result) => {
    return extractTimestamp(result.frame);
  });
  const minDistance = Math.min(...results.map((r) => r.distance));
  const sub = results.map((result) => {
    return calculateSimilarityScore(result.distance, maxDistance, minDistance);
  });

  return (
    <>
      {!isLoading
        ? results.map((result, index) => {
            return (
              <div
                key={index}
                className="flex flex-col gap-y-1 p-2 pb-1 rounded-[8px] w-full h-full font-baloo"
                style={{ backgroundColor: sub[index].backgroundColor }}
              >
                <div className="font-bold">{result.name}</div>
                <div className="relative w-full h-full ">
                  <img
                    src={result.url}
                    alt={`Frame at ${timestamp[index]}`}
                    className="w-full h-full rounded-[4px]"
                  />
                  {/* MỚI — dùng frame này làm mốc cho Temporal Search (Alg.4).
                      stopPropagation() để không kích hoạt luôn onClick cũ
                      (mở VideoPopup). Đặt góc trên-phải để không đè lên nút
                      search icon sẵn có ở góc dưới-phải. */}
                  {onUseAsAnchor && (
                    <div
                      className="absolute top-0 right-0 mr-1 mt-1 hover:cursor-pointer p-1 bg-[#EFEFEF] w-fit h-fit rounded-[4px] border-2 border-[#E3E3E3]"
                      title="Dùng làm mốc cho Temporal Search"
                      onClick={(e) => {
                        e.stopPropagation();
                        onUseAsAnchor(result);
                      }}
                    >
                      ⏱
                    </div>
                  )}
                  <div className="absolute bottom-0 right-0 mr-1 mb-1 hover:cursor-pointer p-1 bg-[#EFEFEF] w-fit h-fit rounded-[4px] border-2 border-[#E3E3E3]">
                    <img
                      src="/search.svg"
                      alt="search_icon"
                      onClick={() => onClick(result)}
                    />
                  </div>
                </div>
                <div className="flex flex-row justify-between items-center w-full">
                  <div>
                    <span className="font-bold">Timestamp:</span>{" "}
                    {timestamp[index]}
                  </div>
                  <div className="font-medium">
                    {sub[index].percentage.toFixed(1)}%
                  </div>
                </div>
              </div>
            );
          })
        : Array.from({ length: 25 }).map((_, index) => (
            <div
              key={index}
              className="flex flex-col gap-y-1 p-2 pb-1 rounded-[8px] w-full h-full font-baloo bg-white shadow"
            >
              <div className="relative w-full aspect-[3/2]">
                <Skeleton
                  className="w-full h-full rounded-[4px]"
                  containerClassName="w-full h-full"
                />
                <div className="absolute bottom-0 right-0 mr-1 mb-1 p-1 bg-[#EFEFEF] w-fit h-fit rounded-[4px] border-2 border-[#E3E3E3]">
                  <Skeleton width={20} height={20} />
                </div>
              </div>
              <div className="flex flex-row justify-between items-center w-full mt-1">
                <div className="flex-1 mr-2">
                  <Skeleton height={16} width="70%" />
                </div>
                <Skeleton height={16} width={40} />
              </div>
            </div>
          ))}
    </>
  );
}