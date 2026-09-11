// Shared visual primitives for the retrieval benchmark UI — the run summary
// page, its per-query table, and the case-detail panel all need to say "what
// happened to this query" and "where did R@k land" in the same language.
// Before this file existed, the page spelled hit/miss as raw "×"/"✓" glyphs
// and three separate Video/Interval/Status columns, while the detail panel
// spelled the same underlying facts out as full sentences — a reader had to
// re-learn the notation in every place it showed up. Pulling the mapping
// (result -> state) and the two small renderers (dot+label, heat-strip) into
// one place keeps that mapping defined exactly once.
import type { RAt } from "../../api/retrievalBenchmark";
import { R_AT_CUTS } from "../../api/retrievalBenchmark";

export type ResultState = "hit" | "wrong-frame" | "video-miss" | "failed" | "pending";

interface ResultSummary {
  state: ResultState;
  label: string;
  // The triage number to show next to the dot — video rank or frame rank,
  // whichever the state is actually about. Null when there is no rank to
  // show (video never appeared at all, or the query hasn't finished).
  rankLabel: string | null;
}

const PENDING_LABEL: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  interrupted: "Interrupted",
};

/** One dot-and-label verdict per query result, aware of task type: TRAKE
 * carries no frame-interval data at all (backend/app/evaluation/scoring.py
 * passes valid_intervals=None for it and every interval field comes back
 * null), so it can only ever be "found the video" or "video missed" — never
 * "wrong frame", because there is nothing to check that against. */
export function describeResult(result: {
  status: string;
  task_type: string;
  reference_video_rank: number | null;
  interval_hit: boolean | null;
  interval_rank: number | null;
}): ResultSummary {
  if (result.status === "failed") {
    return { state: "failed", label: "Failed", rankLabel: null };
  }
  if (result.status !== "completed") {
    return {
      state: "pending",
      label: PENDING_LABEL[result.status] ?? result.status,
      rankLabel: null,
    };
  }

  if (result.reference_video_rank === null) {
    return { state: "video-miss", label: "Video missed", rankLabel: null };
  }

  if (result.task_type === "TRAKE") {
    return {
      state: "hit",
      label: "Video found",
      rankLabel: `video rank ${result.reference_video_rank}`,
    };
  }

  if (result.interval_hit) {
    return {
      state: "hit",
      label: "Right video & frame",
      rankLabel: `frame rank ${result.interval_rank}`,
    };
  }

  return {
    state: "wrong-frame",
    label: "Right video, wrong frame",
    rankLabel: `video rank ${result.reference_video_rank}`,
  };
}

const STATE_COLOR: Record<ResultState, string> = {
  hit: "#3d7a4d",
  "wrong-frame": "#c9962b",
  "video-miss": "#c64545",
  failed: "#c64545",
  pending: "#69707c",
};

export function ResultDot({ state, size = 8 }: { state: ResultState; size?: number }) {
  return (
    <span
      aria-hidden
      className="inline-block rounded-full shrink-0"
      style={{ width: size, height: size, background: STATE_COLOR[state] }}
    />
  );
}

/** Compact form for table rows: dot, label, and the triage rank number on
 * one line. `verbose` (case-detail panel) adds a little breathing room but
 * shows the same three things — never color alone, per accessibility. */
export function ResultIndicator({
  result,
  verbose = false,
}: {
  result: {
    status: string;
    task_type: string;
    reference_video_rank: number | null;
    interval_hit: boolean | null;
    interval_rank: number | null;
  };
  verbose?: boolean;
}) {
  const { state, label, rankLabel } = describeResult(result);
  return (
    <span
      className={`inline-flex items-center gap-1.5 ${verbose ? "text-[13px]" : "text-[12px]"}`}
    >
      <ResultDot state={state} size={verbose ? 9 : 7} />
      <span className="font-medium text-proto-ink">{label}</span>
      {rankLabel && <span className="font-mono text-proto-muted">· {rankLabel}</span>}
    </span>
  );
}

/** R@k as a five-cell heat-strip rather than a text row of percentages (run
 * summary) or a row of ×/✓ glyphs (per-query table, case detail). Takes
 * either a per-query hit map (0/1 per cut, see perQueryRAt below) or an
 * aggregate rate (0..1 per cut) from the run/task-type summary — same visual
 * language at both altitudes, just a lighter fill for a lower rate. */
export function RAtHeatStrip({
  rAt,
  cuts = R_AT_CUTS,
  size = "md",
}: {
  rAt: RAt;
  cuts?: readonly number[];
  size?: "sm" | "md";
}) {
  const cellPx = size === "sm" ? 13 : 17;
  return (
    <span className="inline-flex items-center gap-[3px]" role="img" aria-label="R at k results">
      {cuts.map((cut) => {
        const value = Math.max(0, Math.min(1, rAt[String(cut)] ?? 0));
        return (
          <span
            key={cut}
            title={`R@${cut}: ${(value * 100).toFixed(0)}%`}
            className="rounded-[3px] border border-proto-line"
            style={{
              width: cellPx,
              height: cellPx,
              background: value === 0 ? "transparent" : `rgba(61,122,77,${0.25 + value * 0.75})`,
            }}
          />
        );
      })}
    </span>
  );
}

/** Builds the per-query "hit map" RAtHeatStrip expects from a single
 * interval_rank — R@k is 1 exactly when the matched frame's rank is <= k,
 * mirroring the aggregate computation in scoring.py's score_frame_intervals. */
export function perQueryRAt(
  intervalRank: number | null,
  cuts: readonly number[] = R_AT_CUTS
): RAt {
  const out: RAt = {};
  for (const cut of cuts) {
    out[String(cut)] = intervalRank !== null && intervalRank <= cut ? 1 : 0;
  }
  return out;
}
