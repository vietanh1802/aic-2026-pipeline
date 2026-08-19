import { useEffect, useState } from "react";
import "./App.css";
import FrameDisplay from "./components/FrameDisplay";
import Header from "./components/Header";
import ProjectDescription from "./components/ProjectDescription";
import QueryInput from "./components/QueryInput";
import ResultInfoAndSort, {
  type SortType,
} from "./components/ResultInfoAndSort";
import { useIsQueryStore, useSearchStore } from "./store/useSearchStore";
import { useQueryStore } from "./store/queryStore";
import VideoPopup from "./components/VideoPopUp";
import TemporalSearchPanel from "./components/TemporalSearchPanel";
import { videoSearchApi } from "./types/api";
import { formatResultByVideoID } from "./helpers/formatResult.helper";
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
type VideoId = keyof typeof KeyframeFPS;

function videoIdFromFrame(frame: string): string {
  return frame.match(/^([LK]\d{2}_V\d{3})/)?.[1] ?? "";
}

function frameIdFromName(name: string): string {
  const baseName = name.replace(/\.[^/.]+$/, "");
  return baseName.split("-").slice(1).join("-");
}

function frameIndexFromResult(result: SearchResult): number {
  if (typeof result.frame_idx === "number") {
    return result.frame_idx;
  }
  return Number(result.frame.match(/-(\d+)\.jpg$/)?.[1] ?? 0);
}

function startMsFromResult(result: SearchResult): number {
  const videoId = videoIdFromFrame(result.frame) as VideoId;
  const fps = KeyframeFPS[videoId] as number | undefined;
  if (!fps) {
    return 0;
  }
  return (frameIndexFromResult(result) / fps) * 1000;
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

function App() {
  const results = useSearchStore((state) => state.results);
  const maxDistance = useSearchStore((state) => state.maxDistance);
  const totalTime = useSearchStore((state) => state.totalTime);
  const resultLimit = useQueryStore((state) => state.resultLimit);
  const topM = useQueryStore((state) => state.topM);
  const useRerank = useQueryStore((state) => state.useRerank);
  const searchType = useQueryStore((state) => state.searchType);
  const singleModel = useQueryStore((state) => state.singleModel);
  const [showPopup, setShowPopup] = useState<boolean>(false);
  const [videoUrl, setVideoUrl] = useState<string>("");
  const [startTime, setStartTime] = useState<number>(0);
  const [frameId, setframeId] = useState<string>("");

  const [sortFrameBy, setSortFrameBy] = useState<SortType>("accuracy");
  const queryText = useQueryStore((state) => state.queryText);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const [result, setResult] = useState<SearchResult | null>(null);
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
    checking: "border-gray-300 bg-white text-gray-700",
    starting: "border-amber-300 bg-amber-50 text-amber-800",
    ready: "border-emerald-300 bg-emerald-50 text-emerald-800",
    offline: "border-red-300 bg-red-50 text-red-800",
    failed: "border-red-300 bg-red-50 text-red-800",
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

  const doSearch = async () => {
    if (isSearchDisabled) {
      console.warn(`[health] Search blocked: ${backendHealth.message}`);
      return;
    }
    setIsLoading(true);
    try {
      if (searchType === "temporal") {
        const res = await videoSearchApi.temporalSearchText(queryText);
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
        const res = await videoSearchApi.trakeSearchText(queryText);
        if (res.error) {
          console.error("TRAKE search text error:", res.error);
          setTrakeCandidates([]);
        } else {
          console.log("TRAKE candidates:", res.results);
          setTrakeCandidates(res.results ?? []);
        }
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
    <div className="relative min-h-screen bg-gray-50 p-2">
      {/* Header */}
      <div className="w-full relative">
        <Header />
        {hasQueried && (
          <div className="absolute top-0 left-1/2 transform -translate-x-1/2 z-999">
            <ResultInfoAndSort
              numberOfResults={results.length}
              sortBy={sortFrameBy}
              totalTime={totalTime}
              onSortChange={(option) => setSortFrameBy(option)}
            />
          </div>
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

      {/* Project Description (only when no results) */}
      {!hasQueried && (
        <div className="max-w-4xl mx-auto mt-10">
          <ProjectDescription />
        </div>
      )}
      {showPopup && result !== null && (
        <VideoPopup
          videoId={videoUrl}
          frameId={frameId}
          startAt={startTime}
          onClose={() => setShowPopup(false)}
          setStartAt={setStartTime}
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

      {(isLoading || (hasQueried && sortFrameBy == "accuracy")) && (
        <div className="max-w-[98%] mx-auto grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-6 mb-[200px]">
          <FrameDisplay
            results={results}
            maxDistance={maxDistance}
            isLoading={isLoading}
            onUseAsAnchor={handleUseAsAnchor}
            onClick={(result) => {
              setframeId(frameIdFromName(result.name));
              setVideoUrl(videoIdFromFrame(result.frame));
              setStartTime(startMsFromResult(result));
              setShowPopup(true);
              setResult(result);
            }}
          />
        </div>
      )}

      {(isLoading || (hasQueried && sortFrameBy == "video_id")) && (
        <div className="mb-[200px]">
          {Object.entries(groupedResult).map(([key, items]) => (
            <div
              key={key}
              className="border-5 border-gray-300  m-[15px] mb-[30px] p-[10px] py-[20px] rounded-[8px] flex flex-col"
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
                  onClick={(result) => {
                    setframeId(frameIdFromName(result.name));
                    setVideoUrl(videoIdFromFrame(result.frame));
                    setStartTime(startMsFromResult(result));
                    setShowPopup(true);
                    setResult(result);
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Sticky Query Input */}
      <div className="w-full max-w-[900px] fixed bottom-6 left-1/2 transform -translate-x-1/2 bg-white border border-gray-300 shadow-xl rounded-xl z-40">
        <QueryInput
          doSearch={doSearch}
          disabled={isSearchDisabled || isLoading}
        />
      </div>
    </div>
  );
}

export default App;