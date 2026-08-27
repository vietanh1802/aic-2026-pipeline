import type { SearchResult } from "../../types/api";
import Skeleton from "react-loading-skeleton"; // nếu bạn dùng react-loading-skeleton
import "react-loading-skeleton/dist/skeleton.css";
import { accuracyColor, accuracyPercent } from "./accuracy";
import { videoOf } from "../../helpers/focusFilter";

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
  // MỚI — optional như onUseAsAnchor: không truyền thì nút không hiện, nên
  // mọi chỗ gọi FrameDisplay chưa cập nhật vẫn chạy nguyên.
  onAddToBasket?: (result: SearchResult) => void;
  // MỚI — optional like the two above. Narrows the grid to this video.
  onToggleFocus?: (videoId: string) => void;
  focusVideos?: string[];
};

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

export function routeAgreement(result: SearchResult): "both" | "one" | "none" {
  const count = Object.keys(result.routes ?? {}).length;
  if (count >= 2) return "both";
  if (count === 1) return "one";
  return "none";
}

const AGREEMENT_DOT: Record<"both" | "one" | "none", string> = {
  both: "bg-proto-teal",
  one: "bg-proto-amber",
  none: "bg-proto-line",
};

const AGREEMENT_TITLE: Record<"both" | "one" | "none", string> = {
  both: "BEiT3 và CLIP cùng tìm ra",
  one: "chỉ một model tìm ra",
  none: "không rõ route",
};

// Timestamp từ backend, parse tên file chỉ khi backend không trả trường này.
function frameTimestamp(result: SearchResult): string {
  return result.timestamp || extractTimestamp(result.frame);
}

// Keyframe chưa tải ảnh: vẫn hiện ranking/tên/timestamp thay vì <img> vỡ.
function MissingFrame({ name }: { name: string }) {
  return (
    <div className="w-full h-full min-h-[96px] rounded-[4px] bg-proto-dark border border-dashed border-neutral-600 flex flex-col items-center justify-center text-center px-2">
      <span className="text-neutral-400 text-xs font-semibold">
        Chưa tải ảnh
      </span>
      <span className="text-neutral-500 text-[10px] break-all leading-tight mt-0.5">
        {name}
      </span>
    </div>
  );
}

export default function FrameDisplay({
  results,
  isLoading,
  onClick,
  onUseAsAnchor,
  onAddToBasket,
  onToggleFocus,
  focusVideos = [],
}: FrameDisplayProps2) {
  const timestamp = results.map(frameTimestamp);
  // The ramp is normalised across the results actually on screen. Raw distance
  // spans a narrow band (a measured run went 100.0 to 86.15), so without this
  // every tile lands in the same shade.
  const scores = results.map((r) => r.distance);
  const minScore = scores.length ? Math.min(...scores) : 0;
  const maxScore = scores.length ? Math.max(...scores) : 0;

  return (
    <>
      {!isLoading
        ? results.map((result, index) => {
            return (
              <div
                key={index}
                className="flex flex-col rounded-[8px] w-full h-full font-baloo bg-white border-2 overflow-hidden"
                style={{
                  borderColor: accuracyColor(
                    accuracyPercent(result.distance, minScore, maxScore)
                  ),
                }}
              >
                <div className="relative w-full aspect-[3/2] bg-proto-dark">
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
                </div>
                <div className="flex flex-col w-full px-2 py-1 text-xs text-proto-muted gap-0.5">
                  <span className="flex items-center gap-1 min-w-0">
                    <i
                      className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${
                        AGREEMENT_DOT[routeAgreement(result)]
                      }`}
                      title={AGREEMENT_TITLE[routeAgreement(result)]}
                    />
                    <span className="truncate">{result.name}</span>
                  </span>
                  <span className="flex items-center justify-between">
                    <span>{timestamp[index]}</span>
                    <span
                      className="font-bold tabular-nums"
                      style={{
                        color: accuracyColor(
                          accuracyPercent(result.distance, minScore, maxScore)
                        ),
                      }}
                      title={`điểm thô ${result.distance.toFixed(
                        2
                      )} · thang màu chuẩn hoá theo ${scores.length} kết quả đang hiện`}
                    >
                      {result.distance.toFixed(1)}%
                    </span>
                  </span>
                  {/* Action row — these 4 buttons used to float on top of the
                      image (+ top-left, ⏱/🎯 top-right nearly touching,
                      search bottom-right) and obscured the frame. Moved down
                      here, below the name/timestamp/score block, so the
                      image is only ever used to look at the frame. */}
                  <div className="flex items-center gap-1 pt-1">
                    {onAddToBasket && (
                      <button
                        type="button"
                        className="flex h-7 w-7 items-center justify-center rounded-[4px] bg-proto-primary text-white text-xs font-bold"
                        title="Thêm vào giỏ đáp án"
                        onClick={(e) => {
                          e.stopPropagation();
                          onAddToBasket(result);
                        }}
                      >
                        +
                      </button>
                    )}
                    {onUseAsAnchor && (
                      <button
                        type="button"
                        className="flex h-7 w-7 items-center justify-center rounded-[4px] border-2 border-[#E3E3E3] bg-[#EFEFEF]"
                        title="Dùng làm mốc cho Temporal Search"
                        onClick={(e) => {
                          e.stopPropagation();
                          onUseAsAnchor(result);
                        }}
                      >
                        ⏱
                      </button>
                    )}
                    {onToggleFocus && (
                      <button
                        type="button"
                        className={`flex h-7 w-7 items-center justify-center rounded-[4px] border-2 ${
                          focusVideos.includes(videoOf(result))
                            ? "bg-proto-primary border-proto-primary"
                            : "bg-[#EFEFEF] border-[#E3E3E3]"
                        }`}
                        title={
                          focusVideos.includes(videoOf(result))
                            ? "Bỏ lọc video này"
                            : "Chỉ xem video này"
                        }
                        onClick={(e) => {
                          e.stopPropagation();
                          onToggleFocus(videoOf(result));
                        }}
                      >
                        🎯
                      </button>
                    )}
                    <button
                      type="button"
                      className="flex h-7 w-7 items-center justify-center rounded-[4px] border-2 border-[#E3E3E3] bg-[#EFEFEF]"
                      title="Mở video"
                      onClick={() => onClick(result)}
                    >
                      <img src="/search.svg" alt="search_icon" className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        : Array.from({ length: 25 }).map((_, index) => (
            <div
              key={index}
              className="flex flex-col rounded-[8px] w-full h-full font-baloo bg-white border border-proto-line overflow-hidden"
            >
              <div className="relative w-full aspect-[3/2] bg-proto-dark">
                <Skeleton
                  className="w-full h-full rounded-[4px]"
                  containerClassName="w-full h-full"
                />
                <div className="absolute bottom-0 right-0 mr-1 mb-1 p-1 bg-[#EFEFEF] w-fit h-fit rounded-[4px] border-2 border-[#E3E3E3]">
                  <Skeleton width={20} height={20} />
                </div>
              </div>
              <div className="flex flex-row justify-between items-center w-full px-2 py-1">
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