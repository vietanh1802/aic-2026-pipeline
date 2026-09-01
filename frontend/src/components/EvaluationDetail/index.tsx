import { useEffect, useState } from "react";

import type {
  EvaluationFrameResult,
  EvaluationResult,
} from "../../api/evaluation";
import { videoUrlAt } from "../../helpers/videoSource";
import KeyframeFPS from "../../mapping/fps_map.json";
import KeyframeImg from "../KeyframeImg";

const FPS = KeyframeFPS as Record<string, number | undefined>;

function formatSeconds(ms: number | null): string {
  if (ms === null) return "—";
  return `${(ms / 1000).toFixed(2)}s`;
}

function frameVideoId(
  frame: EvaluationFrameResult,
  fallbackVideoId: string
): string {
  return String(frame.video ?? frame.video_id ?? fallbackVideoId);
}

function frameNumber(frame: EvaluationFrameResult): number | null {
  return typeof frame.frame_idx === "number" ? frame.frame_idx : null;
}

export default function EvaluationDetail({
  result,
}: {
  result: EvaluationResult | null;
}) {
  const [preview, setPreview] = useState<{
    videoId: string;
    frame: number;
    seconds: number;
    src: string;
  } | null>(null);

  useEffect(() => {
    setPreview(null);
  }, [result?.id]);

  if (!result) {
    return (
      <div className="border border-proto-line rounded-[10px] bg-white overflow-hidden min-[1100px]:sticky min-[1100px]:top-4 self-start">
        <div className="px-4 py-2 bg-proto-soft text-[10px] font-bold uppercase tracking-wide text-proto-muted">
          Case detail
        </div>
        <div className="p-4 text-[12.5px] text-proto-muted leading-relaxed">
          Select a query to inspect its translation, ranking, evidence frames, and timing.
        </div>
      </div>
    );
  }

  const rankedVideos = (result.ranked_videos ?? []).slice(0, 10);

  const openFrame = (
    frame: EvaluationFrameResult,
    fallbackVideoId: string
  ) => {
    const videoId = frameVideoId(frame, fallbackVideoId);
    const number = frameNumber(frame);
    if (!videoId || number === null) return;

    const fps = FPS[videoId];
    const seconds = fps && fps > 0 ? number / fps : 0;
    setPreview({
      videoId,
      frame: number,
      seconds,
      src: videoUrlAt(videoId, seconds),
    });
  };

  return (
    <div className="border border-proto-line rounded-[10px] bg-white overflow-hidden min-[1100px]:sticky min-[1100px]:top-4 self-start">
      <div className="px-4 py-2 bg-proto-soft flex items-center gap-2">
        <b className="font-mono text-[12px] text-proto-ink">{result.query_key}</b>
        <span className="text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-proto-dark text-proto-canvas">
          {result.task_type}
        </span>
        <span className="ml-auto text-[10px] uppercase tracking-wide text-proto-muted">
          {result.status}
        </span>
      </div>

      <div className="p-4 max-h-[calc(100vh-120px)] overflow-y-auto">
        {result.error && (
          <div className="mb-4 rounded-[8px] border border-[#c64545]/25 bg-[#c64545]/5 px-3 py-2">
            <div className="text-[10px] font-bold uppercase tracking-wide text-[#c64545] mb-1">
              Error
            </div>
            <div className="text-[12px] font-mono text-[#c64545] break-words">
              {result.error}
            </div>
          </div>
        )}

        <section>
          <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-1">
            Original query
          </div>
          <p className="text-[13px] text-proto-body leading-[1.5] m-0">
            {result.query_vi}
          </p>
        </section>

        <section className="mt-4">
          <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-1">
            Translation
          </div>
          <p className="text-[13px] text-proto-body leading-[1.5] m-0">
            {result.query_en ?? "Not available"}
          </p>
          <div className="text-[10.5px] text-proto-muted mt-1 font-mono">
            {result.translator}
          </div>
        </section>

        <section className="mt-4 grid grid-cols-2 gap-3">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-1">
              Reference
            </div>
            <div className="font-mono text-[12.5px] text-proto-ink">
              {result.reference_video}
            </div>
            <div className="text-[11px] text-proto-muted mt-0.5">
              {result.reference_frame_idx !== null
                ? `frame ${result.reference_frame_idx}`
                : "reference frame not annotated"}
            </div>
          </div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-1">
              Result
            </div>
            <div className="font-mono text-[12.5px] text-proto-ink">
              {result.predicted_top1_video ?? "—"}
            </div>
            <div
              className={`text-[11px] mt-0.5 ${
                result.reference_video_rank === null
                  ? "text-[#c64545]"
                  : "text-proto-muted"
              }`}
            >
              {result.status !== "completed"
                ? result.status
                : result.reference_video_rank === null
                ? "reference not retrieved"
                : `reference rank #${result.reference_video_rank}`}
            </div>
          </div>
        </section>

        {preview && (
          <section className="mt-4 border border-proto-line rounded-[8px] overflow-hidden">
            <div className="px-3 py-1.5 bg-proto-soft flex items-center gap-2 text-[11px] font-mono text-proto-ink">
              {preview.videoId} · frame {preview.frame}
              <button
                type="button"
                className="ml-auto text-proto-muted underline"
                onClick={() => setPreview(null)}
              >
                Close
              </button>
            </div>
            <div className="p-2 bg-white">
              {preview.src ? (
                <video
                  key={preview.src}
                  src={preview.src}
                  controls
                  autoPlay
                  preload="metadata"
                  className="rounded-[7px] w-full bg-proto-dark"
                  onLoadedMetadata={(event) => {
                    event.currentTarget.currentTime = preview.seconds;
                  }}
                />
              ) : (
                <p className="text-[11.5px] text-proto-muted m-0">
                  Video playback is not configured in this frontend environment.
                </p>
              )}
            </div>
          </section>
        )}

        <section className="mt-4">
          <div className="flex items-center gap-2 mb-2">
            <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
              Ranked videos
            </div>
            <span className="text-[10.5px] text-proto-muted">
              top {Math.min(10, result.ranked_videos?.length ?? 0)}
            </span>
          </div>

          {rankedVideos.length === 0 ? (
            <p className="text-[11.5px] text-proto-muted m-0">
              No persisted ranked-video evidence for this query.
            </p>
          ) : (
            <div className="space-y-2.5">
              {rankedVideos.map((candidate) => {
                const isReference = candidate.video_id === result.reference_video;
                return (
                  <div
                    key={`${candidate.rank}-${candidate.video_id}`}
                    className={`rounded-[8px] border px-2.5 py-2 ${
                      isReference
                        ? "border-proto-primary bg-proto-soft"
                        : "border-proto-line"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-[12px] text-proto-ink w-6 text-right">
                        {candidate.rank}
                      </span>
                      <span className="font-mono text-[12px] text-proto-ink">
                        {candidate.video_id}
                      </span>
                      {isReference && (
                        <span className="text-[9.5px] font-bold uppercase tracking-wide text-proto-primary-active ml-auto">
                          Reference
                        </span>
                      )}
                    </div>

                    {candidate.frames.length > 0 && (
                      <div className="grid grid-cols-3 gap-1.5 mt-2">
                        {candidate.frames.map((frame, index) => {
                          const number = frameNumber(frame);
                          const canOpen = number !== null;
                          return (
                            <button
                              key={`${candidate.video_id}-${number ?? index}-${index}`}
                              type="button"
                              disabled={!canOpen}
                              onClick={() => openFrame(frame, candidate.video_id)}
                              className="text-left disabled:cursor-default"
                              title={
                                canOpen
                                  ? `Open ${candidate.video_id} at frame ${number}`
                                  : candidate.video_id
                              }
                            >
                              <KeyframeImg
                                src={frame.url}
                                alt={`${candidate.video_id} evidence frame`}
                                className="w-full aspect-video object-cover rounded-[6px] bg-proto-dark"
                              />
                              <div className="mt-0.5 text-[9.5px] font-mono text-proto-muted truncate">
                                {number !== null ? `#${number}` : frame.timestamp ?? "frame"}
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <section className="mt-4 pt-4 border-t border-proto-line">
          <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-2">
            Timing
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11.5px]">
            <span className="text-proto-muted">Translation</span>
            <span className="font-mono text-right text-proto-ink">
              {formatSeconds(result.translation_ms)}
            </span>
            <span className="text-proto-muted">Retrieval</span>
            <span className="font-mono text-right text-proto-ink">
              {formatSeconds(result.retrieval_ms)}
            </span>
            <span className="text-proto-muted">Aggregation</span>
            <span className="font-mono text-right text-proto-ink">
              {formatSeconds(result.aggregation_ms)}
            </span>
            <span className="text-proto-ink font-semibold">Total</span>
            <span className="font-mono text-right text-proto-ink font-bold">
              {formatSeconds(result.total_ms)}
            </span>
          </div>
        </section>
      </div>
    </div>
  );
}
