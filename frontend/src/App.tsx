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
import { videoSearchApi } from "./types/api";
import { formatResultByVideoID } from "./helpers/formatResult.helper";
import type { SearchResult } from "./types/api";

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

  // Alg.3 (ensemble) hoặc chạy 1 model đơn (Q4) — khớp đúng /ensemble-search
  // và /single-search hiện có trong main.py. Không còn text-search/faiss-
  // search/combined-search/ocr-search/filter-search — các endpoint đó đã bị
  // xóa khỏi backend (xem docstring main.py).
  const doSearch = async () => {
    setIsLoading(true);
    try {
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
      if (response.demo_mode) {
        console.warn(
          "[demo_mode] Backend chưa có beit3.index/clip.index thật — " +
            "kết quả là dữ liệu giả tất định theo query, chỉ để test UI."
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
      setgroupedResult(formatResultByVideoID(results));
      console.log(groupedResult);
      console.log(Object.keys(groupedResult).length);
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
      </div>

      {/* Project Description (only when no results) */}
      {!hasQueried && (
        <div className="max-w-4xl mx-auto mt-10">
          <ProjectDescription />
        </div>
      )}
      {showPopup && result !== null && (
        <VideoPopup
          src={`/${videoUrl}.mp4`}
          videoId={videoUrl}
          frameId={frameId}
          startAt={startTime}
          onClose={() => setShowPopup(false)}
          result={result}
          setStartAt={setStartTime}
        />
      )}

      {(isLoading || (hasQueried && sortFrameBy == "accuracy")) && (
        <div className="max-w-[98%] mx-auto grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-6 mb-[200px]">
          <FrameDisplay
            results={results}
            maxDistance={maxDistance}
            isLoading={isLoading}
            onClick={(result) => {
              const msMatch = result.frame.match(/-(\d+)\.jpg$/);
              const ms = msMatch ? parseInt(msMatch[1]) : 0;
              const baseName = result.name.replace(/\.[^/.]+$/, "");
              const frameId = baseName.split("-").slice(1).join("-");

              const videoIdMatch = result.frame.match(/^([LK]\d{2}_V\d{3})/);
              const videoId = videoIdMatch ? videoIdMatch[1] : "";
              setframeId(frameId);
              setVideoUrl(videoId);
              setStartTime(ms);
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
                  onClick={(result) => {
                    const msMatch = result.frame.match(/-(\d+)\.jpg$/);
                    const ms = msMatch ? parseInt(msMatch[1]) : 0;
                    const baseName = result.name.replace(/\.[^/.]+$/, "");
                    const frameId = baseName.split("-").slice(1).join("-");

                    const videoIdMatch =
                      result.frame.match(/^([LK]\d{2}_V\d{3})/);
                    const videoId = videoIdMatch ? videoIdMatch[1] : "";
                    setframeId(frameId);
                    setVideoUrl(videoId);
                    setStartTime(ms);
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
        <QueryInput doSearch={doSearch} />
      </div>
    </div>
  );
}

export default App;
