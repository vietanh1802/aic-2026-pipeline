import { useState } from "react";

import KeyframeImg from "../KeyframeImg";
import { frameGap } from "../../helpers/candidates";
import type {
  TemporalCandidate,
  TemporalCandidateResult,
  TrakeCandidateResult,
} from "../../types/api";

// Auto-discovery xếp theo discovery_score (tần suất: bao nhiêu đoạn của query
// khớp video này) rồi tới discovery_score_sum. Backend đã sắp sẵn, client giữ
// nguyên thứ tự đó.

function Hit({ got, total }: { got?: number; total: number }) {
  const full = total > 0 && got === total;
  return (
    <span
      className={`text-[10px] font-bold px-2 py-0.5 rounded-full whitespace-nowrap ${
        full
          ? "bg-proto-teal/25 text-[#2f6b60]"
          : "bg-proto-amber/25 text-[#8a5a15]"
      }`}
      title="Số đoạn của query khớp video này (discovery_score)"
    >
      {got ?? 0}/{total} khớp
    </span>
  );
}

function CardHead({
  rank,
  video,
  got,
  total,
  score,
  open,
  onToggle,
  openLabel,
}: {
  rank: number;
  video?: string;
  got?: number;
  total: number;
  score?: number;
  open: boolean;
  onToggle: () => void;
  openLabel: string;
}) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-proto-soft border-b border-proto-line">
      <i
        className={`not-italic w-5 h-5 rounded-full text-[11px] font-extrabold flex items-center justify-center shrink-0 ${
          rank === 1
            ? "bg-proto-primary text-white"
            : "bg-proto-cream-strong text-proto-muted"
        }`}
      >
        {rank}
      </i>
      <span className="font-mono font-bold text-proto-ink text-[13px]">
        {video ?? "?"}
      </span>
      <Hit got={got} total={total} />
      {typeof score === "number" && (
        <span className="font-mono text-[11px] text-proto-muted">
          {score.toFixed(3)}
        </span>
      )}
      <button
        type="button"
        onClick={onToggle}
        className="ml-auto text-[11.5px] font-semibold text-proto-primary-active"
      >
        {open ? "Thu lại ▴" : `${openLabel} ▾`}
      </button>
    </div>
  );
}

function Strip({
  label,
  tone,
  items,
  pickedName,
  onPick,
}: {
  label: string;
  tone: "start" | "end" | "event";
  items: TemporalCandidate[];
  pickedName?: string;
  onPick: (candidate: TemporalCandidate) => void;
}) {
  const ring = {
    start: "border-[#5db872]",
    end: "border-[#c64545]",
    event: "border-proto-primary",
  }[tone];
  return (
    <div className="mt-2">
      <div className="text-[10px] font-extrabold uppercase tracking-wide text-proto-muted mb-1">
        {label} · {items.length}
      </div>
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {items.map((item) => (
          <button
            key={item.name}
            type="button"
            onClick={() => onPick(item)}
            title={`${item.name}${item.score ? ` · điểm ${item.score}` : ""}`}
            className="w-[76px] shrink-0 text-left"
          >
            <KeyframeImg
              src={item.url}
              alt={item.name}
              className={`w-full h-[46px] object-cover rounded border-2 ${
                item.name === pickedName ? ring : "border-proto-line"
              }`}
            />
            <div className="text-[9.5px] text-center text-proto-muted mt-0.5 font-mono">
              {item.frame_idx ?? "—"}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function TemporalCard({
  result,
  rank,
  total,
  fps,
}: {
  result: TemporalCandidateResult;
  rank: number;
  total: number;
  fps: number;
}) {
  const [open, setOpen] = useState(false);
  const [start, setStart] = useState<TemporalCandidate | null>(null);
  const [end, setEnd] = useState<TemporalCandidate | null>(null);

  const startUrl = start?.url ?? result.start_url;
  const endUrl = end?.url ?? result.end_url;
  const startIdx = start?.frame_idx ?? result.start_frame_idx;
  const endIdx = end?.frame_idx ?? result.end_frame_idx;
  const startTs = start?.timestamp ?? result.start_ts;
  const endTs = end?.timestamp ?? result.end_ts;
  const gap =
    typeof startIdx === "number" && typeof endIdx === "number"
      ? frameGap(startIdx, endIdx, fps)
      : null;

  return (
    <div
      className={`rounded-[10px] bg-white overflow-hidden mb-2 border ${
        rank === 1 ? "border-proto-primary" : "border-proto-line"
      }`}
    >
      <CardHead
        rank={rank}
        video={result.video}
        got={result.discovery_score}
        total={total}
        score={result.combined_score}
        open={open}
        onToggle={() => setOpen((v) => !v)}
        openLabel="Chỉnh biên"
      />
      <div className="px-3 py-2.5">
        <div className="flex items-center gap-3">
          <div className="w-[168px] shrink-0">
            <div className="text-[10px] font-extrabold uppercase tracking-wide text-[#3d7a4d] mb-1">
              Bắt đầu
            </div>
            <KeyframeImg
              src={startUrl}
              alt="start"
              className="w-full h-[100px] object-cover rounded-lg border-[3px] border-[#5db872]"
            />
            <div className="flex justify-between text-[10.5px] text-proto-muted mt-1">
              <b className="font-mono text-proto-ink">{startIdx ?? "—"}</b>
              <span>{startTs ?? ""}</span>
            </div>
          </div>

          <div className="flex-1 text-center text-[11px] text-proto-muted">
            <div>cách nhau</div>
            <div className="h-0.5 rounded my-1.5 bg-gradient-to-r from-[#5db872] to-[#c64545]" />
            <div>
              {gap ? (
                <>
                  <b className="font-mono text-proto-ink">{gap.frames} frame</b>
                  {gap.seconds > 0 && ` · ${gap.seconds.toFixed(1)} s`}
                </>
              ) : (
                "—"
              )}
            </div>
          </div>

          <div className="w-[168px] shrink-0">
            <div className="text-[10px] font-extrabold uppercase tracking-wide text-[#8f3030] mb-1">
              Kết thúc
            </div>
            <KeyframeImg
              src={endUrl}
              alt="end"
              className="w-full h-[100px] object-cover rounded-lg border-[3px] border-[#c64545]"
            />
            <div className="flex justify-between text-[10.5px] text-proto-muted mt-1">
              <b className="font-mono text-proto-ink">{endIdx ?? "—"}</b>
              <span>{endTs ?? ""}</span>
            </div>
          </div>
        </div>

        {open && (
          <div className="mt-3 pt-2.5 border-t border-dashed border-proto-line">
            <Strip
              label="Ứng viên khác cho điểm bắt đầu"
              tone="start"
              items={result.left_candidates ?? []}
              pickedName={start?.name ?? result.start_frame}
              onPick={setStart}
            />
            <Strip
              label="Ứng viên khác cho điểm kết thúc"
              tone="end"
              items={result.right_candidates ?? []}
              pickedName={end?.name ?? result.end_frame}
              onPick={setEnd}
            />
          </div>
        )}
      </div>
    </div>
  );
}

export function TemporalCandidates({
  results,
  parts,
  fpsOf,
}: {
  results: TemporalCandidateResult[];
  parts: string[];
  fpsOf: (video?: string) => number;
}) {
  return (
    <div>
      {results.map((result, index) => (
        <TemporalCard
          key={`${result.video}-${index}`}
          result={result}
          rank={index + 1}
          total={parts.length}
          fps={fpsOf(result.video)}
        />
      ))}
    </div>
  );
}

function TrakeCard({
  result,
  rank,
  parts,
}: {
  result: TrakeCandidateResult;
  rank: number;
  parts: string[];
}) {
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState(0);
  const [swaps, setSwaps] = useState<Record<number, TemporalCandidate>>({});
  const events = result.events ?? [];

  return (
    <div
      className={`rounded-[10px] bg-white overflow-hidden mb-2 border ${
        rank === 1 ? "border-proto-primary" : "border-proto-line"
      }`}
    >
      <CardHead
        rank={rank}
        video={result.video}
        got={result.discovery_score}
        total={parts.length}
        score={result.combined_score}
        open={open}
        onToggle={() => setOpen((v) => !v)}
        openLabel="Chỉnh từng mốc"
      />
      <div className="px-3 py-2.5">
        <div className="flex gap-2">
          {parts.map((label, index) => {
            const event = swaps[index] ?? events[index];
            const isPicked = open && picked === index;
            return (
              <button
                key={index}
                type="button"
                onClick={() => setPicked(index)}
                className="flex-1 min-w-0 text-left"
              >
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="text-[10px] font-extrabold text-proto-primary-active">
                    E{index + 1}
                  </span>
                  <span className="text-[10px] text-proto-muted truncate">
                    {label}
                  </span>
                </div>
                <KeyframeImg
                  src={event?.url}
                  alt={label}
                  className={`w-full h-[78px] object-cover rounded-lg border-2 ${
                    isPicked ? "border-proto-primary" : "border-proto-line"
                  }`}
                />
                <div className="flex justify-between text-[10px] mt-1">
                  {event ? (
                    <>
                      <b className="font-mono text-proto-ink">
                        {event.frame_idx ?? "—"}
                      </b>
                      <span className="text-proto-muted">
                        {event.timestamp ?? ""}
                      </span>
                    </>
                  ) : (
                    <span className="text-[#c64545] font-bold">
                      — không khớp
                    </span>
                  )}
                </div>
              </button>
            );
          })}
        </div>

        {open && (
          <div className="mt-3 pt-2.5 border-t border-dashed border-proto-line">
            <Strip
              label={`Ứng viên khác cho E${picked + 1}`}
              tone="event"
              items={events[picked]?.candidates ?? []}
              pickedName={(swaps[picked] ?? events[picked])?.name}
              onPick={(candidate) =>
                setSwaps((prev) => ({ ...prev, [picked]: candidate }))
              }
            />
          </div>
        )}
      </div>
    </div>
  );
}

export function TrakeCandidates({
  results,
  parts,
}: {
  results: TrakeCandidateResult[];
  parts: string[];
}) {
  return (
    <div>
      {results.map((result, index) => (
        <TrakeCard
          key={`${result.video}-${index}`}
          result={result}
          rank={index + 1}
          parts={parts}
        />
      ))}
    </div>
  );
}
