// frontend/src/components/TextIndexStatus/index.tsx

import { useEffect, useState } from "react";

import { videoSearchApi } from "../../types/api";
import type { SystemStatus } from "../../types/api";

const POLL_MS = 15000;

type LoadState = "checking" | "ready" | "not_ready";

function stateOf(ready: boolean | undefined): LoadState {
  if (ready === undefined) return "checking";
  return ready ? "ready" : "not_ready";
}

// Amber, not red: one source being unloaded still leaves the text filter
// partially usable (the other source, or the substring/regex fallback) --
// red on ApiStatus means the whole API is unreachable, a different severity.
const DOT_CLASS: Record<LoadState, string> = {
  checking: "bg-proto-line",
  ready: "bg-proto-teal",
  not_ready: "bg-proto-amber",
};

/**
 * ASR/OCR text-index readiness -- two small dots next to the text-filter row.
 *
 * The reason this exists: `annotate_videos()` renders a genuine "no match"
 * and "the index never loaded" as the exact same matched=false badge (see
 * asr_text.py/text_signal.py) -- there is no way to tell them apart from the
 * badge alone. This is the one place that distinction becomes visible: check
 * these are green BEFORE trusting a "no match" result, not after.
 */
export default function TextIndexStatus() {
  const [status, setStatus] = useState<SystemStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const result = await videoSearchApi.getStatus();
        if (!cancelled) setStatus(result);
      } catch {
        // Indistinguishable from "still starting up" here on purpose --
        // ApiStatus already owns reporting outright API failure.
        if (!cancelled) setStatus(null);
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const asrReady = status?.asr_text?.ready;
  const ocrReady = status?.ocr?.ready;

  const asrTitle =
    asrReady === true
      ? `ASR index loaded (${status?.asr_text?.entries_loaded ?? 0} entries)`
      : asrReady === false
      ? `ASR index not loaded${
          status?.asr_text?.files_present === false ? " — file missing on disk" : ""
        }`
      : "Checking ASR index…";
  const ocrTitle =
    ocrReady === true
      ? `OCR index loaded (${status?.ocr?.frames_with_text ?? 0} frames with text)`
      : ocrReady === false
      ? `OCR index not loaded${
          status?.ocr?.files_present === false ? " — file missing on disk" : ""
        }`
      : "Checking OCR index…";

  return (
    <span
      className="inline-flex items-center gap-1.5 text-[11px] text-proto-muted"
      title="Text-filter data sources"
    >
      <span className="inline-flex items-center gap-0.5" title={asrTitle}>
        <i className={`w-1.5 h-1.5 rounded-full shrink-0 ${DOT_CLASS[stateOf(asrReady)]}`} />
        ASR
      </span>
      <span className="inline-flex items-center gap-0.5" title={ocrTitle}>
        <i className={`w-1.5 h-1.5 rounded-full shrink-0 ${DOT_CLASS[stateOf(ocrReady)]}`} />
        OCR
      </span>
    </span>
  );
}
