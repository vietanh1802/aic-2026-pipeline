import { useEffect, useState } from "react";
import "./App.css";
import FrameDisplay from "./components/FrameDisplay";
import Header from "./components/Header";
import ProjectDescription from "./components/ProjectDescription";
import QueryInput from "./components/QueryInput";
import ResultInfoAndSort, {
  type SortType,
} from "./components/ResultInfoAndSort";
import TaskBrief from "./components/TaskBrief";
import OcrCountBanner from "./components/OcrCountBanner";
import { useIsQueryStore, useSearchStore } from "./store/useSearchStore";
import {
  SEARCH_EMPHASIS_WEIGHTS,
  useQueryStore,
} from "./store/queryStore";
import VideoPopup from "./components/VideoPopUp";
import TemporalSearchPanel from "./components/TemporalSearchPanel";
import { videoSearchApi } from "./types/api";
import { formatResultByVideoID } from "./helpers/formatResult.helper";
import {
  TemporalCandidates,
  TrakeCandidates,
} from "./components/CandidateResults";
import type {
  EventPick,
  TrakeSwapMap,
} from "./components/CandidateResults/types";
import {
  frameIdFromName,
  startMsAt,
  videoIdFromFrame,
} from "./helpers/frameIdentity";
import { splitQueryParts } from "./helpers/candidates";
import { addAnswer } from "./api/answers";
import type { BoardTask } from "./api/board";
import type {
  HealthResponse,
  SearchResult,
  TemporalCandidateResult,
  TrakeCandidateResult,
  MultimodalVideoResult,
} from "./types/api";
import KeyframeFPS from "./mapping/fps_map.json";
import MultimodalResults from "./components/MultimodalResults";

type BackendHealth = {
  status: "checking" | "starting" | "ready" | "offline" | "failed";
  message: string;
  detail?: string;
};
function frameIndexFromResult(result: SearchResult): number {
  if (typeof result.frame_idx === "number") {
    return result.frame_idx;
  }
  return Number(result.frame.match(/-(\d+)\.jpg$/)?.[1] ?? 0);
}

function startMsFromResult(result: SearchResult): number {
  return startMsAt(videoIdFromFrame(result.frame), frameIndexFromResult(result));
}

function describeBackendHealth(health: HealthResponse): BackendHealth {
  if (!health.ok) {
    return { status: "offline", message: "API offline" };
  }
  if (health.warmup.state === "failed") {
    return {
      status: "failed",
      message: "API warm-up failed",
      detail: health.warmup.error ?? undefined,
    };
  }
  if (health.warmup.state !== "ready") {
    return {
      status: "starting",
      message: "API starting",
      detail: "Loading indexes and models",
    };
  }
  return { status: "ready", message: "API ready" };
}

function App({
  activeTask = null,
  onBasketChanged,
}: {
  /** The task claimed on the board, if any. Read-only context for the search. */
  activeTask?: BoardTask | null;
  onBasketChanged?: () => void;
} = {}) {
  const results = useSearchStore((state) => state.results);
  const maxDistance = useSearchStore((state) => state.maxDistance);
  const totalTime = useSearchStore((state) => state.totalTime);
  const resultLimit = useQueryStore((state) => state.resultLimit);
  const topM = useQueryStore((state) => state.topM);
  const useRerank = useQueryStore((state) => state.useRerank);
  const ocrStripDiacritics = useQueryStore((state) => state.ocrStripDiacritics);
  const searchType = useQueryStore((state) => state.searchType);
  const searchEmphasis = useQueryStore((state) => state.searchEmphasis);
  const singleModel = useQueryStore((state) => state.singleModel);
  const [showPopup, setShowPopup] = useState<boolean>(false);
  const [videoUrl, setVideoUrl] = useState<string>("");
  const [startTime, setStartTime] = useState<number>(0);
  const [frameId, setframeId] = useState<string>("");

  const [sortFrameBy, setSortFrameBy] = useState<SortType>("accuracy");
  const queryText = useQueryStore((state) => state.queryText);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const [backendHealth, setBackendHealth] = useState<BackendHealth>({
    status: "checking",
    message: "Checking API",
  });
  const isSearchDisabled = backendHealth.status !== "ready";

  useEffect(() => {
    let cancelled = false;

    const pollHealth = async () => {
      try {
        const health = await videoSearchApi.getHealth();
        if (!cancelled) {
          setBackendHealth(describeBackendHealth(health));
        }
      } catch (err) {
        if (!cancelled) {
          setBackendHealth({
            status: "offline",
            message: "API offline",
            detail: err instanceof Error ? err.message : "Health check failed",
          });
        }
      }
    };

    void pollHealth();
    const interval = window.setInterval(() => {
      void pollHealth();
    }, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  const healthClassName = {
    checking: "border-proto-line bg-white text-proto-muted",
    starting: "border-[#d4a017] bg-[#d4a017]/12 text-[#8a6a0f]",
    ready: "border-[#5db872] bg-[#5db872]/12 text-[#3d7a4d]",
    offline: "border-[#c64545] bg-[#c64545]/10 text-[#8f3030]",
    failed: "border-[#c64545] bg-[#c64545]/10 text-[#8f3030]",
  }[backendHealth.status];

  // ── Temporal Search (Alg.4) — anchor do người dùng tự chọn từ kết quả
  // search đã có (paper: "the initially retrieved and reranked input frame
  // corresponds to the correct reference frame"), kích hoạt qua nút "⏱"
  // trên FrameDisplay. Không thay thế gì của search thường (ensemble/single).
  const [showTemporalPanel, setShowTemporalPanel] = useState(false);
  const [temporalAnchor, setTemporalAnchor] = useState<{
    name: string;
    url: string;
  } | null>(null);

  // Đề bài của BTC là văn bản chỉ đọc; ô search bên dưới là chữ người dùng tự
  // gõ. Hai thứ không bao giờ trộn vào nhau — xem spec §6.2.
  // KIS and Q&A only. TRAKE used to land here too and submitted
  // `Array.from({length: n_events}, () => frame)` — N copies of one frame,
  // which is the right shape carrying meaningless content. A TRAKE row is
  // assembled on the TRAKE search line instead, where all N moments exist.
  const handleAddToBasket = async (result: SearchResult) => {
    if (!activeTask) {
      console.warn("[basket] Chưa mở task nào từ bảng Board.");
      return;
    }
    try {
      await addAnswer(activeTask.id, {
        video_id: videoIdFromFrame(result.frame),
        frames: [Number(result.frame_idx ?? 0)],
      });
      onBasketChanged?.();
    } catch (err) {
      console.error("Không thêm được vào giỏ:", err);
    }
  };

  const handleUseAsAnchor = (result: SearchResult) => {
    setTemporalAnchor({ name: result.name, url: result.url });
    setShowTemporalPanel(true);
  };

  // Alg.3 (ensemble) hoặc chạy 1 model đơn (Q4) — khớp đúng /ensemble-search
  // và /single-search hiện có trong main.py. Không còn text-search/faiss-
  // search/combined-search/ocr-search/filter-search — các endpoint đó đã bị
  // xóa khỏi backend (xem docstring main.py).
  // Kết quả Temporal/TRAKE — khác shape với SearchResult[] (mỗi phần tử là 1
  // VIDEO ứng viên, bên trong có N frame), nên lưu state riêng thay vì dùng
  // chung useSearchStore. CHƯA có component hiển thị — tạm console.log để
  // xác nhận data đúng, phần hiển thị (danh sách card video ứng viên) làm
  // sau, đây là bước "chỉ thêm mode search" theo đúng yêu cầu.
  const [temporalCandidates, setTemporalCandidates] = useState<
    TemporalCandidateResult[]
  >([]);
  const [trakeCandidates, setTrakeCandidates] = useState<
    TrakeCandidateResult[]
  >([]);

  const [multimodalResults, setMultimodalResults] = useState<
    MultimodalVideoResult[]
  >([]);
  const [multimodalTime, setMultimodalTime] = useState(0);
  // The OCR route's three counts. Kept out of useSearchStore because that
  // store is shared with the visual route, which has no notion of "how many
  // images contain this text".
  const [ocrCounts, setOcrCounts] = useState<{
    phrase: number;
    allWords: number;
    anyWord: number;
    searched: number;
  } | null>(null);

  // ── TRAKE line ───────────────────────────────────────────────────────────
  // Which frame each event of each card is currently standing on, when it is
  // not the one the DP chose. Held here rather than inside TrakeCard because
  // the video popup below writes into it: scrubbing to a frame and pressing
  // "Chốt cho E2" has to land back in that cell.
  const [trakeSwaps, setTrakeSwaps] = useState<TrakeSwapMap>({});
  // Set while the popup is open on one event, so the submit button says which
  // moment it is pinning instead of "Add Answer".
  const [trakeSlot, setTrakeSlot] = useState<{
    cardKey: string;
    index: number;
    label: string;
    total: number;
  } | null>(null);

  const swapTrakeEvent = (
    cardKey: string,
    index: number,
    pick: EventPick
  ) => {
    setTrakeSwaps((prev) => ({
      ...prev,
      [cardKey]: { ...(prev[cardKey] ?? {}), [index]: pick },
    }));
  };

  const openTrakeEvent = (
    cardKey: string,
    index: number,
    pick: EventPick,
    video: string
  ) => {
    const frame = pick.frame_idx ?? 0;
    // splitQueryParts rather than the `queryParts` below: this runs from a
    // click, and reading the value straight off current state keeps the two
    // declarations independent of each other's order.
    const labels = splitQueryParts(queryText);
    setframeId(pick.name ? frameIdFromName(pick.name) : String(frame));
    setVideoUrl(video);
    setStartTime(startMsAt(video, frame));
    setTrakeSlot({
      cardKey,
      index,
      label: labels[index] ?? `E${index + 1}`,
      total: activeTask?.n_events ?? labels.length,
    });
    setShowPopup(true);
  };

  // The whole line, as one row. Fires only when every event has a frame.
  const commitTrakeRow = async (video: string, frames: number[]) => {
    if (!activeTask) {
      console.warn("[basket] Chưa mở task nào từ bảng Board.");
      return;
    }
    try {
      await addAnswer(activeTask.id, { video_id: video, frames });
      onBasketChanged?.();
    } catch (err) {
      console.error("Không thêm được dòng TRAKE vào giỏ:", err);
    }
  };

  const doSearch = async () => {
    if (isSearchDisabled) {
      console.warn(`[health] Search blocked: ${backendHealth.message}`);
      return;
    }
    setIsLoading(true);

    if (searchType === "multimodal") {
      setMultimodalResults([]);
    } else if (searchType === "ocr") {
      setOcrCounts(null);
      useSearchStore.getState().setResults([]);
      useSearchStore.getState().setMaxDistance(0);
    } else if (searchType === "temporal") {
      setTemporalCandidates([]);
    } else if (searchType === "trake") {
      setTrakeCandidates([]);
    } else {
      useSearchStore.getState().setResults([]);
      useSearchStore.getState().setMaxDistance(0);
    }
    try {
      if (searchType === "temporal") {
        // topVideos: mặc định 5 quá ít khi video ứng viên trùng lặp/gần
        // giống nhau — tăng lên 20 (không thêm control UI nào, giữ nguyên
        // khung nhập). Chi phí: mỗi candidate chạy 1 lần temporal_search()
        // đầy đủ (bidirectional expansion, tối đa ~40 score_frame()/video) —
        // 20 video vẫn rẻ, không đáng lo hiệu năng.
        const res = await videoSearchApi.temporalSearchText(queryText, {
          topVideos: 20,
        });
        if (res.error) {
          console.error("Temporal search text error:", res.error);
          setTemporalCandidates([]);
        } else {
          console.log("Temporal candidates:", res.results);
          setTemporalCandidates(res.results ?? []);
        }
        return;
      }
      if (searchType === "trake") {
        // Cùng lý do như temporal ở trên. TRAKE tốn hơn 1 chút mỗi video
        // (DP O(N×F²) thay vì bidirectional expansion) nhưng F~vài trăm
        // frame/video, N<=5 nên vẫn rất nhanh — 20 vẫn an toàn.
        const res = await videoSearchApi.trakeSearchText(queryText, {
          topVideos: 20,
        });
        if (res.error) {
          console.error("TRAKE search text error:", res.error);
          setTrakeCandidates([]);
        } else {
          console.log("TRAKE candidates:", res.results);
          setTrakeCandidates(res.results ?? []);
        }
        return;
      }

      if (searchType === "multimodal") {
        const weights = SEARCH_EMPHASIS_WEIGHTS[searchEmphasis];
        const startedAt = performance.now();

        const res = await videoSearchApi.multimodalSearch(queryText, {
          limit: Number(resultLimit),
          visualTopM: topM,
          visualWeight: weights.visualWeight,
          asrWeight: weights.asrWeight,
        });

        setMultimodalResults(res.results);
        setMultimodalTime((performance.now() - startedAt) / 1000);

        console.log("Multimodal results:", res);
        return;
      }
      if (searchType === "ocr") {
        // Pure lexical route - no model call, no blending with the visual
        // route. Results share the SearchResult shape, so the existing grid
        // renders them as-is.
        const res = await videoSearchApi.ocrSearch(
          queryText,
          Number(resultLimit),
          ocrStripDiacritics
        );
        useSearchStore.getState().setTotalTime(res.processing_time);
        useSearchStore.getState().setResults(res.results);
        useSearchStore.getState().setMaxDistance(res.max_distance);
        setOcrCounts({
          phrase: res.phrase_matches,
          allWords: res.all_word_matches,
          anyWord: res.any_word_matches,
          searched: res.searched_frames,
        });
        return;
      }

      const response =
        searchType === "single"
          ? await videoSearchApi.singleSearch(
              queryText,
              singleModel,
              Number(resultLimit),
              topM,
              useRerank
            )
          : await videoSearchApi.ensembleSearch(
              queryText,
              Number(resultLimit),
              topM,
              useRerank
            );
      console.log(response);
      useSearchStore.getState().setTotalTime(response.processing_time);
      useSearchStore.getState().setResults(response.results);
      useSearchStore.getState().setMaxDistance(response.max_distance);
      // Backend không còn demo_mode (đã bỏ chế độ sinh dữ liệu giả); thay bằng
      // has_image để biết bộ ảnh trên máy đã phủ hết kết quả chưa.
      const missing = response.results.filter(
        (r) => r.has_image === false
      ).length;
      if (missing > 0) {
        console.warn(
          `[frames] ${missing}/${response.results.length} kết quả chưa có ảnh ` +
            `trên đĩa → hiển thị placeholder. Tải thêm ZIP frame để đầy đủ.`
        );
      }
    } catch (err) {
      console.error("Search failed:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const { hasQueried, setHasQueried } = useIsQueryStore();
  useEffect(() => {
    if (!hasQueried && queryText && isLoading) {
      setHasQueried(true);
    }
  }, [results, hasQueried, setHasQueried, queryText, isLoading]);

  // Nhãn E1…EN là chính các đoạn người dùng gõ, tách đúng luật của
  // preprocess.py:_split_query_text.
  const queryParts = splitQueryParts(queryText);

  const isVisualSearch =
    searchType === "ensemble" || searchType === "single" || searchType === "ocr";

  const [groupedResult, setgroupedResult] = useState<
    Record<string, SearchResult[]>
  >({});
  useEffect(() => {
    if (sortFrameBy == "video_id" && results) {
      const grouped = formatResultByVideoID(results);
      setgroupedResult(grouped);
      console.log(grouped);
      console.log(Object.keys(grouped).length);
    }
  }, [sortFrameBy, results]);

  return (
    <div className="relative min-h-screen bg-proto-canvas p-2">
      {/* Header */}
      <div className="w-full relative">
        <Header />
        {hasQueried && (
          <div className="absolute top-0 left-1/2 transform -translate-x-1/2 z-999">
            <ResultInfoAndSort
              numberOfResults={
                searchType === "temporal"
                  ? temporalCandidates.length
                  : searchType === "trake"
                  ? trakeCandidates.length
                  : searchType === "multimodal"
                  ? multimodalResults.length
                  : results.length
              }
              sortBy={sortFrameBy}
              totalTime={
                searchType === "multimodal" ? multimodalTime : totalTime
              }
              onSortChange={(option) => setSortFrameBy(option)}
              unit={
                searchType === "temporal" ||
                searchType === "trake" ||
                searchType === "multimodal"
                  ? "videos"
                  : "frames"
              }
              videoSummary={
                searchType === "multimodal"
                  ? "xếp theo bằng chứng hình ảnh + lời nói"
                  : undefined
              }
              queryParts={queryParts.length}
            />
          </div>
        )}
        {hasQueried && searchType === "ocr" && ocrCounts && (
          <OcrCountBanner counts={ocrCounts} shown={results.length} />
        )}
        <div
          className={`absolute top-0 right-0 z-999 max-w-[320px] rounded-md border px-3 py-2 text-xs font-bold shadow-sm ${healthClassName}`}
          title={backendHealth.detail}
        >
          <span>{backendHealth.message}</span>
          {backendHealth.detail && (
            <span className="ml-2 font-normal">{backendHealth.detail}</span>
          )}
        </div>
      </div>

      {/* Đề bài của task đang mở — nguyên văn, chỉ đọc, không bao giờ dịch.
          Pin lên đỉnh khung nhìn: cuộn qua cả trăm kết quả vẫn còn thấy đề. */}
      {activeTask && <TaskBrief task={activeTask} />}

      {/* Project Description (only when no results) */}
      {!hasQueried && !activeTask && (
        <div className="max-w-4xl mx-auto mt-10">
          <ProjectDescription />
        </div>
      )}
      {/* Gated on the video rather than on `result`: a TRAKE event opens the
          same popup without there being a SearchResult behind it. */}
      {showPopup && videoUrl !== "" && (
        <VideoPopup
          activeTask={activeTask}
          onBasketChanged={onBasketChanged}
          videoId={videoUrl}
          frameId={frameId}
          startAt={startTime}
          onClose={() => {
            setShowPopup(false);
            setTrakeSlot(null);
          }}
          setStartAt={setStartTime}
          trakeSlot={
            trakeSlot && {
              index: trakeSlot.index,
              label: trakeSlot.label,
              total: trakeSlot.total,
              onCommit: (frame) => {
                swapTrakeEvent(trakeSlot.cardKey, trakeSlot.index, {
                  name: `${videoUrl} · frame ${frame}`,
                  url: "",
                  frame_idx: frame,
                  timestamp: "",
                  byHand: true,
                });
                setShowPopup(false);
                setTrakeSlot(null);
              },
            }
          }
        />
      )}

      {/* Temporal Search Panel — Alg.4, mở khi bấm "⏱" trên 1 kết quả search */}
      {showTemporalPanel && temporalAnchor && (
        <TemporalSearchPanel
          anchorName={temporalAnchor.name}
          anchorUrl={temporalAnchor.url}
          onClose={() => setShowTemporalPanel(false)}
        />
      )}

      {isVisualSearch && (isLoading || (hasQueried && sortFrameBy == "accuracy")) && (
        <div className="max-w-[98%] mx-auto grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-6 mb-[200px]">
          <FrameDisplay
            results={results}
            maxDistance={maxDistance}
            isLoading={isLoading}
            onUseAsAnchor={handleUseAsAnchor}
            onAddToBasket={
              activeTask && activeTask.type !== "trake"
                ? handleAddToBasket
                : undefined
            }
            onClick={(result) => {
              setframeId(frameIdFromName(result.name));
              setVideoUrl(videoIdFromFrame(result.frame));
              setStartTime(startMsFromResult(result));
              setShowPopup(true);
            }}
          />
        </div>
      )}

      {isVisualSearch && (isLoading || (hasQueried && sortFrameBy == "video_id")) && (
        <div className="mb-[200px]">
          {Object.entries(groupedResult).map(([key, items]) => (
            <div
              key={key}
              className="border border-proto-line bg-white m-[15px] mb-[30px] p-[10px] py-[20px] rounded-[8px] flex flex-col"
            >
              <div className="pl-[14px] mb-[12px] flex text-lg">
                <span className="font-bold">Video ID :</span>
                <span className="ml-[10px]">{key}</span>
              </div>
              <div className="max-w-[98%] mx-auto grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-6">
                <FrameDisplay
                  results={items}
                  maxDistance={maxDistance}
                  isLoading={isLoading}
                  onUseAsAnchor={handleUseAsAnchor}
                  onAddToBasket={
                    activeTask && activeTask.type !== "trake"
                      ? handleAddToBasket
                      : undefined
                  }
                  onClick={(result) => {
                    setframeId(frameIdFromName(result.name));
                    setVideoUrl(videoIdFromFrame(result.frame));
                    setStartTime(startMsFromResult(result));
                    setShowPopup(true);
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Temporal Search Results — Alg.4 text-query path */}
      {searchType === "temporal" && (isLoading || hasQueried) && (
        <div className="max-w-[98%] mx-auto mb-[200px] px-4">
          {isLoading ? (
            <p className="text-sm text-proto-muted animate-pulse">
              Đang tìm kiếm…
            </p>
          ) : temporalCandidates.length === 0 ? (
            <p className="text-sm text-proto-muted">Không tìm thấy kết quả.</p>
          ) : (
            <TemporalCandidates
              results={temporalCandidates}
              parts={queryParts}
              fpsOf={(video) =>
                (KeyframeFPS as Record<string, number>)[video ?? ""] ?? 0
              }
            />
          )}
        </div>
      )}

      {/* TRAKE Search Results */}
      {searchType === "trake" && (isLoading || hasQueried) && (
        <div className="max-w-[98%] mx-auto mb-[200px] px-4">
          {isLoading ? (
            <p className="text-sm text-proto-muted animate-pulse">
              Đang tìm kiếm…
            </p>
          ) : trakeCandidates.length === 0 ? (
            <p className="text-sm text-proto-muted">Không tìm thấy kết quả.</p>
          ) : (
            <TrakeCandidates
              results={trakeCandidates}
              parts={queryParts}
              swaps={trakeSwaps}
              onSwap={swapTrakeEvent}
              onOpenEvent={openTrakeEvent}
              onCommit={activeTask?.type === "trake" ? commitTrakeRow : undefined}
            />
          )}
        </div>
      )}

      {/* Visual + Speech Results */}
      {searchType === "multimodal" && (isLoading || hasQueried) && (
        <div className="max-w-[98%] mx-auto mb-[200px] px-4">
          {isLoading ? (
            <p className="text-sm text-proto-muted animate-pulse">
              Đang tìm kiếm…
            </p>
          ) : multimodalResults.length === 0 ? (
            <p className="text-sm text-proto-muted">
              Không tìm thấy kết quả.
            </p>
          ) : (
            <MultimodalResults
              results={multimodalResults}
              onOpenFrame={(result) => {
                setframeId(frameIdFromName(result.name));
                setVideoUrl(videoIdFromFrame(result.frame));
                setStartTime(startMsFromResult(result));
                setShowPopup(true);
              }}
              onUseAsAnchor={handleUseAsAnchor}
              onAddToBasket={
                activeTask && activeTask.type !== "trake"
                  ? handleAddToBasket
                  : undefined
              }
            />
          )}
        </div>
      )}

      {/* Sticky Query Input */}
      <div className="w-full max-w-[900px] fixed bottom-6 left-1/2 transform -translate-x-1/2 bg-white border border-proto-line shadow-xl rounded-xl z-40">
        <QueryInput
          doSearch={doSearch}
          disabled={isSearchDisabled || isLoading}
        />
      </div>
    </div>
  );
}

export default App;
