import { useState } from "react";

import KeyframeImg from "../KeyframeImg";
import type {
  MultimodalVideoResult,
  SearchResult,
} from "../../types/api";

function formatSeconds(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;

  if (hours > 0) {
    return `${hours.toString().padStart(2, "0")}:${minutes
      .toString()
      .padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }

  return `${minutes.toString().padStart(2, "0")}:${secs
    .toString()
    .padStart(2, "0")}`;
}

function MultimodalCard({
  result,
  onOpenFrame,
  onUseAsAnchor,
  onAddToBasket,
}: {
  result: MultimodalVideoResult;
  onOpenFrame?: (frame: SearchResult) => void;
  onUseAsAnchor?: (frame: SearchResult) => void;
  onAddToBasket?: (frame: SearchResult) => void;
}) {
  const [open, setOpen] = useState(false);

  const bestFrame = result.visual?.frames[0];
  const firstWindow = result.asr?.windows[0];

  return (
    <div
      className={`rounded-[10px] bg-white overflow-hidden border mb-3 ${
        result.rank === 1 ? "border-proto-primary" : "border-proto-line"
      }`}
    >
      <div className="flex items-center gap-2 px-3 py-2 bg-proto-soft border-b border-proto-line">
        <span
          className={`w-6 h-6 rounded-full text-[11px] font-extrabold flex items-center justify-center ${
            result.rank === 1
              ? "bg-proto-primary text-white"
              : "bg-proto-cream-strong text-proto-muted"
          }`}
        >
          {result.rank}
        </span>

        <span className="font-mono font-bold text-[13px] text-proto-ink">
          {result.video_id}
        </span>

        {result.visual && (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-proto-teal/20 text-[#2f6b60]">
            Visual #{result.visual.rank}
          </span>
        )}

        {result.asr && (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-proto-amber/25 text-[#8a5a15]">
            Speech #{result.asr.rank}
            {firstWindow &&
              ` · ${formatSeconds(firstWindow.start_s)}–${formatSeconds(
                firstWindow.end_s
              )}`}
          </span>
        )}

        <button
          type="button"
          className="ml-auto text-[11.5px] font-semibold text-proto-primary-active"
          onClick={() => setOpen((value) => !value)}
        >
          {open ? "Thu lại ▴" : "Xem bằng chứng ▾"}
        </button>
      </div>

      <div className="p-3">
        <div className="flex gap-4">
          {bestFrame ? (
            <div className="w-[220px] shrink-0">
              <button
                type="button"
                className="w-full text-left"
                onClick={() => onOpenFrame?.(bestFrame)}
              >
                <KeyframeImg
                  src={bestFrame.url}
                  alt={bestFrame.name}
                  className="w-full h-[132px] object-cover rounded-lg border border-proto-line"
                />
              </button>

              <div className="flex justify-between mt-1 text-[10px] text-proto-muted">
                <span className="font-mono truncate">{bestFrame.name}</span>
                <span>{bestFrame.timestamp ?? ""}</span>
              </div>

              <div className="flex gap-2 mt-2">
                {onOpenFrame && (
                  <button
                    type="button"
                    className="text-[10.5px] font-bold text-proto-primary-active"
                    onClick={() => onOpenFrame(bestFrame)}
                  >
                    Mở video
                  </button>
                )}

                {onUseAsAnchor && (
                  <button
                    type="button"
                    className="text-[10.5px] font-bold text-proto-primary-active"
                    onClick={() => onUseAsAnchor(bestFrame)}
                  >
                    ⏱ Temporal
                  </button>
                )}

                {onAddToBasket && (
                  <button
                    type="button"
                    className="text-[10.5px] font-bold text-proto-primary-active"
                    onClick={() => onAddToBasket(bestFrame)}
                  >
                    + Giỏ
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="w-[220px] h-[132px] shrink-0 rounded-lg bg-proto-dark border border-dashed border-neutral-600 flex items-center justify-center">
              <span className="text-xs text-neutral-400 text-center px-4">
                Không có visual frame hỗ trợ
              </span>
            </div>
          )}

          <div className="flex-1 min-w-0">
            {firstWindow ? (
              <>
                <div className="text-[10px] font-extrabold uppercase tracking-wide text-proto-muted mb-1">
                  Speech evidence
                </div>

                <div className="text-[11px] font-mono text-proto-primary-active mb-1">
                  {formatSeconds(firstWindow.start_s)}–
                  {formatSeconds(firstWindow.end_s)}
                </div>

                <p className="text-[12.5px] text-proto-body leading-relaxed line-clamp-4">
                  {firstWindow.transcript}
                </p>
              </>
            ) : (
              <p className="text-xs text-proto-muted">
                Không có transcript evidence.
              </p>
            )}
          </div>
        </div>

        {open && (
          <div className="mt-4 pt-3 border-t border-dashed border-proto-line">
            {result.visual && result.visual.frames.length > 0 && (
              <div className="mb-4">
                <div className="text-[10px] font-extrabold uppercase tracking-wide text-proto-muted mb-2">
                  Visual evidence
                </div>

                <div className="flex gap-2 overflow-x-auto">
                  {result.visual.frames.map((frame) => (
                    <button
                      key={frame.name}
                      type="button"
                      className="w-[130px] shrink-0 text-left"
                      onClick={() => onOpenFrame?.(frame)}
                    >
                      <KeyframeImg
                        src={frame.url}
                        alt={frame.name}
                        className="w-full h-[78px] object-cover rounded border border-proto-line"
                      />
                      <div className="text-[9.5px] text-proto-muted mt-1 truncate">
                        {frame.timestamp ?? frame.name}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {result.asr && result.asr.windows.length > 0 && (
              <div>
                <div className="text-[10px] font-extrabold uppercase tracking-wide text-proto-muted mb-2">
                  Speech evidence
                </div>

                <div className="flex flex-col gap-2">
                  {result.asr.windows.slice(0, 2).map((window) => (
                    <div
                      key={window.window_id}
                      className="rounded-[7px] bg-proto-soft border border-proto-line px-3 py-2"
                    >
                      <div className="font-mono text-[10.5px] font-bold text-proto-primary-active mb-1">
                        {formatSeconds(window.start_s)}–
                        {formatSeconds(window.end_s)}
                      </div>

                      <p className="text-[12px] text-proto-body leading-relaxed">
                        {window.transcript}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function MultimodalResults({
  results,
  onOpenFrame,
  onUseAsAnchor,
  onAddToBasket,
}: {
  results: MultimodalVideoResult[];
  onOpenFrame?: (frame: SearchResult) => void;
  onUseAsAnchor?: (frame: SearchResult) => void;
  onAddToBasket?: (frame: SearchResult) => void;
}) {
  return (
    <div>
      {results.map((result) => (
        <MultimodalCard
          key={result.video_id}
          result={result}
          onOpenFrame={onOpenFrame}
          onUseAsAnchor={onUseAsAnchor}
          onAddToBasket={onAddToBasket}
        />
      ))}
    </div>
  );
}