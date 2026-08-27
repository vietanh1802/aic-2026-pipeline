import { useState } from "react";

import KeyframeImg from "../KeyframeImg";
import { accuracyColor, accuracyPercent } from "../FrameDisplay/accuracy";
import { frameGap } from "../../helpers/candidates";
import type {
  TemporalCandidate,
  TemporalCandidateResult,
  TrakeCandidateResult,
} from "../../types/api";

import { trakeCardKey, type EventPick, type EventSwaps, type TrakeSwapMap } from "./types";

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
  action,
}: {
  rank: number;
  video?: string;
  got?: number;
  total: number;
  score?: number;
  open: boolean;
  onToggle: () => void;
  openLabel: string;
  /** Sits before the expand toggle. TRAKE puts its "Chọn" button here. */
  action?: React.ReactNode;
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
      <span className="ml-auto flex items-center gap-3">
        {action}
        <button
          type="button"
          onClick={onToggle}
          className="text-[11.5px] font-semibold text-proto-primary-active"
        >
          {open ? "Thu lại ▴" : `${openLabel} ▾`}
        </button>
      </span>
    </div>
  );
}

// Sort theo frame_idx (thứ tự thời gian trong video) — dễ quét mắt hơn so
// với sort theo điểm (nhảy lung tung theo thời gian). CHỈ đổi thứ tự HIỂN
// THỊ — không đụng backend, backend vẫn chọn frame chính theo điểm đúng
// thuật toán (score_frame + DP/bidirectional expansion), việc sort này chỉ
// áp dụng cho danh sách "ứng viên khác" lúc duyệt/so sánh bằng mắt.
function byFrameIdx(items: TemporalCandidate[]): TemporalCandidate[] {
  return [...items].sort(
    (a, b) => (a.frame_idx ?? 0) - (b.frame_idx ?? 0)
  );
}

// ─────────────────────────────────────────────────────────────────────────────
//  Lightbox — click 1 frame (chính hoặc trong strip ứng viên) → xem full
//  size, có tên đoạn query phía trên, nút ‹ › duyệt qua các ứng viên CÙNG 1
//  slot (E1, E2... hoặc bắt đầu/kết thúc) cho dễ so sánh/track.
// ─────────────────────────────────────────────────────────────────────────────

function Lightbox({
  label,
  items,
  startIndex,
  onClose,
  onPick,
}: {
  label: string;
  items: TemporalCandidate[];
  startIndex: number;
  onClose: () => void;
  onPick?: (candidate: TemporalCandidate) => void;
}) {
  const [index, setIndex] = useState(startIndex);
  const current = items[index];
  if (!current) return null;

  return (
    <div
      className="fixed inset-0 z-[1000] bg-black/75 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="max-w-4xl w-full"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-2">
          <span className="text-white font-bold text-sm">{label}</span>
          <button
            type="button"
            onClick={onClose}
            className="text-white/80 hover:text-white text-2xl leading-none px-2"
          >
            ✕
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={index === 0}
            onClick={() => setIndex((i) => Math.max(0, i - 1))}
            className="text-white text-3xl font-bold disabled:opacity-25 px-1 shrink-0"
          >
            ‹
          </button>

          <div className="flex-1 min-w-0">
            <KeyframeImg
              src={current.url}
              alt={current.name}
              className="w-full max-h-[70vh] object-contain rounded-lg bg-black"
            />
            <div className="flex items-center justify-between text-white/75 text-[11px] mt-2 font-mono">
              <span className="truncate">{current.name}</span>
              <span className="shrink-0 ml-2">
                frame {current.frame_idx ?? "—"}
                {current.timestamp ? ` · ${current.timestamp}` : ""}
                {typeof current.score === "number" &&
                  ` · điểm ${current.score}`}
              </span>
            </div>
            {onPick && (
              <button
                type="button"
                onClick={() => {
                  onPick(current);
                  onClose();
                }}
                className="mt-2 px-3 py-1.5 rounded-lg bg-proto-primary text-white text-xs font-bold"
              >
                Chọn frame này
              </button>
            )}
          </div>

          <button
            type="button"
            disabled={index === items.length - 1}
            onClick={() =>
              setIndex((i) => Math.min(items.length - 1, i + 1))
            }
            className="text-white text-3xl font-bold disabled:opacity-25 px-1 shrink-0"
          >
            ›
          </button>
        </div>

        <div className="text-center text-white/60 text-xs mt-2">
          {index + 1} / {items.length}
        </div>
      </div>
    </div>
  );
}

// Đảm bảo frame đang được chọn làm chính LUÔN nằm trong list duyệt lightbox
// — top_candidates() backend trả top-10 theo điểm RIÊNG từng bên, còn frame
// chính được DP/bidirectional expansion chọn theo điểm TỔNG, nên về lý
// thuyết có thể (hiếm) không nằm trong top-10 đó.
function withMain(
  items: TemporalCandidate[],
  main: TemporalCandidate | null
): TemporalCandidate[] {
  if (!main) return items;
  return items.some((i) => i.name === main.name) ? items : [main, ...items];
}

function Strip({
  label,
  tone,
  items,
  pickedName,
  onPick,
  onExpand,
}: {
  label: string;
  tone: "start" | "end" | "event";
  items: TemporalCandidate[];
  pickedName?: string;
  onPick: (candidate: TemporalCandidate) => void;
  onExpand: (index: number) => void;
}) {
  const ring = {
    start: "border-[#5db872]",
    end: "border-[#c64545]",
    event: "border-proto-primary",
  }[tone];
  const sorted = byFrameIdx(items);
  return (
    <div className="mt-2">
      <div className="text-[10px] font-extrabold uppercase tracking-wide text-proto-muted mb-1">
        {label} · {sorted.length}
      </div>
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {sorted.map((item, i) => (
          <button
            key={item.name}
            type="button"
            onClick={() => onPick(item)}
            onDoubleClick={() => onExpand(i)}
            title={`${item.name}${
              item.score ? ` · điểm ${item.score}` : ""
            } — click để chọn, click đúp để xem full size`}
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
  parts,
  fps,
}: {
  result: TemporalCandidateResult;
  rank: number;
  parts: string[];
  fps: number;
}) {
  const [open, setOpen] = useState(false);
  const [start, setStart] = useState<TemporalCandidate | null>(null);
  const [end, setEnd] = useState<TemporalCandidate | null>(null);
  const [lightbox, setLightbox] = useState<"start" | "end" | null>(null);

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

  const startMain: TemporalCandidate | null = result.start_frame
    ? {
        name: result.start_frame,
        url: result.start_url ?? "",
        frame_idx: result.start_frame_idx,
        timestamp: result.start_ts,
      }
    : null;
  const endMain: TemporalCandidate | null = result.end_frame
    ? {
        name: result.end_frame,
        url: result.end_url ?? "",
        frame_idx: result.end_frame_idx,
        timestamp: result.end_ts,
      }
    : null;

  const startPool = byFrameIdx(
    withMain(result.left_candidates ?? [], start ?? startMain)
  );
  const endPool = byFrameIdx(
    withMain(result.right_candidates ?? [], end ?? endMain)
  );
  const startPickedName = start?.name ?? result.start_frame;
  const endPickedName = end?.name ?? result.end_frame;

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
        openLabel="Chỉnh biên"
      />
      <div className="px-3 py-2.5">
        <div className="flex items-center gap-3">
          {/* Cỡ khung khớp FrameDisplay (grid minmax(240px,1fr) + aspect-[3/2])
              — chỉ đổi kích cỡ, KHÔNG đổi bố cục hàng ngang đang có. */}
          <div className="w-[240px] shrink-0">
            <div className="text-[10px] font-extrabold uppercase tracking-wide text-[#3d7a4d] mb-1">
              Bắt đầu
            </div>
            <button
              type="button"
              onClick={() => setLightbox("start")}
              className="block w-full"
            >
              <KeyframeImg
                src={startUrl}
                alt="start"
                className="w-full aspect-[3/2] object-cover rounded-lg border-[3px] border-[#5db872]"
              />
            </button>
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

          <div className="w-[240px] shrink-0">
            <div className="text-[10px] font-extrabold uppercase tracking-wide text-[#8f3030] mb-1">
              Kết thúc
            </div>
            <button
              type="button"
              onClick={() => setLightbox("end")}
              className="block w-full"
            >
              <KeyframeImg
                src={endUrl}
                alt="end"
                className="w-full aspect-[3/2] object-cover rounded-lg border-[3px] border-[#c64545]"
              />
            </button>
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
              pickedName={startPickedName}
              onPick={setStart}
              onExpand={() => setLightbox("start")}
            />
            <Strip
              label="Ứng viên khác cho điểm kết thúc"
              tone="end"
              items={result.right_candidates ?? []}
              pickedName={endPickedName}
              onPick={setEnd}
              onExpand={() => setLightbox("end")}
            />
          </div>
        )}
      </div>

      {lightbox && (
        <Lightbox
          label={lightbox === "start" ? `Bắt đầu — ${parts[0] ?? ""}` : `Kết thúc — ${parts[1] ?? ""}`}
          items={lightbox === "start" ? startPool : endPool}
          startIndex={(lightbox === "start" ? startPool : endPool).findIndex(
            (c) => c.name === (lightbox === "start" ? startPickedName : endPickedName)
          )}
          onClose={() => setLightbox(null)}
          onPick={lightbox === "start" ? setStart : setEnd}
        />
      )}
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
          parts={parts}
          fps={fpsOf(result.video)}
        />
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
//  TRAKE — one line of N cells, each cell a KIS result card.
//
//  The line was already the right shape. What it never had was KIS's own move:
//  click the frame, watch the video at that instant. Everything below is that
//  card's anatomy applied per event — score-tinted border, the magnifier that
//  opens the player, the name/timestamp footer — plus a candidate strip under
//  each cell, because choosing "cách khớp" is a per-event choice.
//
//  Picks live in the parent rather than here: the video popup App owns has to
//  be able to write a scrubbed frame back into one cell.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Colour for one event's frame, normalised inside that event's own candidates.
 *
 * TrakeEvent.score is a cosine similarity ×100 and its usable band differs per
 * event, so feeding it raw into the KIS ramp would paint whole rows one colour.
 * Normalising against the alternates the backend offered for the same event is
 * the trick FrameDisplay already uses against the results on screen.
 */
function eventTone(pick: EventPick | null, pool: TemporalCandidate[]): string {
  const scores = pool
    .map((candidate) => candidate.score)
    .filter((score): score is number => typeof score === "number");
  if (typeof pick?.score !== "number" || scores.length < 2) {
    return "#e6dfd8";
  }
  const min = Math.min(...scores, pick.score);
  const max = Math.max(...scores, pick.score);
  return accuracyColor(accuracyPercent(pick.score, min, max));
}

function TrakeCard({
  result,
  rank,
  parts,
  swaps,
  onSwap,
  onOpenEvent,
  onCommit,
}: {
  result: TrakeCandidateResult;
  rank: number;
  parts: string[];
  swaps: EventSwaps;
  onSwap: (eventIndex: number, pick: EventPick) => void;
  /** Open the video at this event's frame. Undefined hides the magnifier. */
  onOpenEvent?: (eventIndex: number, pick: EventPick) => void;
  /** Write the whole line as one answer. Undefined hides the button. */
  onCommit?: (video: string, frames: number[]) => void;
}) {
  const [open, setOpen] = useState(true);
  const [lightboxAt, setLightboxAt] = useState<number | null>(null);

  const events = result.events ?? [];
  const count = Math.max(parts.length, events.length);
  const slots = Array.from({ length: count }, (_, index) => index);

  const pickAt = (index: number): EventPick | null =>
    swaps[index] ?? events[index] ?? null;
  const poolAt = (index: number): TemporalCandidate[] =>
    events[index]?.candidates ?? [];

  const frames = slots.map((index) => pickAt(index)?.frame_idx);
  // A row missing an event is not a submission. TRAKE scores the whole tuple,
  // so a short row is a wrong row rather than a partial one.
  const missing = frames.findIndex((frame) => typeof frame !== "number");
  const complete = missing === -1;

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
        onToggle={() => setOpen((value) => !value)}
        openLabel="Ứng viên từng mốc"
        action={
          onCommit ? (
            <button
              type="button"
              disabled={!complete}
              title={
                complete
                  ? "Thêm cả hàng vào giỏ thành một dòng"
                  : `Thiếu mốc E${missing + 1}`
              }
              onClick={() => onCommit(result.video ?? "", frames as number[])}
              className="text-[11.5px] font-bold px-2.5 py-1 rounded-[7px] border border-proto-primary bg-proto-primary text-white disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Chọn ▸
            </button>
          ) : null
        }
      />

      {/* One line, N cells — the line IS the event count. */}
      <div className="flex gap-2.5 px-3 py-3 overflow-x-auto">
        {slots.map((index) => {
          const pick = pickAt(index);
          const pool = poolAt(index);
          const tone = eventTone(pick, pool);
          return (
            <div key={index} className="flex-1 min-w-[168px]">
              <div className="flex items-center gap-1.5 mb-1">
                <span className="text-[10px] font-extrabold font-mono text-proto-primary-active">
                  E{index + 1}
                </span>
                <span className="text-[10.5px] text-proto-muted truncate">
                  {parts[index] ?? ""}
                </span>
              </div>

              {/* The KIS card, per event. */}
              <div
                className="rounded-[8px] border-2 bg-white overflow-hidden"
                style={{ borderColor: tone }}
              >
                <div className="relative w-full aspect-[3/2] bg-proto-dark">
                  {pick?.url ? (
                    <KeyframeImg
                      src={pick.url}
                      alt={parts[index] ?? `E${index + 1}`}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex flex-col items-center justify-center text-center px-2 gap-1">
                      {pick ? (
                        <>
                          <span className="font-mono font-bold text-proto-canvas text-lg">
                            {pick.frame_idx}
                          </span>
                          <span className="text-[10px] text-neutral-400">
                            chốt tay — không có ảnh keyframe
                          </span>
                        </>
                      ) : (
                        <span className="text-[10.5px] text-neutral-400">
                          không tìm thấy mốc này trong video
                        </span>
                      )}
                    </div>
                  )}

                  {/* Same corner, same icon, same job as on a KIS result. */}
                  {pick && onOpenEvent && (
                    <button
                      type="button"
                      title={`Mở video tại mốc E${index + 1}`}
                      onClick={() => onOpenEvent(index, pick)}
                      className="absolute bottom-0 right-0 mr-1 mb-1 p-1 bg-[#EFEFEF] hover:bg-white rounded-[4px] border-2 border-[#E3E3E3]"
                    >
                      <img src="/search.svg" alt="mở video" />
                    </button>
                  )}

                  {pick?.byHand && (
                    <span className="absolute top-0 left-0 ml-1 mt-1 text-[9px] font-bold px-1.5 py-0.5 rounded-[4px] bg-proto-mate text-white">
                      tay
                    </span>
                  )}
                </div>

                <div className="flex flex-col gap-0.5 px-1.5 py-1 text-[10px] text-proto-muted">
                  <span className="truncate font-mono">{pick?.name ?? "—"}</span>
                  <span className="flex items-baseline justify-between gap-2">
                    <span className="font-mono">{pick?.timestamp ?? ""}</span>
                    <b
                      className="font-mono font-bold tabular-nums"
                      style={{ color: tone }}
                    >
                      {pick?.frame_idx ?? "—"}
                    </b>
                  </span>
                </div>
              </div>

              {open && pool.length > 0 && (
                <Strip
                  label={`Cách khớp khác cho E${index + 1}`}
                  tone="event"
                  items={pool}
                  pickedName={pick?.name}
                  onPick={(candidate) => onSwap(index, candidate)}
                  onExpand={() => setLightboxAt(index)}
                />
              )}
            </div>
          );
        })}
      </div>

      {lightboxAt !== null &&
        (() => {
          const current = pickAt(lightboxAt);
          const pool = byFrameIdx(withMain(poolAt(lightboxAt), current));
          return (
            <Lightbox
              label={`E${lightboxAt + 1} — ${parts[lightboxAt] ?? ""}`}
              items={pool}
              startIndex={Math.max(
                0,
                pool.findIndex((candidate) => candidate.name === current?.name)
              )}
              onClose={() => setLightboxAt(null)}
              onPick={(candidate) => onSwap(lightboxAt, candidate)}
            />
          );
        })()}
    </div>
  );
}

export function TrakeCandidates({
  results,
  parts,
  swaps,
  onSwap,
  onOpenEvent,
  onCommit,
}: {
  results: TrakeCandidateResult[];
  parts: string[];
  swaps: TrakeSwapMap;
  onSwap: (cardKey: string, eventIndex: number, pick: EventPick) => void;
  onOpenEvent?: (
    cardKey: string,
    eventIndex: number,
    pick: EventPick,
    video: string
  ) => void;
  onCommit?: (video: string, frames: number[]) => void;
}) {
  return (
    <div>
      {results.map((result, index) => {
        const key = trakeCardKey(result.video, index);
        return (
          <TrakeCard
            key={key}
            result={result}
            rank={index + 1}
            parts={parts}
            swaps={swaps[key] ?? {}}
            onSwap={(eventIndex, pick) => onSwap(key, eventIndex, pick)}
            onOpenEvent={
              onOpenEvent
                ? (eventIndex, pick) =>
                    onOpenEvent(key, eventIndex, pick, result.video ?? "")
                : undefined
            }
            onCommit={onCommit}
          />
        );
      })}
    </div>
  );
}
