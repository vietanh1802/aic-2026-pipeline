import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import FrameDisplay from "./components/FrameDisplay";
import GotoFrame from "./components/GotoFrame";
import Header from "./components/Header";
import ProjectDescription from "./components/ProjectDescription";
import QueryInput from "./components/QueryInput";
import ResultInfoAndSort, {
  type SortType,
} from "./components/ResultInfoAndSort";
import TaskBrief from "./components/TaskBrief";
import OcrCountBanner from "./components/OcrCountBanner";
import { useIsQueryStore, useSearchStore } from "./store/useSearchStore";
import { useQueryStore } from "./store/queryStore";
import { usePopupStore } from "./store/popupStore";
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
import { filterByFocus } from "./helpers/focusFilter";
import { addAnswer } from "./api/answers";
import type { BoardTask } from "./api/board";
import type {
  HealthResponse,
  SearchResult,
  TemporalCandidateResult,
  TrakeCandidateResult,
} from "./types/api";
import KeyframeFPS from "./mapping/fps_map.json";

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
  rowsPerQuery = 100,
  onBasketChanged,
}: {
  /** The task claimed on the board, if any. Read-only context for the search. */
  activeTask?: BoardTask | null;
  /** From the round the task belongs to; threaded down to the popup's answer panel. */
  rowsPerQuery?: number;
  onBasketChanged?: () => void;
} = {}) {
  const results = useSearchStore((state) => state.results);
  const maxDistance = useSearchStore((state) => state.maxDistance);
  const totalTime = useSearchStore((state) => state.totalTime);
  const focusVideos = useSearchStore((state) => state.focusVideos);
  const toggleFocusVideo = useSearchStore((state) => state.toggleFocusVideo);
  const clearFocus = useSearchStore((state) => state.clearFocus);
  const resultLimit = useQueryStore((state) => state.resultLimit);
  const topM = useQueryStore((state) => state.topM);
  const useRerank = useQueryStore((state) => state.useRerank);
  const ocrStripDiacritics = useQueryStore((state) => state.ocrStripDiacritics);
  const searchType = useQueryStore((state) => state.searchType);
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

  // The OCR route's three counts. Kept out of useSearchStore because that
  // store is shared with the visual route, which has no notion of "how many
  // images contain this text".
  const [ocrCounts, setOcrCounts] = useState<{
    phrase: number;
    allWords: number;
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

  // A popup asked for from outside App — a basket row, the goto-frame box.
  // The paths already inside App set this state directly and do not go
  // through the store.
  const popupRequest = usePopupStore((state) => state.request);
  const clearPopupRequest = usePopupStore((state) => state.clear);

  useEffect(() => {
    if (!popupRequest) {
      return;
    }
    const { videoId, frameIdx } = popupRequest;
    // No keyframe name to take an id from, so the header shows the frame
    // number itself — the same thing a hand-pinned TRAKE moment shows.
    setframeId(String(frameIdx));
    setVideoUrl(videoId);
    setStartTime(startMsAt(videoId, frameIdx));
    setTrakeSlot(null);
    setShowPopup(true);
    clearPopupRequest();
  }, [popupRequest, clearPopupRequest]);

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

  const resetTrakeEvent = (cardKey: string, index: number) => {
    setTrakeSwaps((prev) => {
      const card = prev[cardKey];
      if (!card || !(index in card)) {
        return prev;
      }
      const next = { ...card };
      delete next[index];
      return { ...prev, [cardKey]: next };
    });
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
          setTrakeCandidates(res.results ?? []);
        }
        return;
      }

      if (searchType === "ocr") {
        // Pure lexical route - no model call, no blending with the visual
        // route. Results share the SearchResult shape, so they go straight
        // into useSearchStore and the existing grid renders them as-is.
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

  // Everything below renders `shownResults`, never `results`, so the grid, the
  // grouping and the count all agree about what is on screen.
  //
  // Memoised because it feeds the grouping effect's dependency array. Unmemoised,
  // filterByFocus hands back a fresh array on every render whenever a focus is
  // active, so the effect re-ran and re-set groupedResult forever.
  const shownResults = useMemo(
    () => filterByFocus(results, focusVideos),
    [results, focusVideos]
  );

  // Show Top can be 500 (2000 on the OCR route) and that is deliberate — the
  // frame you want may rank 300th, and you cannot pick what you cannot see.
  // What is NOT affordable is painting all of them at once: each keyframe is a
  // full 1280x720 JPEG, ~145 KB on the wire and ~3.5 MB decoded, so 345 tiles
  // is roughly 49 MB of download and a gigabyte of image memory. So the search
  // keeps its reach and the grid pages: a screenful at a time, more as you get
  // to the bottom.
  const PAGE_SIZE = 100;
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const moreRef = useRef<HTMLDivElement | null>(null);

  // A new result set, or a change of filter, starts the window over.
  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [shownResults]);

  const visibleResults = useMemo(
    () => shownResults.slice(0, visibleCount),
    [shownResults, visibleCount]
  );
  const hasMore = visibleCount < shownResults.length;

  // Grow when the sentinel scrolls into view. The button below it does the same
  // thing on click, so a browser that never fires this is still fully usable.
  useEffect(() => {
    const node = moreRef.current;
    if (!node || !hasMore) {
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setVisibleCount((count) => count + PAGE_SIZE);
      }
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, visibleCount]);

  // Nhãn E1…EN là chính các đoạn người dùng gõ, tách đúng luật của
  // preprocess.py:_split_query_text.
  const queryParts = splitQueryParts(queryText);

  const [groupedResult, setgroupedResult] = useState<
    Record<string, SearchResult[]>
  >({});
  useEffect(() => {
    if (sortFrameBy == "video_id" && shownResults) {
      setgroupedResult(formatResultByVideoID(visibleResults));
    }
  }, [sortFrameBy, visibleResults]);

  return (
    <div className="relative min-h-screen bg-proto-canvas p-2">
      {/* Header — one flex row, nothing stacked.
          The counter, the goto-frame box and the API chip used to be absolutely
          positioned on top of <Header/>. Header's `my-9` collapsed through this
          wrapper, so `top-0` landed on Header's own content instead of above it,
          and the right-hand pair sat straight over "VQF — Video Query Finder"
          and the build badge. Laying them out rather than stacking them makes the
          collision impossible, and `flex-wrap` drops the right-hand cluster onto
          its own line on a narrow window instead of letting it ride over anything. */}
      <div className="w-full flex flex-wrap items-center gap-x-4 gap-y-2 pr-2">
        <div className="flex-1 min-w-[260px]">
          <Header />
        </div>
        <div className="flex items-start gap-2 shrink-0">
          <GotoFrame />
          <div
            className={`max-w-[320px] rounded-md border px-3 py-2 text-xs font-bold shadow-sm ${healthClassName}`}
            title={backendHealth.detail}
          >
            <span>{backendHealth.message}</span>
            {backendHealth.detail && (
              <span className="ml-2 font-normal">{backendHealth.detail}</span>
            )}
          </div>
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
          rowsPerQuery={rowsPerQuery}
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

      {focusVideos.length > 0 && (
        <div className="max-w-[98%] mx-auto mb-2 flex flex-wrap items-center gap-1.5 font-baloo">
          <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
            Đang soi
          </span>
          {focusVideos.map((video) => (
            <span
              key={video}
              className="flex items-center gap-1 rounded-full border border-proto-primary bg-proto-primary/10 pl-2.5 text-[12px] font-mono text-proto-primary-active"
            >
              {video}
              <button
                type="button"
                title={`Bỏ lọc ${video}`}
                onClick={() => toggleFocusVideo(video)}
                className="flex h-10 w-10 items-center justify-center font-bold"
              >
                ×
              </button>
            </span>
          ))}
          <button
            type="button"
            onClick={clearFocus}
            className="text-[12px] px-2.5 py-1 rounded-[7px] border border-proto-line text-proto-muted"
          >
            Xoá lọc
          </button>
        </div>
      )}

      {/* ResultInfoAndSort describes the results, so it sits directly above
          the results grid it describes rather than up in the header row —
          it used to crowd the logo/version badge there and wrap onto a
          second line. Condition is `hasQueried` alone (not sortFrameBy or
          searchType) so it shows for every search type, exactly as before. */}
      {hasQueried && searchType === "ocr" && ocrCounts && (
        <div className="max-w-[98%] mx-auto mb-2">
          <OcrCountBanner counts={ocrCounts} shown={results.length} />
        </div>
      )}

      {hasQueried && (
        <div className="max-w-[98%] mx-auto mb-2">
          <ResultInfoAndSort
            numberOfResults={
              searchType === "temporal"
                ? temporalCandidates.length
                : searchType === "trake"
                ? trakeCandidates.length
                : results.length
            }
            sortBy={sortFrameBy}
            totalTime={totalTime}
            onSortChange={(option) => setSortFrameBy(option)}
            unit={
              searchType === "temporal" || searchType === "trake"
                ? "videos"
                : "frames"
            }
            queryParts={queryParts.length}
            filtered={
              focusVideos.length > 0
                ? { shown: shownResults.length, total: results.length }
                : undefined
            }
          />
        </div>
      )}

      {(isLoading || (hasQueried && sortFrameBy == "accuracy")) && (
        <div className="max-w-[98%] mx-auto grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-6">
          <FrameDisplay
            results={visibleResults}
            maxDistance={maxDistance}
            isLoading={isLoading}
            onUseAsAnchor={handleUseAsAnchor}
            onAddToBasket={
              activeTask && activeTask.type !== "trake"
                ? handleAddToBasket
                : undefined
            }
            onToggleFocus={toggleFocusVideo}
            focusVideos={focusVideos}
            onClick={(result) => {
              setframeId(frameIdFromName(result.name));
              setVideoUrl(videoIdFromFrame(result.frame));
              setStartTime(startMsFromResult(result));
              setShowPopup(true);
            }}
          />
        </div>
      )}

      {/* Paging sentinel. Scrolling here loads the next page; the button does
          the same on click, so this still works if IntersectionObserver never
          fires. Both views read `visibleResults`, so the grouped list is
          bounded too. */}
      {hasQueried && !isLoading && hasMore && (
        <div
          ref={moreRef}
          className="max-w-[98%] mx-auto mt-6 flex items-center justify-center"
        >
          <button
            type="button"
            onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}
            className="text-[12.5px] px-4 py-2 rounded-[8px] border border-proto-line bg-white text-proto-body"
          >
            Xem thêm — đang hiện {visibleResults.length}/{shownResults.length}
          </button>
        </div>
      )}
      <div className="mb-[280px]" />

      {(isLoading || (hasQueried && sortFrameBy == "video_id")) && (
        <div className="mb-[280px]">
          {Object.entries(groupedResult).map(([key, items]) => (
            <div
              key={key}
              className="border border-proto-line bg-white m-[15px] mb-[30px] p-[10px] py-[20px] rounded-[8px] flex flex-col"
            >
              <div className="pl-[14px] mb-[12px] flex items-center text-lg">
                <span className="font-bold">Video ID :</span>
                <span className="ml-[10px]">{key}</span>
                <button
                  type="button"
                  title={
                    focusVideos.includes(key)
                      ? "Bỏ lọc video này"
                      : "Chỉ xem video này"
                  }
                  onClick={() => toggleFocusVideo(key)}
                  className={`ml-2 flex h-10 w-10 items-center justify-center rounded-[6px] border-2 ${
                    focusVideos.includes(key)
                      ? "bg-proto-primary border-proto-primary"
                      : "bg-[#EFEFEF] border-[#E3E3E3]"
                  }`}
                >
                  🎯
                </button>
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
                  onToggleFocus={toggleFocusVideo}
                  focusVideos={focusVideos}
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
      {(isLoading || (hasQueried && searchType === "temporal")) && (
        <div className="max-w-[98%] mx-auto mb-[280px] px-4">
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
      {(isLoading || (hasQueried && searchType === "trake")) && (
        <div className="max-w-[98%] mx-auto mb-[280px] px-4">
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
              onResetSlot={resetTrakeEvent}
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