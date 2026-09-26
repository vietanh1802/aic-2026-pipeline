// frontend/src/components/VideoPopUp/YoutubeTimeline.tsx

import { useState } from "react";

import { frameToMs } from "../../helpers/frameIdentity";
import { frameAt } from "../../helpers/frameRange";
import {
  formatClock,
  parseClock,
  youtubeUrlAt,
  type YoutubeInfo,
} from "../../helpers/youtube";

/**
 * Chọn khoảnh khắc mà KHÔNG cần video trong popup tải xong.
 *
 * Mạng phòng thi có thể chỉ vài Mbit/s, trong khi file gốc trên S3 là
 * 720p/1080p. YouTube tự hạ chất lượng nên xem mượt, nhưng không nhúng được
 * để lấy vị trí phát (mức 1 — mở ở tab riêng). Nên khung này là một thanh thời
 * gian GIẢ dài đúng bằng video YouTube: xem ở tab YouTube, thấy cảnh đúng thì
 * gõ/kéo tới cùng giây đó ở đây, và khối "Nộp DRES" nộp thời điểm này.
 *
 * Số frame · ms hiện ở đây quy đổi y như lúc nộp (frameAt rồi frameToMs), nên
 * con số nhìn thấy là con số được gửi.
 */
export default function YoutubeTimeline({
  info,
  fps,
  picked,
  onPick,
  playerSeconds,
  onSeekPlayer,
}: {
  info: YoutubeInfo;
  fps: number;
  /** Giây đang chọn trên khung, null = chưa chọn (DRES dùng trình phát). */
  picked: number | null;
  onPick: (seconds: number | null) => void;
  /** Vị trí trình phát trong popup — điểm xuất phát khi chưa chọn gì. */
  playerSeconds: number;
  onSeekPlayer: (seconds: number) => void;
}) {
  const clamp = (s: number) => Math.min(info.length, Math.max(0, s));
  const cursor = clamp(picked ?? playerSeconds);
  // Ô gõ hiện con trỏ, trừ lúc đang gõ dở — lúc đó giữ nguyên chữ người gõ.
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [bad, setBad] = useState(false);

  const frame = frameAt(cursor, fps);
  const ms = frameToMs(frame, fps);
  const step = fps > 0 ? 1 / fps : 0.04;
  const nudge = (delta: number) => onPick(clamp(cursor + delta));

  const apply = () => {
    if (!editing) {
      return;
    }
    const seconds = parseClock(text);
    if (seconds === null || seconds > info.length + 1) {
      setBad(true);
      return;
    }
    setBad(false);
    setEditing(false);
    onPick(clamp(seconds));
  };

  const small =
    "px-2 py-0.5 rounded-[6px] border border-proto-line bg-white text-[11.5px] font-mono hover:border-[#c4302b]";

  return (
    <div className="mt-2 px-3 py-2.5 rounded-[10px] border-2 border-[#c4302b]/40 bg-[#c4302b]/5 font-baloo">
      <div className="flex items-center gap-2 flex-wrap mb-2">
        <b className="text-[13px] text-[#c4302b]">Khung thời gian YouTube</b>
        <span className="text-[11.5px] text-proto-muted">
          dài {formatClock(info.length).replace(/\.000$/, "")}
        </span>
        <a
          href={youtubeUrlAt(info.id, cursor)}
          target="_blank"
          rel="noreferrer"
          className="ml-auto px-3 py-1 rounded-[7px] bg-[#c4302b] text-white text-[12px] font-bold hover:opacity-90"
          title="Mở tab YouTube đúng giây này (YouTube chỉ nhận nguyên giây)"
        >
          ▶ Mở YouTube tại {formatClock(Math.floor(cursor)).replace(/\.000$/, "")}
        </a>
      </div>

      <input
        type="range"
        min={0}
        max={info.length}
        step="any"
        value={cursor}
        onChange={(e) => onPick(clamp(Number(e.target.value)))}
        className="w-full accent-[#c4302b]"
        aria-label="Chọn thời điểm trên video YouTube"
      />

      <div className="flex items-center gap-1.5 flex-wrap mt-1">
        <input
          value={editing ? text : formatClock(cursor)}
          onChange={(e) => {
            setText(e.target.value);
            setEditing(true);
            setBad(false);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              apply();
            }
          }}
          onBlur={apply}
          placeholder="vd 10:27"
          className={`w-[110px] px-2 py-0.5 rounded-[6px] border text-[12.5px] font-mono bg-white ${
            bad ? "border-[#c64545]" : "border-proto-line"
          }`}
          title="Gõ giây như đồng hồ YouTube: 10:27, 1:02:03, 10:27.5 — Enter để chọn"
        />
        <button type="button" className={small} onClick={() => nudge(-5)}>−5s</button>
        <button type="button" className={small} onClick={() => nudge(-1)}>−1s</button>
        <button type="button" className={small} onClick={() => nudge(-step)}>−1f</button>
        <button type="button" className={small} onClick={() => nudge(step)}>+1f</button>
        <button type="button" className={small} onClick={() => nudge(1)}>+1s</button>
        <button type="button" className={small} onClick={() => nudge(5)}>+5s</button>
      </div>

      <div className="flex items-center gap-2 flex-wrap mt-2 text-[12px]">
        <span className="text-proto-muted">
          {picked === null ? "Chưa chọn — đang theo trình phát:" : "Đã chọn:"}{" "}
          <b className="font-mono text-proto-ink">
            {formatClock(cursor)}
            {frame !== null && ` · frame ${frame}`}
            {ms !== null && ` · ${ms} ms`}
          </b>
        </span>
        {bad && <span className="text-[#c64545]">Không đọc được giờ này</span>}
        <span className="ml-auto flex items-center gap-2">
          <button
            type="button"
            className="text-[11.5px] font-semibold text-proto-primary-active underline decoration-dotted"
            onClick={() => onSeekPlayer(cursor)}
            title="Tua trình phát trong popup tới thời điểm này để soi lại"
          >
            tua trình phát tới đây
          </button>
          {picked !== null && (
            <button
              type="button"
              className="text-[11.5px] text-proto-muted underline"
              onClick={() => onPick(null)}
            >
              bỏ chọn
            </button>
          )}
        </span>
      </div>
      {picked !== null && (
        <p className="mt-1 text-[11px] text-[#c4302b]">
          Khối "Nộp DRES" đang dùng thời điểm này, không phải vị trí trình phát.
        </p>
      )}
    </div>
  );
}
