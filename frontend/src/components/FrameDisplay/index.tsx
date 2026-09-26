// frontend/src/components/FrameDisplay/index.tsx

import { useEffect, useRef } from "react";
import type { OcrSearchResult, SearchResult } from "../../types/api";
import Skeleton from "react-loading-skeleton"; // nếu bạn dùng react-loading-skeleton
import "react-loading-skeleton/dist/skeleton.css";
import { accuracyColor, accuracyPercent } from "./accuracy";
import { videoOf } from "../../helpers/focusFilter";
import { frameClock, frameIndexFromResult, frameMsOf } from "../../helpers/frameIdentity";
import { pickedKind, type GroupInfoByFrame } from "../../helpers/groupResults";
import { describeTextFilter } from "../../helpers/textFilter";
import TextSignalBadge from "../TextSignalBadge";
import GroupBadge from "./GroupBadge";
import { useSearchStore } from "../../store/useSearchStore";
import { useQueryStore } from "../../store/queryStore";

/**
 * The OCR text read off this frame — only present on OCR-route results.
 *
 * Visual-route results carry no `ocr_text`, so this renders nothing and every
 * existing <FrameDisplay/> call site is unaffected.
 *
 * Printed onto the card rather than hidden in a tooltip: reading the line is
 * what tells you instantly whether this is the frame you want, without zooming
 * into each image. That is precisely why the OCR route beats the visual one
 * when the screen carries text.
 */
function OcrLine({ result }: { result: SearchResult }) {
  const text = (result as OcrSearchResult).ocr_text;
  if (!text) return null;
  const wholePhrase = (result as OcrSearchResult).exact_phrase;
  const lines = text.split("\n").filter((l) => l.trim());
  // Chữ dài thì thu nhỏ cỡ chữ: một slide bài giảng có thể ra hơn 1000 ký tự,
  // và ở cỡ thường thì chỉ riêng nó đã cao gấp ba lần cái ảnh.
  const dense = text.length > 260;

  return (
    <div
      // KHÔNG dùng line-clamp nữa. Bản trước cắt ở 3 dòng, mà 3 dòng đầu của
      // một khung tin tức thường chỉ là tên đài với dòng chữ chạy — đúng phần
      // vô dụng nhất, còn phần đáng đọc thì bị giấu.
      //
      // Cũng không cho nó dài tuỳ ý: lưới dùng auto-fill nên một thẻ cao sẽ
      // kéo cao cả hàng. Chặn chiều cao rồi cho cuộn RIÊNG trong khối này —
      // thẻ vẫn đều nhau mà vẫn đọc được hết.
      className={`mt-0.5 max-h-40 overflow-y-auto whitespace-pre-wrap break-words
        leading-snug pr-1 ${dense ? "text-[10px]" : ""} ${
        wholePhrase ? "font-bold text-proto-body" : "text-proto-muted"
      }`}
      title={`${lines.length} dòng · ${text.length} ký tự`}
    >
      {text}
    </div>
  );
}

/**
 * How well this frame matched — read differently per route.
 *
 * The visual route keeps the red-to-green percentage: its scores really are a
 * similarity spread, and where a frame sits within the current result set is
 * the useful thing to see.
 *
 * The OCR route does not, because it has no such spread. Its `distance` is the
 * number of matched words plus 1000 for a whole-phrase hit — printing it as a
 * percentage produced "5.0%" on every card, which is neither a percentage nor
 * a difference between the cards. What actually separates two OCR hits is
 * whether the typed text appeared as ONE PHRASE or as words scattered across
 * the frame, so that is what this says.
 */
function MatchLabel({
  result,
  minScore,
  maxScore,
  shown,
}: {
  result: SearchResult;
  minScore: number;
  maxScore: number;
  shown: number;
}) {
  const ocr = result as OcrSearchResult;

  if (typeof ocr.total_words === "number") {
    const whole = ocr.exact_phrase;
    return (
      <span
        className={`font-bold tabular-nums ${
          whole ? "text-[#3d7a4d]" : "text-proto-muted"
        }`}
        title={
          whole
            ? "Cả cụm chữ nằm liền một mạch trên frame này"
            : "Đủ các chữ đã gõ, nhưng nằm rời rạc trên frame"
        }
      >
        {whole ? "nguyên cụm" : `khớp ${ocr.matched_words}/${ocr.total_words} chữ`}
      </span>
    );
  }

  return (
    <span
      className="font-bold tabular-nums"
      style={{
        color: accuracyColor(accuracyPercent(result.distance, minScore, maxScore)),
      }}
      title={`điểm thô ${result.distance.toFixed(
        2
      )} · thang màu chuẩn hoá theo ${shown} kết quả đang hiện`}
    >
      {result.distance.toFixed(1)}%
    </span>
  );
}

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
  /**
   * Tên keyframe cần khoanh đỏ, vd "L21_V001-0028-3175.jpg".
   *
   * Là khung ĐANG ĐƯỢC CHỌN. Sau khi bấm "Coi X làm" thì đó là khung X đã bấm
   * trong lưới — không phải đáp án cuối X bỏ vào giỏ, mà là cái thẻ X mở ra
   * đầu tiên rồi mới chỉnh tới lui trong popup. Đó mới là chỗ bạn cần bắt đầu
   * để đi lại đường của X.
   *
   * Không truyền thì không thẻ nào được khoanh, nên mọi chỗ gọi FrameDisplay
   * chưa cập nhật vẫn chạy nguyên.
   */
  highlightFrame?: string;
  /**
   * Tên người mình vừa chép trạng thái từ đó, in lên chính cái khoanh.
   * Bỏ trống khi tự bấm chọn — lúc đó nhãn ghi "khung bạn đã chọn".
   */
  highlightLabel?: string;
  /**
   * Set only while the "one card per video" option is on (App.tsx). Keyed by
   * the name of the frame a card shows: how many frames of that video the card
   * stands for, and their names. Two things depend on it: a "N khung" badge on a
   * card with more than one, and the picked-frame ring, which must also land on
   * the card whose group HIDES the picked frame.
   *
   * Absent (the option off, and every caller that does not know about it), the
   * component renders exactly as it did before this prop existed.
   */
  groupInfoByFrame?: GroupInfoByFrame;
};

// DEPRECATED - no callers left. Kept (not deleted) with the reason: it reads the
// trailing number of a keyframe name as MILLISECONDS, but that number is the
// frame index, so it shows the wrong time for every video (36128 -> 00:36.128,
// really 20:05.472 at 29.97 fps). Use frameClock() in helpers/frameIdentity.ts.
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

// The backend's timestamp, else one computed from frame_idx / fps (frameClock).
// Old fallback, kept for the record: extractTimestamp(result.frame) read the
// trailing frame number as milliseconds, so frame 36128 printed 00:36.128
// instead of 00:20:05.472.
function frameTimestamp(result: SearchResult): string {
  return (
    result.timestamp ||
    frameClock(videoOf(result), frameIndexFromResult(result)) ||
    "Unknown"
  );
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
  highlightFrame,
  highlightLabel,
  groupInfoByFrame,
}: FrameDisplayProps2) {
  // Text-signal annotation (ASR/OCR match) from /ensemble-search, read
  // directly from the stores rather than threaded through as props — purely
  // additive metadata, so every existing <FrameDisplay .../> call site is
  // unaffected. null/missing -> TextSignalBadge renders nothing.
  const videoAnnotations = useSearchStore((state) => state.videoAnnotations);
  // Two independent filters now (ASR and OCR). The badge still takes one
  // filterQuery and one mode string, so compose them here (describeTextFilter);
  // each field is its own selector so no new object is created per render.
  const asrFilter = useQueryStore((state) => state.asrFilter);
  const asrFilterMode = useQueryStore((state) => state.asrFilterMode);
  const ocrFilter = useQueryStore((state) => state.ocrFilter);
  const ocrFilterMode = useQueryStore((state) => state.ocrFilterMode);
  const { term: textFilter, mode: textFilterMode } = describeTextFilter({
    asrFilter,
    asrFilterMode,
    ocrFilter,
    ocrFilterMode,
  });

  const timestamp = results.map(frameTimestamp);
  // The ramp is normalised across the results actually on screen. Raw distance
  // spans a narrow band (a measured run went 100.0 to 86.15), so without this
  // every tile lands in the same shade.
  const scores = results.map((r) => r.distance);
  const minScore = scores.length ? Math.min(...scores) : 0;
  const maxScore = scores.length ? Math.max(...scores) : 0;

  // Cuộn tới thẻ được khoanh khi nó vừa xuất hiện.
  //
  // Khoanh đậm cỡ nào cũng vô nghĩa nếu thẻ nằm ở hàng thứ tám: bấm "Coi X
  // làm" xong thì thấy một lưới kết quả trông y như mọi lưới khác, phải tự dò
  // mới ra khung X đã bấm — mà đó chính là thứ vừa bấm nút để xem.
  //
  // `block: "center"` chứ không phải "start": khối đề bài + video ở trên được
  // ghim lại, nên căn lên đầu sẽ đẩy thẻ nằm khuất ngay dưới khối đó.
  const pickedRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!highlightFrame || isLoading) {
      return;
    }
    // Đợi một nhịp để lưới vẽ xong; scrollIntoView trên phần tử vừa mount
    // trong cùng một lượt render sẽ tính sai vị trí.
    const timer = window.setTimeout(() => {
      pickedRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 60);
    return () => window.clearTimeout(timer);
  }, [highlightFrame, isLoading, results]);

  return (
    <>
      {!isLoading
        ? results.map((result, index) => {
            // So theo `name` chứ không theo thứ hạng: cùng một truy vấn chạy
            // lại có thể xáo nhẹ thứ tự khi index được cập nhật, còn tên
            // keyframe thì cố định.
            // Old rule, kept for the record:
            //   const picked = highlightFrame !== undefined && result.name === highlightFrame;
            // Still what pickedKind answers without groupInfoByFrame. With it, a
            // card also counts as picked when the picked frame is folded into it.
            const pickedHow = pickedKind(result, highlightFrame, groupInfoByFrame);
            const picked = pickedHow !== null;
            const group = groupInfoByFrame?.get(result.name);
            // Cards belonging to a pinned video, so a pin reads as "marked"
            // on sight even while the grid still shows every other video too
            // (shownResults only narrows down when showOnlyPinned is on --
            // see App.tsx). Same focusVideos.includes(videoOf(result)) check
            // the pin button itself already uses for its own active state.
            const pinned = focusVideos.includes(videoOf(result));
            return (
              <div
                key={index}
                // Viền xám, không còn tô theo độ khớp.
                //
                // Trước đây viền chạy từ đỏ qua vàng sang xanh theo điểm. Với
                // 50 thẻ đứng cạnh nhau thì đó là 50 mảng màu tranh nhau, mà
                // dải điểm thật lại rất hẹp — một lần đo đi từ 100.0% xuống
                // 98.8%, tức gần như cùng một màu. Màu đó không phân biệt được
                // thẻ nào với thẻ nào, chỉ làm nhiễu đúng thứ cần nhìn là ẢNH.
                //
                // Con số phần trăm ở góc dưới vẫn giữ màu — nó đọc được chính
                // xác, và một chữ nhỏ thì không lấn ảnh như một khung bao quanh.
                //
                // Thẻ được khoanh phải nhìn ra NGAY giữa 50 thẻ giống hệt nhau.
                //
                // Bản trước chỉ có `ring-4` mảnh, và hồi đó mọi thẻ còn viền
                // màu theo điểm nên vòng đỏ lẫn vào đám ấy. Giờ viền chung là
                // xám nhạt, nên thẻ được khoanh đổi hẳn: viền đỏ dày, quầng đỏ
                // bên ngoài, đổ bóng đỏ, và nhô lên một chút. Bốn thứ cùng lúc
                // vì một mình cái nào cũng có thể chìm khi cuộn nhanh.
                ref={picked ? pickedRef : undefined}
                className={`relative flex flex-col rounded-[8px] w-full h-full font-baloo bg-white overflow-hidden ${
                  picked
                    ? "border-[3px] border-[#c64545] ring-4 ring-[#c64545]/40 ring-offset-2 ring-offset-proto-canvas shadow-lg shadow-[#c64545]/35 scale-[1.02] z-10"
                    : pinned
                    ? "border-2 border-proto-primary ring-2 ring-proto-primary/30"
                    : "border-2 border-proto-line"
                }`}
              >
                {picked && (
                  <span className="absolute top-0 left-0 right-0 z-10 bg-[#c64545] text-white text-[11px] font-bold px-2 py-1 text-center tracking-wide">
                    {pickedHow === "hidden"
                      ? // The picked frame is another frame of this video, folded
                        // into this card; saying "this frame" would be wrong.
                        highlightLabel
                        ? `${highlightLabel} bấm vào một khung của video này`
                        : "khung bạn đã chọn nằm trong video này"
                      : highlightLabel
                      ? `${highlightLabel} bấm vào khung này`
                      : "khung bạn đã chọn"}
                  </span>
                )}
                <div className="relative w-full aspect-[3/2] bg-proto-dark">
                  {result.has_image === false ? (
                    <MissingFrame name={result.name} />
                  ) : (
                    <img
                      src={result.url}
                      alt={`Frame at ${timestamp[index]}`}
                      loading="lazy"
                      // Keyframes are full 1280x720 JPEGs shown in a ~240px
                      // tile, so each one costs a real decode. Async keeps
                      // that off the main thread and stops the grid janking
                      // while a screenful comes in.
                      decoding="async"
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
                  {/* Text-signal badge — overlaid on the image corner rather
                      than inserted into the metadata block below, so it adds
                      no height to the card (same convention as TRAKE's "tay"
                      badge in CandidateResults). */}
                  {videoAnnotations && Object.keys(videoAnnotations).length > 0 && (
                    <div className="absolute top-0 right-0 mt-1 mr-1 z-20">
                      <TextSignalBadge
                        videoId={videoOf(result)}
                        annotation={videoAnnotations[videoOf(result)]}
                        filterQuery={textFilter}
                        mode={textFilterMode}
                        cardFrame={result.name}
                      />
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
                    {group && <GroupBadge count={group.count} />}
                  </span>
                  <span className="flex items-center justify-between">
                    {/* frame · ms cạnh đồng hồ: DRES chung kết nộp bằng ms.
                        Was: <span>{timestamp[index]}</span> */}
                    <span className="truncate">
                      {timestamp[index]}
                      <span className="font-mono">
                        {" · "}
                        {frameIndexFromResult(result)}
                        {frameMsOf(videoOf(result), frameIndexFromResult(result)) !== null &&
                          ` · ${frameMsOf(videoOf(result), frameIndexFromResult(result))} ms`}
                      </span>
                    </span>
                    <MatchLabel
                      result={result}
                      minScore={minScore}
                      maxScore={maxScore}
                      shown={scores.length}
                    />
                  </span>
                  <OcrLine result={result} />
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
                        className="flex h-7 w-7 items-center justify-center rounded-[4px] border-2 border-proto-line bg-proto-soft"
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
                            : "bg-proto-soft border-proto-line"
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
                      className="flex h-7 w-7 items-center justify-center rounded-[4px] border-2 border-proto-line bg-proto-soft"
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
                <div className="absolute bottom-0 right-0 mr-1 mb-1 p-1 bg-proto-soft w-fit h-fit rounded-[4px] border-2 border-proto-line">
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