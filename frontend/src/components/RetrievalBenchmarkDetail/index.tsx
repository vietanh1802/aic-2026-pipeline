import { useEffect, useState } from "react";

import type {
  FrameInterval,
  FrameResult,
  QueryResultDetail,
} from "../../api/retrievalBenchmark";
import { R_AT_CUTS } from "../../api/retrievalBenchmark";
import { videoUrlAt } from "../../helpers/videoSource";
import KeyframeFPS from "../../mapping/fps_map.json";
import KeyframeImg from "../KeyframeImg";

const FPS = KeyframeFPS as Record<string, number | undefined>;

function formatSeconds(ms: number | null): string {
  if (ms === null) return "—";
  return `${(ms / 1000).toFixed(2)}s`;
}

function frameVideoId(frame: FrameResult, fallback: string): string {
  return String(frame.video ?? frame.video_id ?? fallback);
}

function frameNumber(frame: FrameResult): number | null {
  return typeof frame.frame_idx === "number" ? frame.frame_idx : null;
}

function inAnyInterval(
  frameIdx: number | null,
  intervals: FrameInterval[] | null
): boolean {
  if (frameIdx === null || !intervals) return false;
  return intervals.some((iv) => frameIdx >= iv.start && frameIdx <= iv.end);
}

function intervalListLabel(intervals: FrameInterval[] | null): string {
  if (!intervals || intervals.length === 0) return "no interval (TRAKE — video ranking only)";
  return intervals.map((iv) => `${iv.start}–${iv.end}`).join(", ");
}

export default function RetrievalBenchmarkDetail({
  result,
  translationPolicyLabel,
}: {
  result: QueryResultDetail | null;
  translationPolicyLabel: string;
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
          Select a query to inspect its translation, interval match, ranked
          videos, evidence frames, and timing.
        </div>
      </div>
    );
  }

  const isTrake = result.task_type === "TRAKE";
  const rankedVideos = (result.ranked_videos ?? []).slice(0, 10);

  const openFrame = (frame: FrameResult, fallbackVideoId: string) => {
    const videoId = frameVideoId(frame, fallbackVideoId);
    const number = frameNumber(frame);
    if (!videoId || number === null) return;

    const fps = FPS[videoId];
    const seconds = fps && fps > 0 ? number / fps : 0;
    setPreview({ videoId, frame: number, seconds, src: videoUrlAt(videoId, seconds) });
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

        {result.reference_notes && (
          <div className="mb-4 rounded-[8px] border border-[#d4a017]/40 bg-[#d4a017]/10 px-3 py-2 text-[12px] text-[#7a5c0c]">
            <b className="uppercase text-[10px] tracking-wide">Reference note</b>
            <div className="mt-1 leading-snug">{result.reference_notes}</div>
          </div>
        )}

        <section>
          <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-1">
            Original query
          </div>
          <p className="text-[13px] text-proto-body leading-[1.5] m-0">{result.query_vi}</p>
        </section>

        <section className="mt-4">
          <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-1">
            Translation
          </div>
          <p className="text-[13px] text-proto-body leading-[1.5] m-0">
            {result.query_en ?? "Not available"}
          </p>
          <div className="text-[10.5px] text-proto-muted mt-1 font-mono">{result.translator}</div>
          <div className="text-[10.5px] text-proto-muted mt-0.5">Policy · {translationPolicyLabel}</div>
        </section>

        <section className="mt-4 grid grid-cols-2 gap-3">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mb-1">
              Reference
            </div>
            <div className="font-mono text-[12.5px] text-proto-ink">{result.reference_video}</div>
            <div className="text-[11px] text-proto-muted mt-0.5">
              frames {intervalListLabel(result.reference_intervals)}
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
                result.reference_video_rank === null ? "text-[#c64545]" : "text-proto-muted"
              }`}
            >
              {result.status !== "completed"
                ? result.status
                : result.reference_video_rank === null
                  ? "reference video not retrieved"
                  : `video rank #${result.reference_video_rank}`}
            </div>
            {!isTrake && (
              <div
                className={`text-[11px] mt-0.5 ${
                  result.interval_hit ? "text-[#3d7a4d]" : "text-proto-muted"
                }`}
              >
                {result.interval_rank === null
                  ? "no frame inside a valid interval"
                  : `interval hit at rank #${result.interval_rank}` +
                    (result.matched_interval_index !== null
                      ? ` (interval ${result.matched_interval_index + 1})`
                      : "")}
              </div>
            )}
          </div>
        </section>

        {!isTrake && (
          <section className="mt-4 border border-proto-line rounded-[8px] px-3 py-2.5">
            <div className="flex items-center justify-between">
              <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
                R-Score
              </div>
              <div className="text-[12px]">
                Final <b className="font-mono text-proto-ink">{result.final_score?.toFixed(2) ?? "—"}</b>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11.5px] font-mono">
              {R_AT_CUTS.map((cut) => {
                const hit =
                  result.interval_rank !== null && result.interval_rank <= cut;
                return (
                  <span key={cut} className={hit ? "text-[#3d7a4d]" : "text-proto-muted"}>
                    R@{cut} {hit ? "✓" : "×"}
                  </span>
                );
              })}
            </div>
          </section>
        )}

        {result.task_type === "QA" && (
          <section className="mt-4 border border-proto-line rounded-[8px] px-3 py-2.5">
            <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
              Reference answer · not scored
            </div>
            <div className="mt-1 text-[13px] font-mono text-proto-ink">
              {result.qa_answer ?? "—"}
            </div>
            <div className="mt-1 text-[11px] text-proto-muted">
              QA is scored on video + frame interval only; the answer text is never checked.
            </div>
          </section>
        )}

        {isTrake && result.trake_events && result.trake_events.length > 0 && (
          <section className="mt-4 border border-proto-line rounded-[8px] px-3 py-2.5">
            <div className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
              TRAKE events · not scored
            </div>
            <ol className="mt-1.5 mb-0 pl-4 space-y-1 text-[12px] text-proto-body">
              {result.trake_events.map((event) => (
                <li key={event.event_id}>
                  <span className="font-mono text-proto-muted">{event.event_id}</span>{" "}
                  {event.description_vi}
                  {event.reference_frame_idx !== null && (
                    <span className="font-mono text-proto-muted"> · #{event.reference_frame_idx}</span>
                  )}
                </li>
              ))}
            </ol>
            <div className="mt-1 text-[11px] text-proto-muted">
              Tier 0: only the target video ranking is scored for TRAKE.
            </div>
          </section>
        )}

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
                      isReference ? "border-proto-primary bg-proto-soft" : "border-proto-line"
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
                          const marked =
                            isReference && inAnyInterval(number, result.reference_intervals);
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
                                className={`w-full aspect-video object-cover rounded-[6px] bg-proto-dark ${
                                  marked ? "ring-2 ring-[#3d7a4d]" : ""
                                }`}
                              />
                              <div className="mt-0.5 text-[9.5px] font-mono text-proto-muted truncate">
                                {number !== null ? `#${number}` : frame.timestamp ?? "frame"}
                                {marked ? " · in interval" : ""}
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
