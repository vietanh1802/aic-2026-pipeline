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
  distance: number
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

// Chỉ dùng làm dự phòng: regex coi số cuối tên file là milliseconds, nhưng số
// đó là frame index — "K19_V001-0000-29.jpg" ra "00:00.29" thay vì 00:00:00.966
// (frame 29 @30fps). Ưu tiên trường `timestamp` của backend, xem frameTimestamp().
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

// Timestamp từ backend, parse tên file chỉ khi backend không trả trường này.
function frameTimestamp(result: SearchResult): string {
  return result.timestamp || extractTimestamp(result.frame);
}

// Keyframe chưa tải ảnh: vẫn hiện ranking/tên/timestamp thay vì <img> vỡ.
function MissingFrame({ name }: { name: string }) {
  return (
    <div className="w-full h-full min-h-[96px] rounded-[4px] bg-gray-200 border-2 border-dashed border-gray-400 flex flex-col items-center justify-center text-center px-2">
      <span className="text-gray-500 text-xs font-semibold">
        Chưa tải ảnh
      </span>
      <span className="text-gray-400 text-[10px] break-all leading-tight mt-0.5">
        {name}
      </span>
    </div>
  );
}

export default function FrameDisplay({
  results,
  isLoading,
  onClick,
}: FrameDisplayProps2) {
  const timestamp = results.map(frameTimestamp);
  const sub = results.map((result) => {
    return calculateSimilarityScore(result.distance);
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
                <div className="relative w-full aspect-[3/2]">
                  {result.has_image === false ? (
                    <MissingFrame name={result.name} />
                  ) : (
                    <img
                      src={result.url}
                      alt={`Frame at ${timestamp[index]}`}
                      loading="lazy"
                      className="w-full h-full rounded-[4px] object-cover"
                      // Dự phòng khi backend không trả has_image, hoặc ảnh biến
                      // mất sau lúc search.
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                        e.currentTarget.nextElementSibling?.classList.remove(
                          "hidden"
                        );
                      }}
                    />
                  )}
                  {result.has_image !== false && (
                    <div className="hidden absolute inset-0">
                      <MissingFrame name={result.name} />
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
